"""Sessions of different repositories in parallel (change parallel-sessions) with fake `ho` and `claude`."""
import json
import os
import subprocess
import sys
import threading
import time

import pytest

import radark.__main__ as hm
import radark.runner as runner_mod
from radark import config as config_mod
from radark import prompts
from radark import select as sel
from radark.__main__ import Dispatcher, main
from radark.runner import Runner, session_env
from radark.state import GoalRun, now_ts
from radark.tests.conftest import START, goal_verdict, item, show

A, B, C = "HO-20261114-aaaa", "HO-20261114-bbbb", "HO-20261114-cccc"
NEW, OLD = "2026-11-14T10:00:00.000Z", "2026-11-14T09:00:00.000Z"
DONE = {"result": "Done."}


def parallel(env, n=2, extra=""):
    env.config_path.write_text(env.config_path.read_text() + f"parallel_sessions = {n}\n" + extra)


def disp(env, lines=None):
    return Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def prompt_of(call):
    return call["argv"][call["argv"].index("-p") + 1]


def shown(hid, to, **kw):
    return {**show(hid, **kw), "to": [to], "from": "product"}


def two_teams(env, title_a="App task", title_b="Backend task"):
    """A new item for app (newest) and an unrelated new item for backend."""
    env.set_hub({"inbox:app": {"action_required": [item(A, title=title_a, last=NEW)]},
                 "inbox:backend": {"action_required": [item(B, title=title_b, last=OLD)]},
                 f"show:{A}": shown(A, "app", created=NEW, title=title_a),
                 f"show:{B}": shown(B, "backend", created=OLD, title=title_b)})


def f(env, name):
    return str(env.root / name)


def stop(env):
    return {"touch": str(env.root / "run" / "STOP")}


def ordered(env, first, second):
    """Scenarios in which `first` and `second` run at the same time and `first` ends first; the first one also
    asks the loop to stop, so no item is started again."""
    return {
        first: [{"steps": [START, {"wait_for": f(env, f"{second}.started")}, stop(env), {"touch": f(env, f"{first}.done")}],
                 "result": DONE}],
        second: [{"steps": [START, {"touch": f(env, f"{second}.started")}, {"wait_for": f(env, f"{first}.done")}, {"sleep": 2}],
                  "result": DONE}],
    }


def starts_and_ends(env):
    return [(e["event"], e["team"]) for e in log_events(env) if e["event"] in ("session_start", "session_end")]


# ---- configuration (task 2.1)

def test_parallel_sessions_default_and_two(env):
    assert env.cfg().parallel_sessions == 1
    parallel(env)
    cfg = env.cfg()
    assert cfg.parallel_sessions == 2
    assert "Parallel sessions: up to 2" in config_mod.summary(cfg, "x")


@pytest.mark.parametrize("value", ["0", '"two"', "true", "1.5"])
def test_parallel_sessions_refused(env, value):
    env.config_path.write_text(env.config_path.read_text() + f"parallel_sessions = {value}\n")
    with pytest.raises(config_mod.ConfigError, match="loop.parallel_sessions"):
        env.cfg()


def test_invalid_value_stops_main(env, capsys):
    env.config_path.write_text(env.config_path.read_text() + "parallel_sessions = 0\n")
    assert main(["--config", str(env.config_path), "once"]) == 2
    assert "parallel_sessions" in capsys.readouterr().err and env.claude_calls() == []


# ---- selection (task 2.2)

def cand(team, hid, recency, index):
    return sel.Candidate(kind="work", team=team, handover=hid, title="", phase="apply", recency=recency,
                         team_index=index)


def test_pick_free():
    a, b = cand("app", A, NEW, 1), cand("backend", B, OLD, 2)
    assert sel.pick_free([b, a], set(), set()) is a  # sel.ordered order
    assert sel.pick_free([a, b], {"app"}, {A}) is b  # second call with the first one running
    assert sel.pick_free([a, b], {"app", "backend"}, {A, B}) is None
    a2 = cand("app", C, NEW, 1)
    assert sel.pick_free([a, a2], {"app"}, {A}) is None  # same repository
    shared = {"app": "repo", "backend": "repo"}
    assert sel.pick_free([a, b], {"repo"}, {A}, shared) is None  # two teams sharing one repository
    b_same = cand("backend", A, OLD, 2)
    assert sel.pick_free([a, b_same], {"app"}, {A}) is None  # same handover for two teams


