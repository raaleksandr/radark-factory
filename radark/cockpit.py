"""The owner cockpit (change owner-cockpit): a local web page that lists every handover addressed to the owner team
in the hubs of all known pipelines and answers short ones through `ho`.

A threaded `http.server` on 127.0.0.1 only; the page (`cockpit_page.html`) is one self-contained document. Reads
are `ho list --to <owner> --status all` and `ho show`, answers `ho respond|done|ack|decline <ID> --body -` followed
by `ho sync`, all as the owner team through `hub.Hub`, after the same `ho` contract check the engine uses. The
server never writes a hub file; the only file it changes is the machine-wide pipeline registry. The History tab
(`GET /api/history`, change cockpit-history) reads each pipeline's `runs.jsonl` and `ho list --status all` through
`cockpit_history`."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import cockpit_history as history_mod
from . import config as config_mod
from . import machine as machine_mod
from .hub import OWNER_ACTIONS, Hub, HoError, HoLifecycleError, HoVersion, check_ho

APP = "radark-cockpit"
HOST = "127.0.0.1"
DONE_SHOWN = 50  # done items per hub read with `show`; older ones are loaded on demand (design D4)
MAX_REQUEST = 64 * 1024  # bytes of a POST body (design D6)
DRAIN_MAX = 1024 * 1024  # a refused body up to this size is read before the answer (see Handler._drain)
MAX_TEXT = 20_000  # characters of an answer (design D5)
HO_TIMEOUT_S = 30.0  # awake time per `ho` call of the cockpit; a page refresh must not hang for minutes
HEALTH_TIMEOUT_S = 2.0
SHOW_WORKERS = 4  # `ho show` calls at once per hub
PENDING_STATES = ("pending", "acknowledged", "returned")
NEEDS_TEXT = ("respond", "decline")
NOTE = ("Answer here only if a short answer is enough; files to place or code to change must be handled outside "
        "the cockpit.")
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; frame-ancestors 'none'")


def version() -> str:
    try:
        from importlib.metadata import version as dist_version
        return dist_version("radark-factory")
    except Exception:  # noqa: BLE001 - a working tree without an installed distribution
        return "unknown"


def page_html() -> bytes:
    return resources.files("radark").joinpath("cockpit_page.html").read_bytes()


def is_pending(my_state, expects, status, archived=False) -> bool:
    """Still waits for the owner: state pending or returned, or acknowledged on a `done` / `response` handover
    (`ack` of an `expects ack` handover is its answer), and the handover is not closed (design D4)."""
    if status == "closed" or archived:
        return False
    return my_state in PENDING_STATES and not (my_state == "acknowledged" and expects == "ack")


def hub_key(hub: Path, owner_team: str) -> str:
    """An opaque index of (hub, owner team) for the page: the page never sees a hub path (design D4)."""
    return hashlib.sha256(f"{machine_mod.norm(hub)}\0{owner_team}".encode("utf-8")).hexdigest()[:12]


@dataclass
class Group:
    """Pipelines that share one hub and owner team: read once, every name shown on the items."""
    key: str
    hub: Path
    owner_team: str
    ho: list[str]
    names: list[str] = field(default_factory=list)


class Cockpit:
    """The data side of the server: pipelines, hub reads and answers. `hub_factory(ho, hub)` makes the `Hub`."""

    def __init__(self, directory: Path, configs=(), hub_factory=None):
        self.registry = machine_mod.Registry(directory)
        self.configs = [os.path.realpath(str(c)) for c in configs]
        self.hub_factory = hub_factory or (lambda ho, hub: Hub(ho, hub, timeout=HO_TIMEOUT_S))
        self._checked: dict[tuple, HoVersion] = {}
        self._check_lock = threading.Lock()
        self._write_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        self.logs = history_mod.LogCache()

    # ---- pipelines (design D3, D4.1)

    def pipelines(self) -> tuple[list[dict], list[Group], str | None]:
        """(pipeline entries for the page, hub groups, a registry problem line or None)."""
        out, groups, problem, _ = self._load()
        return out, groups, problem

    def _load(self) -> tuple[list[dict], list[Group], str | None, list[tuple[dict, Group, Path]]]:
        """`pipelines()` plus, for each readable pipeline, (entry, its group, its run directory) for the history
        (cockpit-history H1); the run directory never goes to the page."""
        entries, problem = self.registry.read()
        paths = {}
        for e in entries:
            paths.setdefault(machine_mod.norm(e["config"]), (e["config"], e.get("name"), True))
        for c in self.configs:
            key = machine_mod.norm(c)
            old = paths.get(key)
            paths[key] = (c, old[1] if old else None, bool(old))
        out, groups, loaded = [], {}, []
        for path, name, registered in paths.values():
            entry = {"config": path, "name": name or Path(path).parent.name, "registered": registered}
            if not Path(path).is_file():
                out.append({**entry, "state": "missing"})
                continue
            try:
                cfg = config_mod.load(path)
            except config_mod.ConfigError as exc:
                out.append({**entry, "state": "error", "message": str(exc)})
                continue
            key = hub_key(cfg.hub, cfg.owner_team)
            entry.update(name=cfg.pipeline_name(), state="ok", owner_team=cfg.owner_team, hub_key=key)
            group = groups.setdefault(key, Group(key, cfg.hub, cfg.owner_team, list(cfg.ho)))
            if entry["name"] not in group.names:
                group.names.append(entry["name"])
            out.append(entry)
            loaded.append((entry, group, cfg.run_dir))
        return out, list(groups.values()), problem, loaded

    def group(self, key: str) -> Group | None:
        return next((g for g in self.pipelines()[1] if g.key == key), None)

    # ---- reads (design D4)

    def _hub(self, group: Group) -> Hub:
        """The group's `Hub` after the contract check, run once per `ho` command and hub; raises HoError."""
        check = (tuple(group.ho), machine_mod.norm(group.hub))
        with self._check_lock:
            found = self._checked.get(check)
        if found is None:
            result = check_ho(group.ho, group.hub, config_file="the pipeline's configuration")
            if isinstance(result, str):
                raise HoError(f"ho incompatible: {result}")
            with self._check_lock:
                self._checked[check] = result
        return self.hub_factory(group.ho, group.hub)

    def items(self) -> dict:
        """Everything the page shows; one failing hub becomes an error entry, the others still show."""
        pipelines, groups, problem = self.pipelines()
        hubs, pending, done = [], [], []
        with ThreadPoolExecutor(max_workers=max(1, len(groups))) as pool:
            results = list(pool.map(self._read_group, groups))
        for group, (items, error) in zip(groups, results):
            hubs.append({"hub_key": group.key, "pipelines": group.names, "owner_team": group.owner_team,
                         "error": error})
            for it in items:
                (pending if it["pending"] else done).append(it)
        for part in (pending, done):
            part.sort(key=lambda it: it.get("last_activity") or "", reverse=True)
        return {"app": APP, "note": NOTE, "pipelines": pipelines, "hubs": hubs, "pending": pending, "done": done,
                "registry_problem": problem}

    def _read_group(self, group: Group) -> tuple[list[dict], str | None]:
        try:
            hub = self._hub(group)
            listed = hub.addressed_to(group.owner_team)
        except HoError as exc:
            return [], str(exc)
        base = [self._summary(group, h) for h in listed if isinstance(h, dict) and h.get("id")]
        done = sorted((it for it in base if not it["pending"]), key=lambda it: it.get("last_activity") or "",
                      reverse=True)
        skip = {it["id"] for it in done[DONE_SHOWN:]}
        wanted = [it for it in base if it["id"] not in skip]

        def detail(it):
            try:
                return self._with_show(group, it, hub.show(it["id"], team=group.owner_team))
            except HoError as exc:
                return {**it, "partial": True, "show_error": str(exc)}
        with ThreadPoolExecutor(max_workers=SHOW_WORKERS) as pool:
            shown = {it["id"]: it for it in pool.map(detail, wanted)}
        return [shown.get(it["id"], it) for it in base], None

    @staticmethod
    def _summary(group: Group, h: dict) -> dict:
        state = h.get("my_state")
        if not state and isinstance(h.get("recipients"), dict):
            state = h["recipients"].get(group.owner_team)
        status = h.get("status")
        tags = [t for t in (h.get("tags") or []) if isinstance(t, str)]
        return {"hub_key": group.key, "pipelines": list(group.names), "id": h["id"], "title": h.get("title") or "",
                "from": h.get("from"), "expects": h.get("expects"), "status": status, "my_state": state,
                "tags": tags, "escalation": "escalation" in tags, "created": h.get("created"),
                "last_activity": h.get("last_activity"),
                "pending": is_pending(state, h.get("expects"), status, h.get("archived")),
                "body": None, "events": [], "allowed": [], "partial": True}

    @staticmethod
    def _with_show(group: Group, it: dict, shown: dict) -> dict:
        events = [{"at": e.get("at"), "team": e.get("team"), "type": e.get("action") or e.get("type"),
                   "body": e.get("body") or ""} for e in (shown.get("events") or []) if isinstance(e, dict)]
        allowed = [a for a in OWNER_ACTIONS if a in (shown.get("allowed_actions") or [])]
        out = {**it, "body": shown.get("body") or "", "events": events, "partial": False,
               "allowed": allowed if it["pending"] else []}
        for key in ("title", "status", "last_activity", "created"):
            if shown.get(key):
                out[key] = shown[key]
        return out

    def item(self, key: str, handover_id: str) -> tuple[int, dict]:
        """One item with body and events (`GET /api/item`, for done items beyond the newest 50)."""
        group = self.group(key)
        if group is None:
            return 404, {"ok": False, "error": "unknown hub"}
        try:
            hub = self._hub(group)
            shown = hub.show(handover_id, team=group.owner_team)
        except HoError as exc:
            return 502, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "item": self._with_show(group, self._summary(group, shown), shown)}

    # ---- history (cockpit-history H5, H7)

    def history(self, pipeline: str | None = None, period: str = history_mod.DEFAULT_PERIOD, now=None) -> dict:
        """The History of finished work: each pipeline's run log, and each hub read once with `ho list --status
        all` (in parallel, after the contract check). Read only: no `ho` write, no file written."""
        _, _, _, loaded = self._load()
        if pipeline is not None:
            loaded = [x for x in loaded if x[0]["name"] == pipeline]
        hubs: dict[str, Group] = {}
        for _, group, _ in loaded:
            hubs.setdefault(machine_mod.norm(group.hub), group)
        keys = list(hubs)
        with ThreadPoolExecutor(max_workers=max(1, len(keys))) as pool:
            lists = dict(zip(keys, pool.map(lambda k: self._list_all(hubs[k]), keys)))
        inputs = []
        for entry, group, run_dir in loaded:
            items, error = lists[machine_mod.norm(group.hub)]
            inputs.append(history_mod.PipelineInput(entry["name"], self.logs.read(Path(run_dir) / "runs.jsonl"),
                                                    items, error))
        return history_mod.history(inputs, period, pipeline, now)

    def _list_all(self, group: Group) -> tuple[dict[str, dict] | None, str | None]:
        try:
            listed = self._hub(group).all_handovers(group.owner_team)
        except HoError as exc:
            return None, str(exc)
        return {h["id"]: h for h in listed if isinstance(h, dict) and isinstance(h.get("id"), str)}, None

    # ---- answers (design D5)

    def _write_lock(self, key: str) -> threading.Lock:
        with self._locks_lock:
            return self._write_locks.setdefault(key, threading.Lock())

    def act(self, request: dict) -> tuple[int, dict]:
        key, hid, action, text = (request.get(k) for k in ("hub_key", "id", "action", "text"))
        text = "" if text is None else text
        if action not in OWNER_ACTIONS:
            return 400, {"ok": False, "error": f"action must be one of {', '.join(OWNER_ACTIONS)}"}
        if not isinstance(key, str) or not isinstance(hid, str) or not hid:
            return 400, {"ok": False, "error": "hub_key and id are required"}
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            return 400, {"ok": False, "error": f"text must be a string of at most {MAX_TEXT} characters"}
        if action in NEEDS_TEXT and not text.strip():
            return 400, {"ok": False, "error": f"{action} needs a text"}
        group = self.group(key)
        if group is None:
            return 404, {"ok": False, "error": "unknown hub"}
        with self._write_lock(key):
            try:
                hub = self._hub(group)
                shown = hub.show(hid, team=group.owner_team)
            except HoError as exc:
                return 502, {"ok": False, "error": str(exc), "code": getattr(exc, "code", "")}
            allowed = [a for a in OWNER_ACTIONS if a in (shown.get("allowed_actions") or [])]
            if action not in allowed:
                return 409, {"ok": False, "error": "not allowed now", "allowed": allowed}
            try:
                result = hub.act(action, hid, group.owner_team, text.strip() and text)
            except HoLifecycleError as exc:
                return 409, {"ok": False, "error": str(exc), "code": exc.code}
            except HoError as exc:
                return 502, {"ok": False, "error": str(exc), "code": exc.code}
            warning = None
            try:
                hub.sync()
            except HoError as exc:
                warning = f"ho sync failed after the {action}: {exc}"
        return 200, {"ok": True, "result": result, "warning": warning}

    def forget(self, request: dict) -> tuple[int, dict]:
        path = request.get("config")
        if not isinstance(path, str) or not path:
            return 400, {"ok": False, "error": "config is required"}
        try:
            gone = self.registry.forget(path)
        except machine_mod.MachineError as exc:
            return 502, {"ok": False, "error": str(exc)}
        if not gone:
            return 404, {"ok": False, "error": "not registered"}
        return 200, {"ok": True}


