"""The owner cockpit (change owner-cockpit) with fake `ho`, a temporary machine directory and the server on a free
port in a thread; requests through `http.client`. No test opens a browser."""
import http.client
import json
import os
import re
import socket
import sys
import threading
from pathlib import Path

import pytest

from radark import cockpit
from radark.__main__ import main
from radark.machine import Registry
from radark.tests.conftest import FAKES, toml_path, write_config

WRITES = {"new", "respond", "done", "ack", "decline", "close", "comment", "return", "sync", "seen"}
ALLOWED = {"response": ["ack", "respond", "decline", "comment", "seen"],
           "done": ["ack", "done", "decline", "comment", "seen"],
           "ack": ["ack", "decline", "comment", "seen"]}
P1, P2, P3 = "HO-20261110-aaaa", "HO-20261110-bbbb", "HO-20261110-cccc"
D1 = "HO-20261109-dddd"


def ho_item(hid, title="Question", sender="product", expects="response", state="pending", status="open", tags=(),
            last="2026-11-10T10:00:00.000Z", allowed=None, to="owner", body=None):
    done = state not in ("pending", "acknowledged", "returned") or status == "closed"
    return {"id": hid, "title": title, "from": sender, "to": [to], "expects": expects, "status": status,
            "recipients": {to: state}, "tags": list(tags), "created": "2026-11-09T08:00:00.000Z",
            "last_activity": last, "auto_close": False, "body": body if body is not None else f"Body of {title}.",
            "events": [], "allowed_actions": allowed if allowed is not None else
            (["comment", "seen"] if done else ALLOWED[expects])}


def hub_data(*items) -> dict:
    return {f"show:{h['id']}": h for h in items}


def named(env, name: str) -> Path:
    env.config_path.write_text(f'name = "{name}"\n' + env.config_path.read_text(encoding="utf-8"), encoding="utf-8")
    return env.config_path


def second_pipeline(env, name="beta", same_hub=True, data: dict | None = None) -> Path:
    """Another pipeline: the same hub as `env`, or its own hub read by a fake `ho` with its own data file."""
    root = env.root / name
    root.mkdir()
    path = write_config(root)
    text = f'name = "{name}"\n' + path.read_text(encoding="utf-8")
    if same_hub:
        text = text.replace(toml_path(root / "hub"), toml_path(env.root / "hub"))
    else:
        own = root / "ho.json"
        own.write_text(json.dumps(data or {}))
        wrapper = root / "ho_wrapper.py"
        wrapper.write_text("import os, runpy, sys\nos.environ['FAKE_HO_DATA'] = sys.argv.pop(1)\n"
                           f"runpy.run_path({str(FAKES / 'fake_ho.py')!r}, run_name='__main__')\n")
        text = text.replace(f"ho = [{toml_path(sys.executable)}, {toml_path(FAKES / 'fake_ho.py')}]",
                            f"ho = [{toml_path(sys.executable)}, {toml_path(wrapper)}, {toml_path(own)}]")
    path.write_text(text, encoding="utf-8")
    return path


def calls_of(data_file: Path) -> list[dict]:
    p = Path(str(data_file) + ".calls")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