def test_held_item_is_not_picked():
    cands = sel.candidates([("app", "technical")], {"app": {"action_required": [item(A)]}},
                           {A: show(A)}, {A: {"team": "app", "flags": {}, "sessions": []}},
                           {A: [{"handover": B, "team": "backend", "state": "pending"}]})
    assert sel.pick_free(cands, set(), set()) is None


# ---- environment and prompt note (tasks 1.2, 1.3)

@pytest.mark.parametrize("n", [1, 2])
def test_session_env_has_parallel_sessions(env, n):
    parallel(env, n)
    cfg = env.cfg()
    assert session_env({}, cfg, "backend", B, "s", "r")["HARNESS_PARALLEL_SESSIONS"] == str(n)


@pytest.mark.parametrize("n", [1, 2])
def test_parallel_note_in_phase_and_resume_prompts(env, n):
    parallel(env, n)
    env.set_hub({"inbox:app": {"action_required": [item(A, last=NEW)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": DONE}])
    d = disp(env)
    d.loop(once=True)
    rec = d.state.get(A)
    rec["resume_after_timeout"] = {"session": rec["sessions"][0]["id"], "team": "app", "phase": "propose",
                                   "reason": "idle_timeout", "duration_s": 60}
    d.state.save()
    disp(env).loop(once=True)
    phase, resume = (prompt_of(c) for c in env.claude_calls())
    assert "--resume" in env.claude_calls()[1]["argv"]
    for text in (phase, resume):
        assert (prompts.PARALLEL_NOTE in text) == (n > 1)
    assert env.claude_calls()[0]["env"]["HARNESS_PARALLEL_SESSIONS"] == str(n)


def test_work_in_progress_section():
    running = [{"team": "app", "handover": A, "phase": "apply", "title": "App task"}]
    text = prompts.idle_prompt([], None, running)
    assert f'Work in progress right now (other sessions are working on it): app {A} "App task" (apply).' in text
    assert "do not report them as stalled" in text
    assert "Work in progress" not in prompts.idle_prompt([], None, [])
    assert f"app {A}" in prompts.goal_check_prompt("Goal.", "", running)
    assert "Work in progress" not in prompts.goal_check_prompt("Goal.")


# ---- recovery (task 3.1)

def left(session, team, hid, phase="apply"):
    return {"session": session, "run_id": session, "team": team, "handover": hid, "phase": phase, "step": None,
            "pid": 0, "started": now_ts()}


@pytest.mark.parametrize("kind", ["none", "old", "new", "two"])
def test_recovery_of_running_records(env, kind):
    d = disp(env)
    d.state.ensure(A, "app")
    d.state.ensure(B, "backend")
    one, two = left("s-app", "app", A), left("s-backend", "backend", B)
    d.state.meta["running"] = {"none": None, "old": one, "new": {"s-app": one},
                               "two": {"s-app": one, "s-backend": two}}[kind]
    if kind == "none":
        d.state.meta.pop("running")
    d.state.save()
    d = disp(env)
    d.recover()
    events = log_events(env, "interrupted")
    expected = {"none": [], "old": ["s-app"], "new": ["s-app"], "two": ["s-app", "s-backend"]}[kind]
    assert sorted(e["session"] for e in events) == expected
    assert "running" not in d.state.meta
    for session, hid in (("s-app", A), ("s-backend", B)):
        if session in expected:
            assert d.state.get(hid)["resume_after_timeout"]["session"] == session


# ---- two sessions at once (task 3.2)

@pytest.mark.parametrize("first", ["app", "backend"])
def test_two_sessions_run_at_once_and_end_in_either_order(env, first):
    parallel(env)
    two_teams(env)
    second = "backend" if first == "app" else "app"
    env.set_claude(ordered(env, first, second))
    lines = []
    d = disp(env, lines)
    assert d.loop() == 0
    seq = starts_and_ends(env)
    assert seq[:2] == [("session_start", "app"), ("session_start", "backend")]
    assert seq[2:] == [("session_end", first), ("session_end", second)]
    for hid, team in ((A, "app"), (B, "backend")):
        rec = d.state.get(hid)
        assert rec["team"] == team and [s["outcome"] for s in rec["sessions"]] == ["finished"]
    raw = (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(x) for x in raw)  # complete JSON lines
    assert any("(2 running)" in x and "backend" in x for x in lines)
    ends = [x for x in lines if "→ finished" in x or "-> finished" in x]
    assert any(f"app" in x and A in x for x in ends) and any("backend" in x and B in x for x in ends)
    assert "running" not in d.state.meta
    calls = env.claude_calls()
    assert {c["env"]["HARNESS_TEAM"] for c in calls} == {"app", "backend"}


def decline(hid):
    return {"ho": ["decline", hid, "-m", "not now"]}


def test_one_session_at_a_time_by_default(env):
    two_teams(env)
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "backend.started"), "within": 1}, decline(A)],
                             "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}, stop(env)], "result": DONE}]})
    d = disp(env)
    assert d.loop() == 0
    assert starts_and_ends(env) == [("session_start", "app"), ("session_end", "app"),
                                    ("session_start", "backend"), ("session_end", "backend")]


def test_same_repository_waits(env):
    parallel(env)
    env.set_hub({"inbox:app": {"action_required": [item(A, last=NEW), item(C, last=OLD)]},
                 f"show:{A}": shown(A, "app", created=NEW), f"show:{C}": shown(C, "app", created=OLD)})
    env.set_claude({"app": [{"steps": [START, {"sleep": 1}, decline(A)], "result": DONE},
                            {"steps": [START, stop(env)], "result": DONE}]})
    d = disp(env)
    assert d.loop() == 0
    starts = [e for e in log_events(env) if e["event"] in ("session_start", "session_end")]
    assert [e["event"] for e in starts][:4] == ["session_start", "session_end", "session_start", "session_end"]


def test_same_handover_for_two_teams_runs_once_at_a_time(env):
    parallel(env)
    env.set_hub({"inbox:app": {"action_required": [item(A, last=NEW)]},
                 "inbox:backend": {"action_required": [item(A, last=NEW)]}, f"show:{A}": show(A, created=NEW)})
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "backend.started"), "within": 1}, stop(env)],
                             "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}], "result": DONE}]})
    d = disp(env)
    assert d.loop() == 0
    assert starts_and_ends(env) == [("session_start", "app"), ("session_end", "app")]


