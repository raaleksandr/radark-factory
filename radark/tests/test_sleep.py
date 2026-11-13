"""Sleep of the computer, interrupted sessions and their recovery (change sleep-aware-dispatcher)."""
import json
import os
import subprocess
import sys
import time

import pytest

import radark.__main__ as hm
from radark.__main__ import Dispatcher, main
from radark.clock import Sleep
from radark.state import GoalRun, now_ts
from radark.tests.conftest import START, goal_verdict, item, show

A = "HO-20261016-aaaa"
NIGHT = 9 * 3600 + 57 * 60


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def a_sleep(seconds=NIGHT):
    end = time.time()
    return Sleep(start=end - seconds, end=end, seconds=seconds)


class Watch:
    """Reports the given sleeps, one per check; with `during`, only once a session has run `after` seconds."""

    def __init__(self, *sleeps, during=None, after=0.0):
        self.sleeps, self.during, self.after, self.seen = list(sleeps), during, after, None

    def check(self):
        if not self.sleeps:
            return None
        if self.during is not None:
            if self.during._running is None:
                return None
            self.seen = self.seen or time.monotonic()
            if time.monotonic() - self.seen < self.after:
                return None
        return self.sleeps.pop(0)


def disp(env, lines=None, watch=None):
    return Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)), watch=watch)


def grace(env, minutes):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", f"[loop]\nwake_grace_minutes = {minutes}"))


def prompt_of(call):
    return call["argv"][call["argv"].index("-p") + 1]


def apply_item(env):
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]}, f"show:{A}": show(A)})
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    d.state.save()


def review_item(env):
    """A handover app has done, waiting for the product team's review."""
    env.set_hub({"inbox:product": {"to_review": [item(A, sender="app")]}, f"show:{A}": show(A)})
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="done")
    d.state.save()


# ---- the sleep line and the `suspend` event (task 1.3)

def test_sleep_reported_once(env):
    lines = []
    s = a_sleep()
    d = disp(env, lines, Watch(s))
    assert d.loop(once=True) == 0
    d.loop(once=True)
    want = f"! computer slept {hm.stamp(s.start)}{hm.sym('–')}{hm.stamp(s.end)} (9 h 57 min) - not counted"
    assert [x for x in lines if "computer slept" in x] == [f"{hm.stamp()}  {want}"]
    events = log_events(env, "suspend")
    assert len(events) == 1 and events[0]["seconds"] == NIGHT and events[0]["during"] is None
    assert (events[0]["start"], events[0]["end"]) == (s.start, s.end)


def test_sleep_during_a_session_names_it(env):
    apply_item(env)
    env.set_claude([{"steps": [START, {"text": "working"}], "result": {"result": "Done."}}])
    d = disp(env, watch=None)
    d.watch = Watch(a_sleep(3600), during=d)
    d.loop(once=True)
    (event,) = log_events(env, "suspend")
    assert event["during"] == {"team": "app", "handover": A, "phase": "apply"}


def test_usage_window_reset_during_the_sleep(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    d = disp(env)
    reset = time.time() - 3 * 3600  # 04:20 while the computer slept 01:00-07:00
    d.state.meta["usage"] = {"five_hour": {"utilization": 0.95, "resets_at": reset, "status": "allowed", "seen": "x"}}
    d.state.meta["backoff_until"] = reset + hm.USAGE_MARGIN_S
    d.state.meta["usage_wait"] = {"until": reset + hm.USAGE_MARGIN_S, "window": "five_hour", "cause": "threshold"}
    d.state.save()
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    lines = []
    d = disp(env, lines, Watch(a_sleep(6 * 3600)))
    assert d.loop(once=True) == 0
    assert len(env.claude_calls()) == 1
    assert any("Usage window five_hour has reset; resuming." in x for x in lines)
    assert len(log_events(env, "suspend")) == 1


# ---- interrupted sessions and their resume (tasks 2.3)

def test_interrupted_review_is_resumed_after_the_wake(env):
    grace(env, 0.02)  # 1.2 s
    review_item(env)
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": {}},
                    {"steps": [START], "result": {"result": "Accepted."}}])
    lines = []
    d = disp(env, lines)
    d.watch = Watch(a_sleep(2 * 3600), during=d, after=1.5)
    d.loop(once=True)
    rec = d.state.get(A)
    first = rec["sessions"][0]["id"]
    end = log_events(env, "session_end")[0]
    assert (end["outcome"], end["interrupt_cause"]) == ("interrupted", "sleep")
    assert rec["no_progress"] == 0 and rec["resume_after_timeout"]["reason"] == "sleep"
    assert rec["resume_after_timeout"]["team"] == "product"
    assert any(f"{hm.sym('→')} interrupted, computer slept (" in x for x in lines)
    assert not any("no progress" in x or "error" in x for x in lines)
    assert "running" not in d.state.meta
    d = disp(env)
    d.loop(once=True)
    call = env.claude_calls()[1]
    assert call["argv"][call["argv"].index("--resume") + 1] == first
    assert "The computer slept" in prompt_of(call) and f"ho close {A}" in prompt_of(call)
    assert "resume_after_timeout" not in d.state.get(A)


