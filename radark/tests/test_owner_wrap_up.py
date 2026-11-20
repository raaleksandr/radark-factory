"""Wrap-up on demand with fake `ho` and `claude` (owner-wrap-up-on-demand, tasks 1-4).

A "long tool call" is a fake `PostToolUse` step that waits for a file the test creates; the test creates it only once
the dispatcher has logged the request, so the hook runs after the request like a real tool call that returns later.
Grace and `--within` limits are a few seconds of real time (as in test_until_strict.py)."""
import datetime as dt
import json
import os
import threading
import time
from pathlib import Path

import pytest

import radark.__main__ as hm
from radark import prompts
from radark.__main__ import Dispatcher, main, sym
from radark.runner import OWNER_HARD, OWNER_STOP, SessionResult
from radark.tests.conftest import START, item, show
from radark.tests.test_limit_check import limits as check_limits
from radark.tests.test_parallel import A as PA, B as PB, f, parallel, two_teams
from radark.tests.test_progress import A, apply_item, limits, log_events

GRACE = 0.05  # 3 s wrap-up grace period
TOOL = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}


def run_dir(env) -> Path:
    return env.root / "run"


def request(env, within=None, requested=None):
    """The file `wrap-up` writes."""
    at = dt.datetime.fromtimestamp(requested or time.time(), dt.timezone.utc).isoformat(timespec="seconds")
    (run_dir(env) / "WRAP_UP").write_text(json.dumps({"requested": at, "within_minutes": within}))


def long_tool(env, name="release"):
    """A tool call that returns once the test creates `name`; its PostToolUse hook runs then."""
    return {"hook": "PostToolUse", "input": TOOL, "wait_for": f(env, name)}


def stop_hook(text="Committed the work; the rest is listed under Left for a later run."):
    return {"hook": "Stop", "input": {"stop_hook_active": False, "last_assistant_message": text}}


def scenario(env, *steps, started="started"):
    return {"steps": [START, {"touch": f(env, started)}, *steps], "result": {"result": "Wrapped up."}}


def wait_file(path, within=30):
    end = time.monotonic() + within
    while not os.path.exists(path):
        assert time.monotonic() < end, f"{path} not created"
        time.sleep(0.05)


def wait_event(env, kind, n=1, within=30):
    end = time.monotonic() + within
    while len(log_events(env, kind)) < n:
        assert time.monotonic() < end, f"no {kind} event"
        time.sleep(0.05)


def owner(env, *, started=("started",), within=None, release="release", after=None):
    """The owner's side in a thread: once the sessions run, request the wrap-up; once the dispatcher has seen it,
    let the long tool calls return."""
    def body():
        for name in started:
            wait_file(f(env, name))
        request(env, within)
        wait_event(env, "owner_wrap_up_requested")
        if after:
            after()
        if release:
            open(f(env, release), "w").close()
    t = threading.Thread(target=body, daemon=True)
    t.start()
    return t


def stream_hooks(r_or_path, hook=None):
    path = r_or_path.stream_path if hasattr(r_or_path, "stream_path") else r_or_path
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("type") == "fake_hook" and (hook is None or ev.get("hook") == hook):
            out.append(ev["output"])
    return out


def prompt_of(call):
    return call["argv"][call["argv"].index("-p") + 1]