def test_console_log_has_whole_lines(env):
    parallel(env)
    two_teams(env)
    env.set_claude(ordered(env, "backend", "app"))
    assert main(["--config", str(env.config_path), "run"]) == 0
    text = (env.root / "run" / "console.log").read_text(encoding="utf-8")
    lines = [x for x in text.splitlines() if "finished (" in x]
    assert len(lines) == 2 and all(x[:5].replace(":", "").isdigit() for x in lines)


# ---- run control (task 3.4)

def test_end_time_lets_both_sessions_finish(env):
    parallel(env)
    two_teams(env)
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "backend.started")}, {"sleep": 1.5}], "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}, {"sleep": 4}],
                                 "result": DONE}]})
    lines = []
    d = disp(env, lines)
    threading.Timer(1.0, lambda: setattr(d, "until", time.time())).start()  # passes while both run
    assert d.loop() == 0
    assert [t for _, t in starts_and_ends(env)].count("app") == 2  # one start and one end each
    assert [t for _, t in starts_and_ends(env)].count("backend") == 2
    assert any("End time" in x and "reached" in x for x in lines)
    assert any("No new session (end time reached)" in x for x in lines)


def test_pause_waits_without_new_starts(env):
    parallel(env)
    env.set_hub({"inbox:app": {"action_required": [item(A, last=NEW)]}, f"show:{A}": show(A)})
    env.set_claude({"app": [{"steps": [START, {"touch": str(env.root / "run" / "PAUSE")},
                                       {"ho": ["new", "--to", "backend", "--title", "Later", "--expects", "done",
                                               "-m", "Do it."]},
                                       {"wait_for": f(env, "backend.started"), "within": 1.5}], "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}], "result": DONE}]})
    lines = []
    d = disp(env, lines)

    def later():
        time.sleep(4)
        (env.root / "run" / "STOP").touch()
    threading.Thread(target=later, daemon=True).start()
    assert d.loop() == 0
    teams = [t for e, t in starts_and_ends(env) if e == "session_start"]
    assert teams == ["app"] and "Paused (PAUSE file); waiting." in lines


def test_ctrl_c_twice_ends_both_sessions(env):
    parallel(env)
    two_teams(env)
    env.set_claude({"app": [{"steps": [START, {"touch": f(env, "app.started")}, {"active": 20, "every": 0.2}],
                             "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}, {"active": 20, "every": 0.2}],
                                 "result": DONE}]})
    lines = []
    d = disp(env, lines)

    def press():
        for name in ("app.started", "backend.started"):
            while not os.path.exists(f(env, name)):
                time.sleep(0.05)
        time.sleep(0.5)
        d._on_interrupt(None, None)
        d._on_interrupt(None, None)
    threading.Thread(target=press, daemon=True).start()
    t0 = time.time()
    assert d.loop() == 0
    assert time.time() - t0 < 15
    ends = log_events(env, "session_end")
    assert sorted(e["team"] for e in ends) == ["app", "backend"]
    assert all((e["outcome"], e["interrupt_cause"]) == ("interrupted", "owner") for e in ends)
    assert any("Ending the 2 running sessions." in x for x in lines)


def test_ctrl_c_once_finishes_both(env):
    parallel(env)
    two_teams(env)
    env.set_claude({"app": [{"steps": [START, {"touch": f(env, "app.started")}, {"wait_for": f(env, "go")}],
                             "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}, {"wait_for": f(env, "go")}],
                                 "result": DONE}]})
    lines = []
    d = disp(env, lines)

    def press():
        for name in ("app.started", "backend.started"):
            while not os.path.exists(f(env, name)):
                time.sleep(0.05)
        d._on_interrupt(None, None)
        open(f(env, "go"), "w").close()
    threading.Thread(target=press, daemon=True).start()
    assert d.loop() == 0
    assert all(e["outcome"] == "finished" for e in log_events(env, "session_end"))
    assert len(log_events(env, "session_end")) == 2
    assert any("Finishing the 2 running sessions" in x for x in lines)


def test_goal_max_sessions_stops_new_starts(env):
    parallel(env)
    two_teams(env)
    path = env.root / "goal.md"
    path.write_text("Finish it.", encoding="utf-8")
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish it.", 2, 12))
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "backend.started")}], "result": DONE}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.started")}], "result": DONE}]})
    assert d.loop() == hm.GOAL_EXIT["limit"]
    assert sorted(e["team"] for e in log_events(env, "session_start")) == ["app", "backend"]
    assert log_events(env, "goal_result")[0]["status"] == "limit"


