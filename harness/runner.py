"""Launch one `claude -p` session, save its stream and classify the outcome (design D2, D3, D4, T1, T2)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import clock
from .config import Config
from .prompts import STANDING_RULE
from .state import now_ts, write_json_atomic

HOOKS_DIR = Path(__file__).resolve().parent / "hooks"
OUR_TOOLS = {"AskUserQuestion"}  # denied by our own hook; recorded through markers, not as owner denials
RECENT_EVENTS = 40  # events kept for the limit check's digest (check-session-at-time-limit D3)
TEXT_CHARS, TOOL_CHARS = 300, 150


@dataclass
class SessionResult:
    run_id: str
    session_id: str
    team: str
    handover: str | None
    phase: str
    started: str
    ended: str = ""
    duration_s: float = 0.0
    exit_code: int | None = None
    outcome: str = "error"
    result_text: str = ""
    is_error: bool = False
    has_result: bool = False
    denials: list = field(default_factory=list)
    markers: list = field(default_factory=list)
    hooks_loaded: bool = False
    timed_out: bool = False
    timeout_reason: str | None = None  # idle_timeout | max_time (design T2)
    killed: bool = False
    interrupt_cause: str | None = None  # sleep | owner | dispatcher_stopped: outcome `interrupted` (sleep-aware D4)
    rate_limited: bool = False
    structured: dict | None = None
    assistant_text: str = ""
    stream_path: str = ""
    stderr: str = ""
    progress_sources: list | None = None  # set by the dispatcher: hub | commits | tasks (design T3)
    progress_ignored: str | None = None  # "change_notes": commits found but only inside the change (no-loop N2)
    usage: dict = field(default_factory=dict)  # window -> {utilization, resets_at, status} from rate_limit_event
    # for the limit check's digest (check-session-at-time-limit D3): awake times of the session's start and of its
    # newest event other than a heartbeat, (awake time, kind, text) of recent events, (tool, seconds, seen at)
    awake_start: float = 0.0
    last_event_at: float = 0.0
    recent: deque = field(default_factory=lambda: deque(maxlen=RECENT_EVENTS))
    running_tool: tuple | None = None
    limit_reason: str | None = None  # the product team's reason when its limit check judged the session hung

    def markers_of(self, event: str) -> list[dict]:
        return [m for m in self.markers if m.get("event") == event]


def write_session_settings(cfg: Config) -> Path:
    """Hooks in exec form (no shell), passed with --settings so team repositories stay untouched."""
    def entry(script: str) -> dict:
        return {"type": "command", "command": sys.executable, "args": [str(HOOKS_DIR / script)], "timeout": 60}

    settings = {"hooks": {
        "SessionStart": [{"hooks": [entry("session_start.py")]}],
        "PreToolUse": [{"matcher": "AskUserQuestion", "hooks": [entry("ask_user_question.py")]}],
        "Stop": [{"hooks": [entry("stop.py")]}],
        "StopFailure": [{"hooks": [entry("stop_failure.py")]}],
    }}
    write_json_atomic(cfg.run_dir / "hook-config.json", {
        "default_answer": cfg.default_answer,
        "escalation_keywords": cfg.escalation_keywords,
        "triage_teams": cfg.triage.teams if cfg.triage else [],
    })
    path = cfg.run_dir / "session-settings.json"
    write_json_atomic(path, settings)
    return path


def session_env(base: dict, cfg: Config, team: str, handover: str | None, session_id: str, run_id: str,
                phase: str = "") -> dict:
    env = dict(base)
    env.pop("ANTHROPIC_API_KEY", None)  # a stray key would switch the agents to API billing
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.update({
        "HARNESS_RUN_DIR": str(cfg.run_dir),
        "HARNESS_RUN_ID": run_id,
        "HARNESS_SESSION": session_id,
        "HARNESS_TEAM": team,
        "HARNESS_HANDOVER": handover or "",
        "HARNESS_PHASE": phase,
        "HO_HUB": str(cfg.hub),
        "HO_TEAM": team,
    })
    return env


def classify(r: SessionResult) -> str:
    if r.interrupt_cause:  # not the session's fault: resumed, never an error or no progress (sleep-aware D4)
        return "interrupted"
    events = {m.get("event") for m in r.markers}
    if "usage_limit" in events or r.rate_limited:
        return "usage_limit"
    if "escalation" in events or r.denials:
        return "waiting_for_owner"
    if r.timed_out or r.killed or r.exit_code != 0 or not r.has_result or r.is_error or not r.hooks_loaded:
        return "error"
    if "question" in events:
        return "question"
    return "finished"


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        kill_pid_tree(proc.pid)
    else:
        proc.kill()


def kill_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


class Runner:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.kill_requested = False
        self.clock = clock.awake  # session limits count awake time only (sleep-aware D1)
        (cfg.run_dir / "sessions").mkdir(parents=True, exist_ok=True)
        (cfg.run_dir / "markers").mkdir(parents=True, exist_ok=True)
        self.settings_path = write_session_settings(cfg)

    def command(self, prompt: str, session_id: str, resume: bool = False, tools: list[str] | None = None,
                json_schema: dict | None = None) -> list[str]:
        cmd = list(self.cfg.claude) + ["-p", prompt]
        cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
        cmd += [
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", self.cfg.permission_mode,
            "--permission-prompts", "none",
            "--settings", str(self.settings_path),
            "--append-system-prompt", STANDING_RULE,
        ]
        if tools is not None:
            cmd += ["--tools", ",".join(tools), "--allowedTools", ",".join(tools)]
        if json_schema is not None:
            cmd += ["--json-schema", json.dumps(json_schema)]
        return cmd + list(self.cfg.extra_args)

    def kill(self) -> None:
        self.kill_requested = True
        if self.proc is not None:
            kill_tree(self.proc)

    def run(self, team: str, prompt: str, *, phase: str, handover: str | None = None,
            resume: str | None = None, tools: list[str] | None = None, json_schema: dict | None = None,
            timeout_s: float | None = None, idle_s: float | None = None,
            session_id: str | None = None, on_usage=None, on_start=None, sleep_check=None,
            grace_s: float | None = None, on_deadline=None, on_deadline_abort=None) -> SessionResult:
        """`on_usage(window, utilization, resets_at)` is called from the stream thread for every usage reading;
        `on_start(session_id, run_id, pid)` right after the process starts; `sleep_check()` (a `Sleep` or None)
        every loop iteration: after a sleep a session silent for `grace_s` is ended as interrupted (design D3).
        `on_deadline(result, elapsed_s)` runs in a thread when the maximum duration is reached: seconds move the
        deadline, None ends the session by `max_time`; while it runs, `max_time` waits. `on_deadline_abort()` is
        called when the session ends while it runs (check-session-at-time-limit D1)."""
        session_id = resume or session_id or str(uuid.uuid4())
        run_id = session_id if not resume else f"{session_id}-r{int(time.time())}"
        repo = self.cfg.team(team).repo
        r = SessionResult(run_id=run_id, session_id=session_id, team=team, handover=handover,
                          phase=phase, started=now_ts())
        stream_path = self.cfg.run_dir / "sessions" / f"{run_id}.jsonl"
        r.stream_path = str(stream_path)
        cmd = self.command(prompt, session_id, resume=bool(resume), tools=tools, json_schema=json_schema)
        env = session_env(os.environ, self.cfg, team, handover, session_id, run_id, phase)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0  # our Ctrl+C is handled by us
        now = self.clock
        t0 = now()
        r.awake_start = r.last_event_at = t0
        self.kill_requested = False
        self.proc = subprocess.Popen(
            cmd, cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=flags,
        )
        if on_start is not None:
            on_start(session_id, run_id, self.proc.pid)
        stderr_chunks: list[bytes] = []
        err_thread = threading.Thread(target=lambda: stderr_chunks.append(self.proc.stderr.read()), daemon=True)
        err_thread.start()
        # awake time of the newest stream event (heartbeats excluded, design T1) and of the newest line of any kind
        last_event = [t0, t0]
        out_thread = threading.Thread(target=self._pump, args=(self.proc, stream_path, r, last_event, on_usage, now),
                                      daemon=True)
        out_thread.start()
        max_s = timeout_s if timeout_s is not None else self.cfg.session_max_minutes * 60
        idle_s = idle_s if idle_s is not None else self.cfg.session_idle_minutes * 60
        grace_s = grace_s if grace_s is not None else self.cfg.wake_grace_minutes * 60
        woke = None  # awake time of a wake seen during this session, until the session shows a sign of life
        check, answer, expired = None, [], False  # thread of a pending deadline check and its answer
        while self.proc.poll() is None:
            if sleep_check is not None and sleep_check():
                woke = now()
            t = now()
            if woke is not None and last_event[1] > woke:  # a line after the wake: it goes on as before
                woke = None
            if check is not None and not check.is_alive():
                check = None
                if answer and answer[0]:
                    max_s += answer[0]
                else:
                    expired = True
            over = t - t0 > max_s
            if (over and on_deadline is not None and check is None and not expired and r.timeout_reason is None
                    and r.interrupt_cause is None):
                answer = []
                check = threading.Thread(target=_ask_deadline, args=(on_deadline, r, t - t0, answer), daemon=True)
                check.start()
            reason = ("max_time" if over and check is None else
                      "idle_timeout" if t - last_event[0] > idle_s else None)
            if reason and r.timeout_reason is None and r.interrupt_cause is None:
                r.timed_out, r.timeout_reason = True, reason
                kill_tree(self.proc)
            elif woke is not None and t - woke > grace_s and r.timeout_reason is None and r.interrupt_cause is None:
                r.interrupt_cause = "sleep"
                kill_tree(self.proc)
            time.sleep(0.2)
        if check is not None and check.is_alive():  # the session ended first: its check is moot
            if on_deadline_abort is not None:
                try:
                    on_deadline_abort()
                except Exception:
                    pass
            check.join(10)
        out_thread.join(10)
        err_thread.join(10)
        r.killed = self.kill_requested
        if r.killed and r.timeout_reason is None and r.interrupt_cause is None:
            r.interrupt_cause = "owner"  # the owner's second Ctrl+C (design D4)
        r.exit_code = self.proc.returncode
        r.stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")[-4000:]
        self.proc = None
        r.ended = now_ts()
        r.duration_s = round(now() - t0, 1)
        r.markers = read_markers(self.cfg.run_dir, run_id)
        r.hooks_loaded = any(m.get("event") == "hooks_loaded" for m in r.markers)
        r.outcome = classify(r)
        return r

    @staticmethod
    def _pump(proc: subprocess.Popen, path: Path, r: SessionResult, last_event: list[float], on_usage=None,
              now=clock.awake) -> None:
        texts: list[str] = []
        with open(path, "wb") as fh:
            for raw in proc.stdout:
                fh.write(raw)
                fh.flush()
                last_event[1] = now()
                try:
                    ev = json.loads(raw.decode("utf-8", errors="replace"))
                except ValueError:
                    last_event[0] = last_event[1]
                    continue
                if not is_heartbeat(ev):  # a hung tool call keeps sending heartbeats (design T1)
                    last_event[0] = r.last_event_at = last_event[1]
                apply_event(ev, r, texts, on_usage, at=last_event[1])
        r.assistant_text = "\n\n".join(texts)


def _ask_deadline(on_deadline, r: SessionResult, elapsed: float, answer: list) -> None:
    try:
        answer.append(on_deadline(r, elapsed))
    except Exception:  # a failing check ends the session as without it
        answer.append(None)


def _short(text: str, size: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= size else text[:size - 3].rstrip() + "..."


def tool_text(block: dict) -> str:
    """`Bash: pnpm e2e`: a tool call's name and the telling part of its input (check-session-at-time-limit D3)."""
    name, data = block.get("name") or "?", block.get("input")
    if isinstance(data, dict):
        part = next((data[k] for k in ("command", "file_path", "pattern", "path", "url", "description", "prompt")
                     if isinstance(data.get(k), str) and data[k].strip()), None)
        if part is None:
            part = json.dumps(data, ensure_ascii=False) if data else ""
    else:
        part = ""
    return _short(f"{name}: {part}" if part else name, TOOL_CHARS)