class Running:
    def __init__(self, server):
        self.server = server
        self.port = server.port

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        hdrs = dict(headers or {})
        payload = raw
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        try:
            conn.request(method, path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, dict(resp.getheaders()), data
        finally:
            conn.close()

    def json(self, method, path, body=None, headers=None, raw=None):
        status, hdrs, data = self.request(method, path, body, headers, raw)
        return status, json.loads(data.decode("utf-8"))

    def items(self) -> dict:
        status, data = self.json("GET", "/api/items")
        assert status == 200
        return data

    def act(self, hub_key, hid, action, text=""):
        return self.json("POST", "/api/action", {"hub_key": hub_key, "id": hid, "action": action, "text": text})


@pytest.fixture
def start(machine_home):
    servers = []

    def go(configs=()):
        server = cockpit.Server(0, cockpit.Cockpit(machine_home, configs))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return Running(server)
    yield go
    for s in servers:
        s.shutdown()
        s.server_close()


def ids(items):
    return [i["id"] for i in items]


# ---- server and request checks (task 2.1)

def test_health(env, start):
    status, data = start().json("GET", "/api/health")
    assert status == 200 and data["app"] == "radark-cockpit" and data["pid"] == os.getpid() and "version" in data


@pytest.mark.parametrize("host", ["attacker.invalid:{port}", "127.0.0.1:1", "localhost", "example.invalid"])
def test_foreign_host_refused_on_get_and_post(env, start, host):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha")])
    h = {"Host": host.format(port=c.port)}
    for path in ("/", "/api/health", "/api/items"):
        assert c.request("GET", path, headers=h)[0] == 403
    status, _ = c.json("POST", "/api/action", {"hub_key": "x", "id": P1, "action": "ack"}, headers=h)
    assert status == 403 and env.ho_calls() == []


def test_localhost_host_accepted(env, start):
    c = start()
    assert c.request("GET", "/api/health", headers={"Host": f"LOCALHOST:{c.port}"})[0] == 200


def test_foreign_origin_refused_and_no_ho_call(env, start):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    before = len(env.ho_calls())
    status, _ = c.json("POST", "/api/action", {"hub_key": key, "id": P1, "action": "ack"},
                       headers={"Origin": "http://example.invalid"})
    assert status == 403 and len(env.ho_calls()) == before
    status, _ = c.json("POST", "/api/action", {"hub_key": key, "id": P1, "action": "ack"},
                       headers={"Origin": f"http://localhost:{c.port}"})
    assert status == 200


@pytest.mark.parametrize("ctype", [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_wrong_content_type_refused(env, start, ctype):
    c = start()
    headers = {"Content-Type": ctype} if ctype else {}
    status, _ = c.json("POST", "/api/forget", raw=b'{"config": "x"}', headers=headers)
    assert status == 415


def test_body_over_64_kib_refused(env, start):
    c = start()
    raw = json.dumps({"config": "x" * (65 * 1024)}).encode()
    status, _ = c.json("POST", "/api/forget", raw=raw, headers={"Content-Type": "application/json"})
    assert status == 413


def test_non_object_body_refused(env, start):
    c = start()
    assert c.json("POST", "/api/forget", raw=b"[1]", headers={"Content-Type": "application/json"})[0] == 400


def test_headers_and_no_cors_in_any_answer(env, start):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha")])
    answers = [c.request("GET", p) for p in ("/", "/api/health", "/api/items", "/nothing")]
    answers.append(c.request("POST", "/api/forget", body={"config": "x"}))
    answers.append(c.request("OPTIONS", "/api/action", headers={"Origin": "http://example.invalid",
                                                               "Access-Control-Request-Method": "POST"}))
    for status, headers, _ in answers:
        assert not any(k.lower().startswith("access-control-") for k in headers), headers
    for status, headers, _ in answers[:-1]:
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
        assert headers["Referrer-Policy"] == "no-referrer"


def test_get_never_calls_a_write_command(env, start):
    env.set_hub(hub_data(ho_item(P1), ho_item(D1, state="answered", status="resolved")))
    c = start([named(env, "alpha")])
    data = c.items()
    for path in ("/", "/api/health", f"/api/item?hub_key={data['hubs'][0]['hub_key']}&id={P1}"):
        c.request("GET", path)
    assert env.ho_calls() and not [x for x in env.ho_calls() if x["args"][0] in WRITES]


# ---- data gathering (task 2.2)

def test_pending_and_done_split_newest_first_with_names(env, start):
    env.set_hub(hub_data(
        ho_item(P1, "Escalated question", tags=["escalation"], last="2026-11-10T10:00:00.000Z"),
        ho_item(P2, "Later request", expects="done", state="acknowledged", last="2026-11-10T11:00:00.000Z"),
        ho_item(P3, "Returned", expects="done", state="returned", last="2026-11-10T09:00:00.000Z"),
        ho_item(D1, "Resolved request", state="answered", status="resolved", last="2026-11-09T10:00:00.000Z"),
        ho_item("HO-20261109-eeee", "Acked note", expects="ack", state="acknowledged", status="resolved"),
        ho_item("HO-20261109-ffff", "Closed", state="pending", status="closed"),
        ho_item("HO-20261109-gggg", "To someone else", to="app"),
    ))
    data = start([named(env, "alpha")]).items()
    assert ids(data["pending"]) == [P2, P1, P3]
    assert set(ids(data["done"])) == {D1, "HO-20261109-eeee", "HO-20261109-ffff"}
    esc = data["pending"][1]
    assert esc["escalation"] is True and data["pending"][0]["escalation"] is False
    assert esc["pipelines"] == ["alpha"] and esc["from"] == "product" and esc["expects"] == "response"
    assert esc["created"] and esc["last_activity"] and esc["title"] == "Escalated question"
    assert esc["body"] == "Body of Escalated question." and esc["events"] == [] and esc["tags"] == ["escalation"]
    assert esc["allowed"] == ["respond", "ack", "decline"]  # owner actions of allowed_actions, in a fixed order
    assert all(i["allowed"] == [] for i in data["done"])
    assert data["note"].startswith("Answer here only if a short answer is enough")
    assert "hub" not in json.dumps(data["pipelines"]).replace("hub_key", "")  # no hub path to the page
    assert str(env.root / "hub") not in json.dumps(data)
    lists = [x for x in env.ho_calls() if x["args"][0] == "list"]
    assert lists == [{"args": ["list", "--to", "owner", "--status", "all"], "team": "owner",
                      "hub": str(env.root / "hub")}]
    assert {x["team"] for x in env.ho_calls() if x["args"][0] == "show"} == {"owner"}


def test_two_pipelines_on_one_hub_read_once_with_both_names(env, start):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha"), second_pipeline(env, "beta")])
    data = c.items()
    assert data["pending"][0]["pipelines"] == ["alpha", "beta"] and len(data["hubs"]) == 1
    assert len([x for x in env.ho_calls() if x["args"][0] == "list"]) == 1
    assert len([x for x in env.ho_calls() if x["args"][0] == "--version"]) == 1
    c.items()  # the contract check runs once per ho and hub, not per refresh
    assert len([x for x in env.ho_calls() if x["args"][0] == "--version"]) == 1


def test_registry_and_config_deduplicated(env, start, machine_home):
    path = named(env, "alpha")
    Registry(machine_home).record(path, "old-name")
    data = start([path]).items()
    assert [(p["name"], p["state"]) for p in data["pipelines"]] == [("alpha", "ok")]


def test_missing_configuration_listed_others_still_show(env, start, machine_home):
    env.set_hub(hub_data(ho_item(P1)))
    gone = env.root / "gone" / "radark.toml"
    Registry(machine_home).record(gone, "gamma")
    data = start([named(env, "alpha")]).items()
    states = {p["name"]: p for p in data["pipelines"]}
    assert states["gamma"]["state"] == "missing" and states["gamma"]["registered"] is True
    assert states["alpha"]["state"] == "ok" and ids(data["pending"]) == [P1]


def test_broken_configuration_listed_as_error(env, start):
    bad = env.root / "bad.toml"
    bad.write_text("hub = 'nowhere'\n")
    data = start([bad]).items()
    [entry] = data["pipelines"]
    assert entry["state"] == "error" and "hub.json" in entry["message"]


def test_failing_ho_for_one_pipeline_others_still_show(env, start):
    env.set_hub(hub_data(ho_item(P1)))
    other = second_pipeline(env, "beta", same_hub=False, data={
        "list": {"exit": 4, "error": {"code": "integrity", "message": "hub is damaged"}}})
    data = start([named(env, "alpha"), other]).items()
    errors = {tuple(h["pipelines"]): h["error"] for h in data["hubs"]}
    assert errors[("beta",)] == "hub is damaged" and errors[("alpha",)] is None
    assert ids(data["pending"]) == [P1] and data["pending"][0]["pipelines"] == ["alpha"]


def test_incompatible_ho_is_an_error_and_nothing_is_read(env, start):
    env.set_hub(hub_data(ho_item(P1)))
    other = second_pipeline(env, "beta", same_hub=False, data={"_version": {"exit": 2}})
    c = start([named(env, "alpha"), other])
    data = c.items()
    [err] = [h["error"] for h in data["hubs"] if h["pipelines"] == ["beta"]]
    assert err.startswith("ho incompatible") and "--version" in err
    own = env.root / "beta" / "ho.json"
    assert [x["args"][0] for x in calls_of(own)] == ["--version"]
    status, answer = c.act([h["hub_key"] for h in data["hubs"] if h["pipelines"] == ["beta"]][0], P1, "ack")
    assert status == 502 and [x["args"][0] for x in calls_of(own)] == ["--version", "--version"]


def test_done_items_beyond_the_newest_50_load_on_demand(env, start):
    old = [ho_item(f"HO-20261101-{i:04d}", f"Old {i}", state="answered", status="resolved",
                   last=f"2026-11-01T10:{i:02d}:00.000Z") for i in range(52)]
    env.set_hub(hub_data(*old))
    c = start([named(env, "alpha")])
    data = c.items()
    assert len(data["done"]) == 52
    partial = [i for i in data["done"] if i["partial"]]
    assert ids(partial) == ["HO-20261101-0001", "HO-20261101-0000"] and partial[0]["body"] is None
    assert len([x for x in env.ho_calls() if x["args"][0] == "show"]) == 50
    status, one = c.json("GET", f"/api/item?hub_key={partial[0]['hub_key']}&id={partial[0]['id']}")
    assert status == 200 and one["item"]["body"] == "Body of Old 1." and one["item"]["partial"] is False
    assert c.json("GET", f"/api/item?hub_key=nope&id={P1}")[0] == 404


# ---- answers (task 2.3)

def owner_writes(env):
    return [x for x in env.ho_calls() if x["args"][0] in WRITES]


@pytest.mark.parametrize("action, expects, text, args", [
    ("respond", "response", "Use the plain variant.", ["respond", P1, "--body", "-"]),
    ("done", "done", "Placed the key.", ["done", P1, "--body", "-"]),
    ("done", "done", "", ["done", P1]),
    ("ack", "ack", "", ["ack", P1]),
    ("decline", "response", "Not now.", ["decline", P1, "--body", "-"]),
])
def test_each_answer_runs_ho_as_owner_then_sync(env, start, action, expects, text, args):
    env.set_hub(hub_data(ho_item(P1, expects=expects)))
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    status, data = c.act(key, P1, action, text)
    assert status == 200 and data["ok"] is True and data["warning"] is None and data["result"]["id"] == P1
    writes = owner_writes(env)
    assert [w["args"] for w in writes] == [args, ["sync"]]
    assert writes[0]["team"] == "owner" and writes[0].get("stdin") == (text or None)
    assert ids(c.items()["done"]) == [P1]


def test_not_allowed_action_is_refused_without_a_write(env, start):
    env.set_hub(hub_data(ho_item(P1, expects="done")))
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    data = json.loads(env.ho_data.read_text())
    data[f"show:{P1}"]["allowed_actions"] = ["comment", "seen"]  # answered in a console meanwhile
    env.set_hub(data)
    status, answer = c.act(key, P1, "done")
    assert status == 409 and answer["error"] == "not allowed now" and answer["allowed"] == []
    assert owner_writes(env) == []


@pytest.mark.parametrize("action", ["respond", "decline"])
def test_empty_text_refused(env, start, action):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    assert c.act(key, P1, action, "  \n")[0] == 400
    assert owner_writes(env) == []


@pytest.mark.parametrize("request_body", [
    {"action": "close", "id": P1}, {"action": "ack"}, {"action": "respond", "id": P1, "text": 5},
    {"action": "respond", "id": P1, "text": "x" * 20_001}])
def test_bad_action_requests_refused(env, start, request_body):
    env.set_hub(hub_data(ho_item(P1)))
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    status, _ = c.json("POST", "/api/action", {"hub_key": key, **request_body})
    assert status == 400 and owner_writes(env) == []


def test_ho_exit_3_is_409_with_hos_message(env, start):
    data = hub_data(ho_item(P1))
    data["decline"] = {"exit": 3, "error": {"code": "invalid_transition", "message": "Cannot 'decline' now."}}
    env.set_hub(data)
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    status, answer = c.act(key, P1, "decline", "No.")
    assert status == 409 and answer["error"] == "Cannot 'decline' now." and answer["code"] == "invalid_transition"
    assert [w["args"][0] for w in owner_writes(env)] == ["decline"]  # no sync after a failed write
    assert ids(c.items()["pending"]) == [P1]


def test_sync_failure_is_a_warning(env, start):
    data = hub_data(ho_item(P1))
    data["sync"] = {"exit": 1, "error": {"code": "git_error", "message": "no remote"}}
    env.set_hub(data)
    c = start([named(env, "alpha")])
    key = c.items()["hubs"][0]["hub_key"]
    status, answer = c.act(key, P1, "ack")
    assert status == 200 and answer["ok"] is True and "no remote" in answer["warning"]


def test_forget_from_the_page_changes_only_the_registry(env, start, machine_home):
    gone = env.root / "gone" / "radark.toml"
    Registry(machine_home).record(gone, "gamma")
    c = start([named(env, "alpha")])
    status, answer = c.json("POST", "/api/forget", {"config": str(gone)})
    assert status == 200 and answer["ok"] is True
    assert c.json("POST", "/api/forget", {"config": str(gone)})[0] == 404
    assert [p["name"] for p in c.items()["pipelines"]] == ["alpha"]
    assert owner_writes(env) == []


# ---- the page (task 3.1)

def page_source() -> str:
    return (Path(cockpit.__file__).parent / "cockpit_page.html").read_text(encoding="utf-8")


def test_page_served_self_contained(env, start):
    status, headers, body = start().request("GET", "/")
    html = body.decode("utf-8")
    assert status == 200 and headers["Content-Type"].startswith("text/html") and "radark cockpit" in html
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert not re.search(r"""(src|href)\s*=\s*["']?\s*(https?:)?//""", html)
    assert "@import" not in html and "url(" not in html
    assert not re.search(r"<link\b", html) and not re.search(r"<script[^>]+src", html)
    for tab in ("Owner", "History", "Now", "Refresh", "Pending", "Done"):
        assert tab in html
    assert cockpit.NOTE not in html  # the note comes from the API, as one source of truth


def test_page_escapes_before_markdown():
    src = page_source()
    md = src[src.index("function md("):]
    first = md[:md.index("\n", md.index("{")) + 200]
    assert "esc(src)" in first.splitlines()[1]  # the first statement escapes the whole text
    for value in re.findall(r"\.innerHTML\s*=\s*([^;]+);", src):
        assert value.strip().startswith("md("), value  # nothing else is put in as HTML
    esc = src[src.index("function esc("):src.index("function inline(")]
    for char, entity in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")):
        assert entity in esc
    assert "https?:\\/\\/" in src and 'rel="noopener noreferrer"' in src  # links to http(s) targets only


# ---- the command (task 2.4)

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def no_serve(monkeypatch):
    """`serve` returns at once and records the server's port; the browser call is recorded, never made."""
    seen = {"ports": [], "browser": []}
    monkeypatch.setattr(cockpit, "serve", lambda server: seen["ports"].append(server.port))
    monkeypatch.setattr(cockpit, "open_browser", lambda url: seen["browser"].append(url))
    return seen


def test_forget_command(env, machine_home, capsys, no_serve):
    gone = env.root / "gone" / "radark.toml"
    Registry(machine_home).record(gone, "gamma")
    assert main(["cockpit", "--forget", str(gone)]) == 0
    assert "Forgot" in capsys.readouterr().out and Registry(machine_home).entries() == []
    assert main(["cockpit", "--forget", str(gone)]) == 1
    assert "not in the pipeline registry" in capsys.readouterr().err
    assert no_serve["ports"] == []


def test_port_precedence(env, machine_home, capsys, no_serve):
    a, b = free_port(), free_port()
    (machine_home / "machine.toml").write_text(f"[cockpit]\nport = {a}\n")
    assert main(["cockpit", "--no-browser"]) == 0
    assert main(["cockpit", "--port", str(b), "--no-browser"]) == 0
    assert no_serve["ports"] == [a, b] and no_serve["browser"] == []
    out = capsys.readouterr().out
    assert f"Cockpit running at http://127.0.0.1:{a}/" in out and f"http://127.0.0.1:{b}/" in out


def test_default_port_and_browser(env, machine_home, no_serve, monkeypatch):
    port = free_port()
    monkeypatch.setattr(cockpit.machine_mod, "DEFAULT_COCKPIT_PORT", port)
    assert main(["cockpit"]) == 0
    assert no_serve["ports"] == [port] and no_serve["browser"] == [f"http://127.0.0.1:{port}/"]
    assert cockpit.machine_mod.load_cockpit_port(machine_home) == port


@pytest.mark.parametrize("setting, args", [("port = 0", []), ("port = 70000", []), ("", ["--port", "70000"]),
                                           ("", ["--port", "0"])])
def test_invalid_port_exit_2(env, machine_home, capsys, no_serve, setting, args):
    (machine_home / "machine.toml").write_text(f"[cockpit]\n{setting}\n")
    assert main(["cockpit", "--no-browser", *args]) == 2
    err = capsys.readouterr().err
    assert ("machine.toml" in err and "cockpit.port" in err) if setting else "--port" in err
    assert no_serve["ports"] == []


def test_invalid_cockpit_port_does_not_stop_dry_run(env, machine_home):
    (machine_home / "machine.toml").write_text("[cockpit]\nport = 0\n")
    assert main(["--config", str(env.config_path), "dry-run"]) == 0


def test_busy_port_by_a_cockpit_exits_0(env, start, capsys, no_serve):
    running = start()
    assert main(["cockpit", "--port", str(running.port)]) == 0
    assert f"Cockpit already running at http://127.0.0.1:{running.port}/" in capsys.readouterr().out
    assert no_serve["browser"] == [f"http://127.0.0.1:{running.port}/"] and no_serve["ports"] == []
    assert main(["cockpit", "--port", str(running.port), "--no-browser"]) == 0
    assert len(no_serve["browser"]) == 1


def test_busy_port_by_another_program_exits_2(env, capsys, no_serve):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert main(["cockpit", "--port", str(port), "--no-browser"]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and f"Port {port} is busy" in err[0] and "--port N" in err[0]
    assert "[cockpit] port" in err[0] and no_serve["ports"] == []


def test_config_option_recorded_and_shown(env, machine_home, no_serve, monkeypatch):
    path = named(env, "alpha")
    shown = []
    monkeypatch.setattr(cockpit, "serve", lambda server: shown.append(server.cockpit.pipelines()[0]))
    assert main(["--config", str(path), "cockpit", "--port", str(free_port()), "--no-browser"]) == 0
    [entry] = Registry(machine_home).entries()
    assert entry["name"] == "alpha" and entry["config"] == os.path.realpath(path)
    assert [(p["name"], p["state"]) for p in shown[0]] == [("alpha", "ok")]


def test_keyboard_interrupt_exits_130(env, monkeypatch, no_serve):
    def interrupted(server):
        raise KeyboardInterrupt
    monkeypatch.setattr(cockpit, "serve", interrupted)
    assert main(["cockpit", "--port", str(free_port()), "--no-browser"]) == 130


def test_npm_script():
    data = json.loads((Path(cockpit.__file__).parents[1] / "package.json").read_text(encoding="utf-8"))
    assert data["scripts"]["cockpit"] == "python -m radark cockpit"