# ---- whole-hub steps next to running work (task 3.5)

def test_idle_ask_next_to_a_long_apply(env):
    parallel(env, extra="idle_ask = true\n")
    env.set_hub({"inbox:app": {"action_required": [item(A, title="Long apply", last=NEW)]},
                 f"show:{A}": show(A, created=NEW, title="Long apply")})
    verdict = {"structured_output": {"verdict": "none", "reason": "nothing", "waiting_for_owner": []}}
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "idle.done")}, {"sleep": 2}], "result": DONE}],
                    "product": [{"steps": [START, stop(env), {"touch": f(env, "idle.done")}], "result": verdict}]})
    d = disp(env)
    assert d.loop() == 0
    calls = env.claude_calls()
    idle = next(c for c in calls if c["env"]["HARNESS_TEAM"] == "product")
    assert f"Work in progress right now (other sessions are working on it): app {A}" in prompt_of(idle)
    assert starts_and_ends(env)[-1] == ("session_end", "app")


def test_idle_ask_without_running_work_has_no_section(env):
    parallel(env, extra="idle_ask = true\n")
    verdict = {"structured_output": {"verdict": "none", "reason": "nothing", "waiting_for_owner": []}}
    env.set_claude({"product": [{"steps": [START, stop(env)], "result": verdict}]})
    disp(env).loop()
    assert "Work in progress" not in prompt_of(env.claude_calls()[0])