def tool_result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return _short(content or "", TEXT_CHARS)


def is_heartbeat(ev: dict) -> bool:
    """`tool_progress` heartbeats are sent every 30 s while a tool runs, whether or not it is making progress."""
    return ev.get("type") == "tool_progress" and bool(ev.get("heartbeat"))


def apply_event(ev: dict, r: SessionResult, texts: list[str], on_usage=None, at: float = 0.0) -> None:
    """`at`: awake time the event arrived, for the ring of recent events (check-session-at-time-limit D3)."""
    kind = ev.get("type")
    if kind == "tool_progress":
        if ev.get("heartbeat"):
            r.running_tool = (ev.get("tool_name") or "?", _number(ev.get("elapsed_time_seconds")) or 0.0, at)
    elif kind == "rate_limit_event":
        for window, reading in parse_usage(ev).items():  # later events overwrite earlier ones (design D1)
            r.usage[window] = reading
            if on_usage is not None and reading["utilization"] is not None:
                try:
                    on_usage(window, reading["utilization"], reading["resets_at"])
                except Exception:  # the reading is advisory; it must never break the stream
                    pass
    elif kind == "assistant":
        r.running_tool = None
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])
                r.recent.append((at, "text", _short(block["text"], TEXT_CHARS)))
            elif isinstance(block, dict) and block.get("type") == "tool_use":
                r.recent.append((at, "tool", tool_text(block)))
    elif kind == "user":
        r.running_tool = None
        content = (ev.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                r.recent.append((at, "error", tool_result_text(block)))
    elif kind == "system" and ev.get("subtype") == "api_retry":
        if "rate" in json.dumps(ev).lower():
            r.rate_limited = True
    elif kind == "result":
        r.has_result = True
        r.is_error = bool(ev.get("is_error"))
        r.result_text = ev.get("result") or ""
        if ev.get("session_id"):
            r.session_id = ev["session_id"]
        r.denials = [d for d in ev.get("permission_denials") or [] if d.get("tool_name") not in OUR_TOOLS]
        if isinstance(ev.get("structured_output"), dict):
            r.structured = ev["structured_output"]


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_usage(ev: dict) -> dict:
    """{window: {utilization (0-1), resets_at (Unix s), status}} from a `rate_limit_event` (design D1).
    `unifiedWindows` first, else the top-level window; the top-level status belongs to `rateLimitType`.
    Malformed parts are skipped."""
    info = ev.get("rate_limit_info")
    if not isinstance(info, dict):
        return {}
    named = info.get("rateLimitType") if isinstance(info.get("rateLimitType"), str) else None
    windows = info.get("unifiedWindows")
    if not isinstance(windows, dict):
        windows = {named: info} if named else {}
    out = {}
    for name, w in windows.items():
        if not isinstance(name, str) or not isinstance(w, dict):
            continue
        utilization, resets = _number(w.get("utilization")), _number(w.get("resetsAt"))
        if utilization is None and resets is None:
            continue
        out[name] = {"utilization": utilization, "resets_at": resets, "status": None}
    if named in out and isinstance(info.get("status"), str):
        out[named]["status"] = info["status"]
    return out


def read_markers(run_dir: Path, run_id: str) -> list[dict]:
    path = Path(run_dir) / "markers" / f"{run_id}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