def test_failing_resume_after_a_sleep_starts_fresh(env):
    apply_item(env)
    d = disp(env)
    d.state.get(A)["resume_after_timeout"] = {"session": "sess-cut", "team": "app", "phase": "apply",
                                              "reason": "sleep", "duration_s": 120}
    d.state.save()
    env.set_claude([{"steps": [START], "result": None, "exit": 1},
                    {"steps": [START], "result": {"result": "Done."}}])
    disp(env).loop(once=True)
    first, second = env.claude_calls()
    assert first["argv"][first["argv"].index("--resume") + 1] == "sess-cut" and "computer slept" in prompt_of(first)
    assert "--session-id" in second["argv"] and "Implement the OpenSpec change `add-x`" in prompt_of(second)


def test_interrupted_goal_check_runs_again(env):
    grace(env, 0.02)
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": {}},
                    {"steps": [START], "result": goal_verdict("complete", "done")}])
    d = disp(env)
    d.watch = Watch(a_sleep(3600), during=d, after=1.5)
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    assert d.loop() == 0
    assert len(env.claude_calls()) == 2 and d.goal.empty_continues == 0
    assert not log_events(env, "goal_verdict_invalid")


# ---- the running-session record (task 3.1)

def copy_state(env, name):
    src, dst = env.root / "run" / "state.json", env.root / name
    return {"cmd": [sys.executable, "-c", f"import shutil; shutil.copy(r'{src}', r'{dst}')"]}


def test_running_record_during_a_session_only(env):
    apply_item(env)
    env.set_claude([{"steps": [START, copy_state(env, "during.json")], "result": {"result": "Done."}}])
    d = disp(env)
    d.loop(once=True)
    running = json.loads((env.root / "during.json").read_text(encoding="utf-8"))["meta"]["running"]
    session = d.state.get(A)["sessions"][0]["id"]
    assert (running["session"], running["team"], running["handover"], running["phase"]) == (session, "app", A, "apply")
    assert running["pid"] > 0 and running["started"]
    assert "running" not in d.state.meta
    assert "running" not in json.loads((env.root / "run" / "state.json").read_text(encoding="utf-8"))["meta"]


def test_running_record_for_a_goal_check(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    env.set_claude([{"steps": [START, copy_state(env, "during.json")],
                     "result": goal_verdict("complete", "done")}])
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    assert d.loop() == 0
    running = json.loads((env.root / "during.json").read_text(encoding="utf-8"))["meta"]["running"]
    assert (running["phase"], running["handover"], running["team"]) == ("goal", None, "product")
    assert "running" not in json.loads((env.root / "run" / "state.json").read_text(encoding="utf-8"))["meta"]


# ---- recovery at start (task 3.2)

def leave_record(env, **fields):
    d = disp(env)
    d.state.meta["running"] = {"session": "sess-left", "run_id": "sess-left", "team": "app", "handover": A,
                               "phase": "apply", "step": None, "pid": 0, "started": now_ts(), **fields}
    d.state.save()


def test_apply_left_running_is_resumed_first(env, capsys):
    apply_item(env)
    leave_record(env)
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    assert main(["--config", str(env.config_path), "once"]) == 0
    call = env.claude_calls()[0]
    assert call["argv"][call["argv"].index("--resume") + 1] == "sess-left"
    assert "The dispatcher stopped while this session ran" in prompt_of(call)
    out = capsys.readouterr().out
    assert f"! app {A}: session sess-left (apply) was interrupted at " in out and "it will be resumed" in out
    (event,) = log_events(env, "interrupted")
    assert (event["cause"], event["session"], event["resumed"]) == ("dispatcher_stopped", "sess-left", True)
    state = json.loads((env.root / "run" / "state.json").read_text(encoding="utf-8"))
    assert "running" not in state["meta"] and state["handovers"][A]["sessions"][0]["outcome"] == "interrupted"


def test_goal_check_left_running_is_dropped(env, capsys):
    leave_record(env, team="product", handover=None, phase="goal")
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    assert main(["--config", str(env.config_path), "run", "--goal", str(path), "--no-wait"]) == 0
    call = env.claude_calls()[0]
    assert "--resume" not in call["argv"] and "goal" in prompt_of(call).lower()
    assert "it will run again when due" in capsys.readouterr().out
    assert log_events(env, "interrupted")[0]["resumed"] is False


@pytest.mark.skipif(os.name != "nt", reason="process creation time is read on Windows only")
def test_leftover_process_ended_but_a_reused_pid_kept(env):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        leave_record(env, pid=proc.pid, started="2000-01-01T00:00:00.000Z")  # the PID now belongs to a later process
        disp(env).recover()
        time.sleep(0.5)
        assert proc.poll() is None
        leave_record(env, pid=proc.pid)  # recorded after the process started: it is the session's
        disp(env).recover()
        assert proc.wait(10) is not None
    finally:
        proc.kill()


# ---- goal duration (task 4.1)

def test_night_sleep_does_not_end_the_goal_run(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    d = disp(env, watch=Watch(a_sleep(8 * 3600)))
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    d.goal.started -= 10 * 3600  # 2 h of work, then 8 h of sleep
    assert d.loop() == 0
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "complete" and result["slept_s"] == 8 * 3600
    assert 2 * 3600 <= result["duration_s"] < 2 * 3600 + 60
    report = sorted((env.root / "run").glob("goal-report-*.md"))[-1].read_text(encoding="utf-8")
    assert "duration 2 h 00 min (limit 12 h), slept 8 h 00 min" in report
    assert json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))["slept_s"] == 8 * 3600