def test_goal_complete_while_a_session_runs(env):
    parallel(env)
    env.set_hub({"inbox:backend": {"action_required": [item(B, last=OLD)]}, f"show:{B}": show(B)})
    path = env.root / "goal.md"
    path.write_text("Finish B.", encoding="utf-8")
    env.set_claude({"backend": [{"steps": [START, {"wait_for": f(env, "goal.done")}, {"sleep": 2}], "result": DONE}],
                    "product": [{"steps": [START, {"touch": f(env, "goal.done")}],
                                 "result": goal_verdict("complete", "all done")}]})
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish B.", 40, 12))
    assert d.loop() == 0
    events = [e["event"] for e in log_events(env) if e["event"] in ("session_end", "goal_result", "goal_verdict")]
    assert events[-1] == "goal_result" and events.count("session_end") == 2
    ends = [e["team"] for e in log_events(env, "session_end")]
    assert ends == ["product", "backend"]  # the run ends only after backend is processed
    assert log_events(env, "goal_result")[0]["status"] == "complete"


def test_no_repeated_goal_check_while_waiting(env):
    parallel(env)
    env.set_hub({"inbox:backend": {"action_required": [item(B, last=OLD)]}, f"show:{B}": show(B)})
    path = env.root / "goal.md"
    path.write_text("Finish B.", encoding="utf-8")
    env.set_claude({"backend": [{"steps": [START, {"wait_for": f(env, "goal.done")}, {"sleep": 2}, stop(env)],
                                 "result": DONE}],
                    "product": [{"steps": [START, {"touch": f(env, "goal.done")}],
                                 "result": goal_verdict("continue", "in progress")}]})
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish B.", 40, 12))
    d.loop()
    assert [e["team"] for e in log_events(env, "session_start")] == ["backend", "product"]
    assert d.goal.empty_continues == 0  # waiting for running work is no stall


# ---- dry-run (task 3.7)

@pytest.mark.parametrize("n", [1, 2])
def test_dry_run_parallel_line(env, capsys, n):
    parallel(env, n)
    two_teams(env)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"Would start: app" in out
    if n == 1:
        assert "In parallel" not in out
    else:
        assert f"In parallel (parallel_sessions = 2): backend propose {B}" in out


def test_dry_run_nothing_else_can_start(env, capsys):
    parallel(env)
    env.set_hub({"inbox:app": {"action_required": [item(A, last=NEW), item(C, last=OLD)]},
                 f"show:{A}": show(A), f"show:{C}": show(C)})
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert "In parallel: nothing else can start (the other candidates are for a repository or handover" in \
        capsys.readouterr().out


# ---- a session's processes end with it (task 1.1)

def pid_alive(pid):
    return hm.pid_alive(pid) if os.name == "nt" else _posix_alive(pid)


def _posix_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_gone(pid, seconds=10):
    end = time.time() + seconds
    while time.time() < end and pid_alive(pid):
        time.sleep(0.1)
    return not pid_alive(pid)


@pytest.mark.parametrize("end", ["normal", "kill"])
def test_detached_child_ends_with_the_session(env, end):
    pidfile = env.root / "child.pid"
    steps = [START, {"detach": str(pidfile)}] + ([{"active": 30, "every": 0.2}] if end == "kill" else [])
    env.set_claude([{"steps": steps, "result": DONE}])
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])  # another session's process
    try:
        runner = Runner(env.cfg())
        if end == "kill":
            def kill():
                while not pidfile.exists():
                    time.sleep(0.05)
                time.sleep(0.3)
                runner.kill()
            threading.Thread(target=kill, daemon=True).start()
        r = runner.run("app", "go", phase="apply", handover=A)
        assert r.isolated
        assert (r.outcome == "finished") == (end == "normal")
        child = int(pidfile.read_text())
        assert wait_gone(child)
        assert other.poll() is None
    finally:
        other.kill()


