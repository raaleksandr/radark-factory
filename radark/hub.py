"""Wrapper around the `ho` CLI. The only hub writes are escalation handovers to the owner (`new`, `close` of
those) and `sync`; team handovers are never changed."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import clock
from .runner import kill_tree

TIMEOUT_S = 120  # awake time per hub command (harness-survive-sleep D3)
SLICE_S = 5  # one wait; timing out of a slice only means "not yet"
READS = ("inbox", "show", "list")  # re-run once when killed by a sleep (D4); writes never are


class HoError(Exception):
    exit_code = 1

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


class HoUsageError(HoError):
    exit_code = 1


class HoNotFound(HoError):
    exit_code = 2


class HoLifecycleError(HoError):
    exit_code = 3


class HoIntegrityError(HoError):
    exit_code = 4


class HoTimeout(HoError):
    """No answer within the awake-time limit; the process tree was killed (D5)."""


SUPPORTED_HO_CONTRACTS = (1,)  # JSON contract versions of `ho` this engine reads (ho-contract-check D2)
VERSION_TIMEOUT_S = 60  # time limit of the start probe `ho --version --json`


HUB_LOCK = "hub-lock"  # `features` entry of an ho that serialises hub writes and sync (parallel-sessions D6)


@dataclass(frozen=True)
class HoVersion:
    version: str
    contract: int
    features: tuple = ()

    def line(self) -> str:
        return f"{self.version} (contract {self.contract})"

    @property
    def hub_lock(self) -> bool:
        return HUB_LOCK in self.features


def hub_lock_message(ho: HoVersion, sessions: int) -> str:
    """Why an ho without the hub lock cannot run parallel sessions (parallel-sessions D6)."""
    return (f"ho {ho.line()} does not report the hub lock (no \"{HUB_LOCK}\" in the features of "
            f"'ho --version --json'); parallel_sessions = {sessions} needs it, so that several sessions and the "
            "dispatcher can write to the hub at the same time. Install a radark-handover release with the hub lock, "
            "or set [loop] parallel_sessions = 1.")


def contracts_text(supported=SUPPORTED_HO_CONTRACTS) -> str:
    return " or ".join(str(c) for c in supported)


def check_ho(cmd: list[str], hub: Path, timeout: float = VERSION_TIMEOUT_S,
             supported=SUPPORTED_HO_CONTRACTS, config_file: str = "the configuration file") -> HoVersion | str:
    """Probe `ho --version --json` once at start (ho-contract-check D1-D3). Returns the found version, or the one
    message that stops the dispatcher: missing, no answer, too old (no usable --version) or unsupported contract."""
    shown, needed = " ".join(cmd), contracts_text(supported)
    env = dict(os.environ, HO_HUB=str(hub))
    env.pop("HO_TEAM", None)
    try:
        proc = subprocess.run(list(cmd) + ["--version", "--json"], capture_output=True, env=env, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return (f"ho '{shown}' did not answer '--version --json' within {timeout:g} s. "
                f"This radark-factory needs an ho with JSON contract {needed}.")
    except OSError as exc:
        return (f"ho not found: cannot start '{shown}' ({exc}). This radark-factory needs an ho with JSON contract "
                f"{needed}: install radark-handover with that contract, or fix 'ho' in {config_file}.")
    data = _json(proc.stdout.decode("utf-8", errors="replace"))
    version = data.get("version") if isinstance(data, dict) else None
    contract = data.get("contract", data.get("schema_version")) if isinstance(data, dict) else None
    if (proc.returncode != 0 or not isinstance(version, str) or not version
            or not isinstance(contract, int) or isinstance(contract, bool)):
        how = f"exit {proc.returncode}" if proc.returncode != 0 else "no version in its answer"
        return (f"ho '{shown}' has no --version ({how}): it is older than this radark-factory supports. "
                f"Found: no version; needed: JSON contract {needed}. "
                f"Install a radark-handover release that has 'ho --version' with contract {needed}.")
    if contract not in supported:
        return (f"ho '{shown}' is version {version} with JSON contract {contract}; this radark-factory needs "
                f"contract {needed}. Install a radark-handover release with contract {needed}, "
                f"or a radark-factory release that supports contract {contract}.")
    features = data.get("features")
    features = tuple(f for f in features if isinstance(f, str)) if isinstance(features, list) else ()
    return HoVersion(version, contract, features)


_BY_EXIT = {1: HoUsageError, 2: HoNotFound, 3: HoLifecycleError, 4: HoIntegrityError}


def _json(stdout: str):
    try:
        return json.loads(stdout) if stdout.strip() else {}
    except ValueError:
        return {}


class Hub:
    def __init__(self, ho: list[str], hub: Path, *, awake=clock.awake, wall=time.time, timeout: float = TIMEOUT_S,
                 slice_s: float = SLICE_S):
        self.ho = list(ho)
        self.hub = Path(hub)
        self.awake, self.wall, self.timeout, self.slice_s = awake, wall, timeout, slice_s

    def _run(self, args: list[str], team: str | None = None, stdin: str | None = None) -> dict:
        env = dict(os.environ, HO_HUB=str(self.hub))
        env.pop("HO_TEAM", None)
        if team:
            env["HO_TEAM"] = team
        code, out, err, slept = self._call(args, env, stdin)
        stdout = out.decode("utf-8", errors="replace")
        data = _json(stdout)
        if slept and args[0] in READS and (code is None or (code != 0 and not data)):
            # killed or left hanging by a sleep: a read is safe to run once more (D4)
            code, out, err, slept = self._call(args, env, stdin)
            stdout = out.decode("utf-8", errors="replace")
            data = _json(stdout)
        if code is None:
            raise HoTimeout(f"no answer within {self.timeout:g} s")
        if code != 0:
            e = data.get("error", {}) if isinstance(data, dict) else {}
            message = (e.get("message") or err.decode("utf-8", errors="replace").strip()
                       or f"ho {' '.join(args)} failed")
            raise _BY_EXIT.get(code, HoError)(message, e.get("code", ""))
        if not isinstance(data, dict) or not data:
            raise HoError(f"ho {' '.join(args)} printed no JSON: {stdout[:200]!r}")
        return data

    def _call(self, args: list[str], env: dict, stdin: str | None) -> tuple[int | None, bytes, bytes, bool]:
        """Run `ho` once, waiting in slices until `timeout` seconds of awake time have passed, so a sleep in the
        middle adds no time (D3). Returns (exit code, or None after a timeout kill; stdout; stderr; whether the
        computer slept during the call)."""
        wall0, awake0 = self.wall(), self.awake()
        proc = subprocess.Popen(  # bytes: text mode would turn the body's LF into CRLF on Windows
            self.ho + args + ["--json"], stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        data = stdin.encode("utf-8") if stdin is not None else None
        code = None
        while True:
            try:
                out, err = proc.communicate(data, timeout=self.slice_s)
                code = proc.returncode
                break
            except subprocess.TimeoutExpired:
                data = None  # sent with the first wait only
                if self.awake() - awake0 >= self.timeout:
                    kill_tree(proc)
                    try:
                        out, err = proc.communicate(timeout=self.slice_s)
                    except subprocess.TimeoutExpired:
                        out, err = b"", b""
                    break
        gap = (self.wall() - wall0) - (self.awake() - awake0)
        return code, out or b"", err or b"", gap >= clock.SLEEP_MIN_S


    def inbox(self, team: str) -> dict:
        return self._run(["inbox"], team=team)

    def show(self, handover_id: str, team: str | None = None) -> dict:
        return self._run(["show", handover_id], team=team)

    def sent_by(self, team: str) -> list[dict]:
        """Handovers created by `team` (used to see new handovers after a session)."""
        return self._run(["list", "--from", team, "--status", "all"]).get("items", [])

    def teams(self) -> list[str]:
        return [t["id"] for t in self._run(["teams"]).get("teams", [])]

    # ---- writes (escalation handovers only, design E7)

    def new(self, team: str, to: str, title: str, body: str, *, expects: str = "response",
            tags: list[str] = (), refs: list[str] = (), auto_close: bool = True) -> dict:
        """Create a handover from `team`; the body goes through stdin. Returns the summary (with `id`)."""
        args = ["new", "--to", to, "--expects", expects, "--title", title, "--body", "-"]
        for tag in tags:
            args += ["--tag", tag]
        for ref in refs:
            args += ["--ref", ref]
        if auto_close:
            args.append("--auto-close")
        return self._run(args, team=team, stdin=body)

    def close(self, handover_id: str, team: str, message: str, force: bool = False) -> dict:
        return self._run(["close", handover_id, "-m", message] + (["--force"] if force else []), team=team)

    def sync(self) -> dict:
        return self._run(["sync"])