# ---- HTTP (design D1, D6)

class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows SO_REUSEADDR would let a second server share the port (design D2)
    daemon_threads = True

    def __init__(self, port: int, cockpit: Cockpit):
        self.cockpit = cockpit
        super().__init__((HOST, port), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = APP
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # quiet: no hub text in the console; only errors, on one line
    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler's signature
        pass

    def log_error(self, format, *args):  # noqa: A002
        sys.stderr.write(f"cockpit: {format % args}\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, data: dict) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _own(self) -> set[str]:
        return {f"{HOST}:{self.server.port}", f"localhost:{self.server.port}"}

    def _host_ok(self) -> bool:
        """Against DNS rebinding: only our own host name and port (design D6)."""
        return (self.headers.get("Host") or "").strip().lower() in self._own()

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"ok": False, "error": "forbidden host"})
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, page_html(), "text/html; charset=utf-8")
            if url.path == "/api/health":
                return self._json(200, {"app": APP, "version": version(), "pid": os.getpid()})
            if url.path == "/api/items":
                return self._json(200, self.server.cockpit.items())
            if url.path == "/api/history":
                period = query.get("period", history_mod.DEFAULT_PERIOD)
                if period not in history_mod.PERIODS:
                    return self._json(400, {"ok": False, "error": "unknown period",
                                            "allowed": list(history_mod.PERIODS)})
                return self._json(200, self.server.cockpit.history(query.get("pipeline") or None, period))
            if url.path == "/api/item":
                code, data = self.server.cockpit.item(query.get("hub_key", ""), query.get("id", ""))
                return self._json(code, data)
        except Exception as exc:  # noqa: BLE001 - one failing request must not stop the server
            self.log_error("%s %s failed: %s", self.command, url.path, exc)
            return self._json(500, {"ok": False, "error": f"internal error: {exc}"})
        return self._json(404, {"ok": False, "error": "not found"})

    do_HEAD = do_GET

    def _drain(self, length: int | None) -> None:
        """Read an unread body before a refusal: closing a socket with unread data makes Windows reset the connection,
        and the client would lose the answer. A body without a length or beyond DRAIN_MAX ends the connection."""
        if length is None or length > DRAIN_MAX:
            self.close_connection = True
            return
        while length > 0:
            chunk = self.rfile.read(min(length, 65536))
            if not chunk:
                break
            length -= len(chunk)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            length = None
        if length is not None and length < 0:
            length = None

        def refuse(code: int, error: str):
            self._drain(length)
            return self._json(code, {"ok": False, "error": error})
        if not self._host_ok():
            return refuse(403, "forbidden host")
        origin = self.headers.get("Origin")
        if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in self._own()}:
            return refuse(403, "forbidden origin")
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return refuse(415, "content type must be application/json")
        if length is None:
            return refuse(411, "Content-Length is required")
        if length > MAX_REQUEST:
            return refuse(413, f"the body must be at most {MAX_REQUEST} bytes")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            return self._json(400, {"ok": False, "error": "the body must be a JSON object"})
        path = urlsplit(self.path).path
        try:
            if path == "/api/action":
                return self._json(*self.server.cockpit.act(data))
            if path == "/api/forget":
                return self._json(*self.server.cockpit.forget(data))
        except Exception as exc:  # noqa: BLE001
            self.log_error("%s %s failed: %s", self.command, path, exc)
            return self._json(500, {"ok": False, "error": f"internal error: {exc}"})
        return self._json(404, {"ok": False, "error": "not found"})