def test_fallback_when_the_job_cannot_be_made(env, monkeypatch):
    class NoJob(runner_mod.ProcessJob):
        def __init__(self, proc):
            self.proc, self.handle, self.ok = proc, None, False

    monkeypatch.setattr(runner_mod, "make_job", NoJob)
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    pidfile = env.root / "child.pid"
    env.set_claude([{"steps": [START, {"detach": str(pidfile)}], "result": DONE}])
    lines = []
    d = disp(env, lines)
    d.loop(once=True)
    children = [int(pidfile.read_text())]
    try:
        assert len(log_events(env, "job_object_unavailable")) == 1
        assert any("could not be put in a job object" in x for x in lines)
        d.loop(once=True)
        children.append(int(pidfile.read_text()))
        assert len(log_events(env, "job_object_unavailable")) == 1  # logged once
    finally:
        for child in children:
            hm.kill_pid_tree(child)


# ---- per-session handling in the worker (task 3.3)

def test_usage_limit_of_one_session_sets_the_backoff_and_the_other_goes_on(env):
    parallel(env)
    two_teams(env)
    reset = int(time.time()) + 52 * 60
    env.set_claude({"app": [{"steps": [START, {"wait_for": f(env, "backend.ended")}, {"sleep": 1}, stop(env)],
                             "result": DONE}],
                    "backend": [{"steps": [START, {"usage": {"five_hour": [0.99, reset]}},
                                           {"hook": "StopFailure", "input": {"error": "rate_limit"}},
                                           {"touch": f(env, "backend.ended")}], "exit": 1}]})
    d = disp(env)
    assert d.loop() == 0
    outcomes = {e["team"]: e["outcome"] for e in log_events(env, "session_end")}
    assert outcomes == {"app": "finished", "backend": "usage_limit"}
    assert d.state.meta["backoff_until"] == reset + 60
    assert len(log_events(env, "session_start")) == 2


def test_triage_of_one_session_while_another_runs(env):
    from radark.tests.conftest import ASK_STEP, stop_step
    parallel(env)
    two_teams(env)
    tri = {"structured_output": {"verdict": "technical", "answer": "", "reason": "internal detail"}}
    env.set_claude({"app": [{"steps": [START, ASK_STEP, stop_step("Waiting for the answer.")],
                             "result": {"result": "Referred."}},
                            {"steps": [START, decline(A), {"touch": f(env, "app.resumed")}], "result": DONE}],
                    "product": [{"steps": [START], "result": {"result": "", **tri}}],
                    "backend": [{"steps": [START, {"wait_for": f(env, "app.resumed")}, {"sleep": 1}, stop(env)],
                                 "result": DONE}]})
    d = disp(env)
    assert d.loop() == 0
    ends = [(e["team"], e["phase"]) for e in log_events(env, "session_end")]
    assert ends[:3] == [("app", "propose"), ("product", "consult"), ("app", "propose")]
    assert ends[3] == ("backend", "propose")
    assert log_events(env, "triage")[0]["verdict"]["verdict"] == "technical"
    calls = env.claude_calls()
    resumed = [c for c in calls if c["env"]["HARNESS_TEAM"] == "app"][1]["argv"]
    assert "--resume" in resumed


def test_limit_check_of_one_session_while_another_runs(env):
    parallel(env)
    text = env.config_path.read_text()
    env.config_path.write_text(text.replace("[loop]", "[loop]\nsession_max_minutes = 0.03\nlimit_check_minutes = 1\n"
                                                      "limit_checks = 3\nwrap_up_minutes = 0"))
    two_teams(env)
    hung = {"structured_output": {"verdict": "hung", "reason": "No output for long."}}
    env.set_claude({"app": [{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}],
                    "product": [{"steps": [START, {"wait_for": f(env, "backend.done")}, stop(env)], "result": hung}],
                    "backend": [{"steps": [START, {"touch": f(env, "backend.done")}], "result": DONE}]})
    d = disp(env)
    t0 = time.time()
    assert d.loop() == 0
    assert time.time() - t0 < 25
    ends = {e["team"]: (e["outcome"], e["timeout_reason"]) for e in log_events(env, "session_end")}
    assert ends == {"app": ("error", "max_time"), "backend": ("finished", None)}
    (check,) = log_events(env, "limit_check")
    assert (check["team"], check["verdict"]) == ("app", "hung")


def test_start_line_running_count():
    assert hm.start_lines("backend", "apply", B, None, None, 2)[0].endswith(f"{B} (2 running)")
    assert "running" not in hm.start_lines("backend", "apply", B, None, None, 1)[0]