def streams(env):
    return sorted((run_dir(env) / "sessions").glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


# ---- the command and the file (tasks 1.1, 1.2)

def cli(env, *args):
    return main(["--config", str(env.config_path), *args])


def live_lock(env):
    run_dir(env).mkdir(exist_ok=True)
    (run_dir(env) / "lock").write_text(str(os.getpid()))  # this process: a live dispatcher


def test_command_without_a_running_run_writes_nothing(env, capsys):
    assert cli(env, "wrap-up") == 1
    assert "No run is running for this configuration; nothing to wrap up." in capsys.readouterr().err
    assert not (run_dir(env) / "WRAP_UP").exists()
    run_dir(env).mkdir(exist_ok=True)
    (run_dir(env) / "lock").write_text("999999")  # a lock of a dispatcher that is gone
    assert cli(env, "wrap-up") == 1 and not (run_dir(env) / "WRAP_UP").exists()


def test_command_with_a_running_run_writes_the_request(env, capsys):
    live_lock(env)
    t0 = time.time()
    assert cli(env, "wrap-up", "--within", "30") == 0
    out = capsys.readouterr().out
    data = json.loads((run_dir(env) / "WRAP_UP").read_text())
    assert data["within_minutes"] == 30
    assert abs(hm.read_wrap_up(run_dir(env) / "WRAP_UP")["requested"] - t0) < 5
    assert out.startswith(f"Wrap-up requested at {hm.hhmm(t0)}: running sessions finish their current tool call, "
                          "save their work and stop; no new step starts.")
    assert "Sessions not reached within 30 min are stopped and wrapped up." in out


def test_pending_request_is_kept(env, capsys):
    live_lock(env)
    earlier = time.time() - 600
    request(env, requested=earlier)
    before = (run_dir(env) / "WRAP_UP").read_text()
    assert cli(env, "wrap-up", "--within", "5") == 0
    assert capsys.readouterr().out.strip() == f"A wrap-up was already requested at {hm.hhmm(earlier)}."
    assert (run_dir(env) / "WRAP_UP").read_text() == before


@pytest.mark.parametrize("value", ["0", "-3", "soon"])
def test_invalid_limit_is_refused(env, value):
    live_lock(env)
    with pytest.raises(SystemExit) as exc:
        cli(env, "wrap-up", "--within", value)
    assert exc.value.code == 2 and not (run_dir(env) / "WRAP_UP").exists()


def test_hand_made_file_is_a_request_at_its_time_without_a_limit(env):
    run_dir(env).mkdir(exist_ok=True)
    path = run_dir(env) / "WRAP_UP"
    path.write_text("please stop")
    req = hm.read_wrap_up(path)
    assert req == {"requested": path.stat().st_mtime, "within": None}
    path.write_text("")
    assert hm.read_wrap_up(path)["within"] is None
    assert hm.read_wrap_up(run_dir(env) / "missing") is None


def test_status_shows_a_pending_request(env, capsys):
    live_lock(env)
    request(env, within=30)
    assert cli(env, "status") == 0
    out = capsys.readouterr().out
    at = hm.hhmm(hm.read_wrap_up(run_dir(env) / "WRAP_UP")["requested"])
    assert (f"Wrap-up requested at {at} (within 30 min): the running sessions are wrapping up; the run ends after "
            "them.") in out
    (run_dir(env) / "lock").unlink()
    assert cli(env, "status") == 0
    assert "A WRAP_UP file exists but no run is running; the next run removes it." in capsys.readouterr().out


def test_stale_file_at_start_is_removed_and_the_run_goes_on(env, capsys):
    env.set_hub({})
    run_dir(env).mkdir(exist_ok=True)
    request(env)
    (run_dir(env) / "wrap-up-request.json").write_text("{}")
    assert cli(env, "once") == 0
    out = capsys.readouterr().out
    assert "Removed a WRAP_UP file left from an earlier run." in out and "Nothing to do." in out
    assert not (run_dir(env) / "WRAP_UP").exists() and not (run_dir(env) / "wrap-up-request.json").exists()
    assert len(log_events(env, "owner_wrap_up_stale")) == 1 and not log_events(env, "owner_wrap_up_requested")


# ---- detection while idle (task 1.3)

@pytest.mark.parametrize("n", [1, 2])
def test_request_while_idle_ends_the_wait_and_the_run(env, n):
    env.config_path.write_text(env.config_path.read_text().replace("poll_seconds = 0", "poll_seconds = 120"))
    if n > 1:
        parallel(env, n)
    env.set_hub({})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    threading.Timer(1.0, lambda: request(env)).start()
    t0 = time.time()
    assert d.loop() == 0
    assert time.time() - t0 < 10 and env.claude_calls() == []
    (req,) = log_events(env, "owner_wrap_up_requested")
    assert req["sessions"] == [] and req["within_min"] is None
    (done,) = log_events(env, "owner_wrap_up_done")
    assert done["sessions"] == []
    out = "\n".join(lines)
    assert "no new step starts; nothing is running; the run ends." in out
    assert "Wrap-up done: 0 sessions ended; exiting." in out
    assert not (run_dir(env) / "WRAP_UP").exists() and not (run_dir(env) / "wrap-up-request.json").exists()


def test_stop_and_wrap_up_together_stop_wins(env):
    env.set_hub({})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    run_dir(env).mkdir(exist_ok=True)
    request(env)
    (run_dir(env) / "STOP").write_text("")
    assert d.loop() == 0
    assert "STOP file found; exiting." in lines and not log_events(env, "owner_wrap_up_done")
    assert not (run_dir(env) / "WRAP_UP").exists()


def test_goal_run_ends_stopped(env, monkeypatch):
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    ended = []
    monkeypatch.setattr(d, "end_goal", lambda status, reason: ended.append((status, reason)) or 0)
    d.goal = object()
    d._wrap_req = {"requested": time.time(), "within": None, "seen": time.time()}
    assert d.end_run() == 0 and ended == [("stopped", "wrap-up requested")]


# ---- delivery between tool calls (tasks 2.2, 2.3, 3.2)

def test_request_during_a_long_tool_call(env):
    limits(env, wrap=GRACE)
    lines = []
    d = apply_item(env)
    d._print = lines.append
    env.set_claude([scenario(env, long_tool(env), stop_hook())])
    owner(env)
    assert d.loop() == 0
    (call,) = env.claude_calls()
    (stream,) = streams(env)
    (ctx,) = stream_hooks(stream, "PostToolUse")
    text = ctx["hookSpecificOutput"]["additionalContext"]
    assert ctx["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert text.startswith(f"The owner asked this run to wrap up now (handover {A}, phase apply). Do not start new "
                           "work.")
    assert stream_hooks(stream, "Stop") == []  # no nudge after the delivery
    (end,) = log_events(env, "session_end")
    assert end["exit_code"] == 0 and end["outcome"] == "interrupted" and end["interrupt_cause"] == "owner_wrap_up"
    assert not end["timed_out"]  # the tool call ran to its end
    (req,) = log_events(env, "owner_wrap_up_requested")
    assert [(s["team"], s["handover"], s["phase"]) for s in req["sessions"]] == [("app", A, "apply")]
    assert req["sessions"][0]["session"] == call["env"]["HARNESS_SESSION"]
    (dlv,) = log_events(env, "owner_wrap_up_delivered")
    assert (dlv["source"], dlv["tool_name"], dlv["handover"]) == ("tool", "Bash", A)
    (done,) = log_events(env, "owner_wrap_up_done")
    assert done["sessions"] == [{"team": "app", "handover": A, "outcome": "interrupted", "cause": "owner_wrap_up"}]
    assert not log_events(env, "owner_wrap_up_stop") and not log_events(env, "nudge")
    rec = d.state.get(A)
    assert rec["resume_after_timeout"]["reason"] == "owner_wrap_up" and rec.get("no_progress", 0) == 0
    out = "\n".join(lines)
    assert (f"no new step starts; asking 1 running session to wrap up after the current tool call: app {A}") in out
    assert f"app {A}: wrap-up request delivered after Bash; wrapping up within {GRACE:g} min" in out
    assert f"{sym('→')} interrupted, owner wrap-up (" in out
    assert f"Wrap-up done: 1 session ended (app {A} interrupted); exiting." in out
    assert "session ended with an error" not in out


def test_request_while_the_session_writes_its_answer(env):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    env.set_claude([scenario(env, {"wait_for": f(env, "release")}, stop_hook("Here is my summary."),
                             stop_hook("Saved; Left for a later run noted."))])
    owner(env)
    assert d.loop() == 0
    (stream,) = streams(env)
    (block,) = stream_hooks(stream, "Stop")  # the second stop is let through
    assert block["decision"] == "block"
    assert block["reason"].startswith(f"The owner asked this run to wrap up now (handover {A}, phase apply).")
    (dlv,) = log_events(env, "owner_wrap_up_delivered")
    assert dlv["source"] == "stop" and dlv["tool_name"] is None
    assert not log_events(env, "nudge")


def test_grace_after_delivery_stops_the_session(env):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    env.set_claude([scenario(env, long_tool(env), {"active": 30, "every": 0.2})])
    owner(env)
    t0 = time.time()
    assert d.loop() == 0
    assert time.time() - t0 < 20 and len(env.claude_calls()) == 1
    (stop,) = log_events(env, "owner_wrap_up_stop")
    assert stop["reason"] == "grace" and stop["handover"] == A
    (end,) = log_events(env, "session_end")
    assert end["outcome"] == "interrupted" and end["interrupt_cause"] == "owner_wrap_up"


def test_no_grace_stops_right_at_delivery(env):
    limits(env, wrap=0)
    d = apply_item(env)
    env.set_claude([scenario(env, long_tool(env), {"active": 30, "every": 0.2})])
    owner(env)
    t0 = time.time()
    assert d.loop() == 0 and time.time() - t0 < 15
    assert log_events(env, "owner_wrap_up_stop")[0]["reason"] == "grace"


def test_within_reached_stops_and_resumes_with_the_wrap_up_prompt(env):
    limits(env, wrap=GRACE)
    lines = []
    d = apply_item(env)
    d._print = lines.append
    hung = scenario(env, {"heartbeats": 30, "every": 0.2})  # a tool call that does not return in time
    env.set_claude([hung, {"steps": [START, {"text": "Committed."}], "result": {"result": "Wrapped up."}}])
    owner(env, within=0.02, release=None)  # 1.2 s
    assert d.loop() == 0
    work, wrap = env.claude_calls()
    assert wrap["argv"][wrap["argv"].index("--resume") + 1] == work["env"]["HARNESS_SESSION"]
    text = prompt_of(wrap)
    assert text.startswith("The owner asked this run to wrap up now, and the dispatcher stopped this session before "
                           f"the request could reach it, in the apply phase of handover {A}. You now have {GRACE:g} "
                           "min to wrap up")
    (stop,) = log_events(env, "owner_wrap_up_stop")
    assert stop["reason"] == "within"
    (resume,) = log_events(env, "owner_wrap_up_resume")
    assert resume["outcome"] == "interrupted" and resume["interrupt_cause"] == "owner_wrap_up"
    assert [e["interrupt_cause"] for e in log_events(env, "session_end")] == ["owner_wrap_up", None]
    assert [s["outcome"] for s in d.state.get(A)["sessions"]] == ["interrupted", "interrupted"]
    assert d.state.get(A)["resume_after_timeout"]["reason"] == "owner_wrap_up"
    out = "\n".join(lines)
    assert f"app {sym('·')} apply {sym('·')} owner wrap-up {sym('·')} {A}" in out
    assert "the wrap-up limit was reached before the request reached it; the session is stopped and resumed" in out


def test_within_without_grace_only_stops(env):
    limits(env, wrap=0)
    d = apply_item(env)
    env.set_claude([scenario(env, {"heartbeats": 30, "every": 0.2})])
    owner(env, within=0.02, release=None)
    assert d.loop() == 0 and len(env.claude_calls()) == 1
    (end,) = log_events(env, "session_end")
    assert end["outcome"] == "interrupted" and end["interrupt_cause"] == "owner_wrap_up"


@pytest.mark.parametrize("delivered,answer", [(False, OWNER_HARD), (True, OWNER_STOP)])
def test_deadline_after_the_request_runs_no_limit_check(env, delivered, answer):
    check_limits(env, wrap=GRACE)
    d = apply_item(env)
    on_deadline, _ = d.limit_watch("app", A, "Task", None, None)
    d._wrap_req = {"requested": time.time(), "within": None, "seen": time.time()}
    r = SessionResult(run_id="x", session_id="x", team="app", handover=A, phase="apply", started="")
    if delivered:
        d.enlist({"team": "app", "handover": A, "phase": "apply", "title": None, "run_id": "x"})["delivered"] = 1.0
    assert on_deadline(r, 400) == answer
    assert env.claude_calls() == [] and not log_events(env, "limit_check_start")
    (stop,) = log_events(env, "owner_wrap_up_stop")
    assert stop["reason"] == "max_time"


def test_strict_end_time_still_applies(env):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    d.until, d.until_strict = time.time() + 3, True
    env.set_claude([scenario(env, {"heartbeats": 30, "every": 0.2}), {"steps": [START], "result": {}}])
    owner(env, release=None)  # never delivered: the tool call runs past the end time
    assert d.loop() == 0
    assert log_events(env, "end_time_stop") and log_events(env, "end_time_wrap_up")
    assert log_events(env, "session_end")[0]["interrupt_cause"] == "end_time"


# ---- outcome and resume (task 3.3)

def test_phase_completed_during_the_wrap_up_stays_finished(env, monkeypatch):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    monkeypatch.setattr(d, "phase_complete", lambda *a: True)
    env.set_claude([scenario(env, long_tool(env), stop_hook())])
    owner(env)
    assert d.loop() == 0
    (end,) = log_events(env, "session_end")
    assert end["outcome"] == "finished" and end["interrupt_cause"] is None
    assert "resume_after_timeout" not in d.state.get(A)
    assert log_events(env, "owner_wrap_up_done")[0]["sessions"][0]["outcome"] == "finished"


def test_question_after_the_request_is_not_triaged(env):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    ask = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion", "tool_input": {"questions": [
        {"question": "Map or object?", "header": "Cache", "options": [{"label": "Map"}, {"label": "Object"}]}]}}}
    env.set_claude([scenario(env, {"wait_for": f(env, "release")}, ask)])
    owner(env)
    assert d.loop() == 0
    assert len(env.claude_calls()) == 1 and not log_events(env, "triage")
    (end,) = log_events(env, "session_end")
    assert end["outcome"] == "interrupted" and end["interrupt_cause"] == "owner_wrap_up"