# ---- the command (design D1, D2)

def health(port: int, timeout: float = HEALTH_TIMEOUT_S) -> dict | None:
    """The answer of a cockpit on `port`, or None when something else (or nothing) is there."""
    conn = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        conn.request("GET", "/api/health", headers={"Host": f"{HOST}:{port}"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8")) if resp.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        conn.close()
    return data if isinstance(data, dict) and data.get("app") == APP else None


def serve(server: Server) -> None:
    """Run until Ctrl+C; a test replaces it."""
    server.serve_forever()


def open_browser(url: str) -> None:
    webbrowser.open(url)


def command(port: int | None = None, configs=(), no_browser: bool = False, forget: str | None = None,
            out=None, err=None) -> int:
    """`python -m radark cockpit`. Exit codes: 130 after Ctrl+C; 0 when a cockpit already runs on the port, or after
    `--forget`; 1 for `--forget` of a path that is not registered; 2 for a wrong or busy port."""
    out = out or (lambda text: print(text, flush=True))  # the start line shows at once, also in a log file
    err = err or (lambda text: print(text, file=sys.stderr, flush=True))
    directory = machine_mod.machine_dir()
    if forget is not None:
        path = os.path.abspath(forget)
        try:
            gone = machine_mod.Registry(directory).forget(path)
        except machine_mod.MachineError as exc:
            err(f"Cockpit: {exc}")
            return 2
        if not gone:
            err(f"{path} is not in the pipeline registry ({directory / 'pipelines.json'}).")
            return 1
        out(f"Forgot {path} (the pipeline registry only; its hub is unchanged).")
        return 0
    if port is None:
        try:
            port = machine_mod.load_cockpit_port(directory)
        except machine_mod.MachineError as exc:
            err(f"Machine error: {exc}")
            return 2
    elif not 1 <= port <= 65535:
        err(f"--port must be an integer from 1 to 65535, not {port}.")
        return 2
    paths = [os.path.abspath(c) for c in configs]
    if paths:
        record_configs(directory, paths, out)
    url = f"http://{HOST}:{port}/"
    try:
        server = Server(port, Cockpit(directory, paths))
    except OSError:
        if health(port) is not None:
            out(f"Cockpit already running at {url}")
            if not no_browser:
                open_browser(url)
            return 0
        err(f"Port {port} is busy; use --port N or set [cockpit] port in {directory / 'machine.toml'}.")
        return 2
    try:
        out(f"Cockpit running at {server.url} (Ctrl+C to stop)")
        if not no_browser:
            open_browser(server.url)
        serve(server)
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


def record_configs(directory: Path, paths: list[str], out) -> None:
    """Each `--config` of the cockpit goes into the registry (design D3); a problem is one line."""
    try:
        machine_mod.prepare_dir(directory)
        registry = machine_mod.Registry(directory)
        for path in paths:
            try:
                name = config_mod.load(path).pipeline_name()
            except config_mod.ConfigError:
                name = Path(path).parent.name
            problem = registry.record(path, name)
            if problem:
                out(f"! {problem}")
    except machine_mod.MachineError as exc:
        out(f"! {exc}; the cockpit shows the --config pipelines anyway")