def test_next_run_resumes_the_item(env):
    limits(env, wrap=GRACE)
    d = apply_item(env)
    env.set_claude([scenario(env, long_tool(env), stop_hook()),
                    {"steps": [START], "result": {"result": "Done."}}])
    owner(env)
    assert d.loop() == 0
    first = env.claude_calls()[0]["env"]["HARNESS_SESSION"]
    nxt = Dispatcher(env.cfg(), out=lambda *a: None)
    (cand,) = nxt.plan()
    again = nxt.run_candidate(cand)
    call = env.claude_calls()[1]
    assert call["argv"][call["argv"].index("--resume") + 1] == first
    assert prompt_of(call).startswith(prompts.INTERRUPT_LABELS["owner_wrap_up"] + ", in the apply phase of handover ")
    assert again.outcome == "finished"
    assert log_events(env, "resume_after_timeout")[0]["reason"] == "owner_wrap_up"


# ---- parallel sessions (task 2.2)

def test_request_with_two_sessions_running(env):
    limits(env, wrap=GRACE)
    parallel(env)
    two_teams(env)
    work = lambda team: scenario(env, long_tool(env), stop_hook(), started=f"{team}.started")
    env.set_claude({"app": [work("app")], "backend": [work("backend")]})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    owner(env, started=("app.started", "backend.started"))
    assert d.loop() == 0
    assert len(env.claude_calls()) == 2
    (req,) = log_events(env, "owner_wrap_up_requested")
    assert sorted(s["team"] for s in req["sessions"]) == ["app", "backend"]
    assert sorted(e["team"] for e in log_events(env, "owner_wrap_up_delivered")) == ["app", "backend"]
    for stream in streams(env):
        (ctx,) = stream_hooks(stream, "PostToolUse")
        assert "The owner asked this run to wrap up now" in ctx["hookSpecificOutput"]["additionalContext"]
    (done,) = log_events(env, "owner_wrap_up_done")
    assert sorted(s["handover"] for s in done["sessions"]) == sorted([PA, PB])
    assert "asking 2 running sessions to wrap up after the current tool call" in "\n".join(lines)
    assert "Wrap-up done: 2 sessions ended" in "\n".join(lines)
