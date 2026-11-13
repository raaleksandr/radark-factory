"""Usage budget of a run: options, ending the run, override of the global threshold, reporting (run-usage-budget)."""
import json
import time

import pytest

from harness.__main__ import Dispatcher, budget_reached, held_windows, main
from harness.state import GoalRun
from harness.tests.conftest import START, item, show, usage_step

A = "HO-20261016-aaaa"


def disp(env, lines=None, **budget):
    d = Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))
    d.budget = budget
    return d


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def with_task(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


def store(env, **windows):
    """windows: name=(utilization, seconds until reset[, status])."""
    d = disp(env)
    d.state.meta["usage"] = {w: {"utilization": v[0], "resets_at": time.time() + v[1],
                                 "status": v[2] if len(v) > 2 else "allowed", "seen": "x"}
                             for w, v in windows.items()}
    d.state.save()


def reading(utilization, seconds=3600, status="allowed"):
    return {"utilization": utilization, "resets_at": time.time() + seconds, "status": status}


def run(env, *args):
    return main(["--config", str(env.config_path), *args])


# ---- options (task 1.1)

def test_dry_run_accepts_both_budgets(env, capsys):
    with_task(env)
    assert run(env, "dry-run", "--budget-5h", "95", "--budget-7d", "80") == 0
    assert "budget: below (five_hour 0% < 95%, seven_day 0% < 80%)" in capsys.readouterr().out
    assert run(env, "run", "--dry-run", "--budget-7d", "80") == 0
    assert "budget: below (seven_day 0% < 80%)" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--budget-5h", "--budget-7d"])
@pytest.mark.parametrize("value", ["0", "120"])
def test_invalid_budget_refused(env, capsys, flag, value):
    with_task(env)
    assert run(env, "run", flag, value) == 2
    assert flag in capsys.readouterr().err
    assert env.claude_calls() == [] and not (env.root / "run" / "lock").exists()


def test_budget_not_stored(env):
    store(env, seven_day=(0.5, 3600))
    d = disp(env, seven_day=80)
    d.start_budget()
    d.state.save()
    assert "budget" not in json.dumps(d.state.meta)
    assert Dispatcher(env.cfg(), out=lambda *a: None).budget == {}


# ---- helpers (task 1.2)

def test_budget_reached():
    now = time.time()
    assert budget_reached({"seven_day": reading(0.80)}, {"seven_day": 80}, now)[0] == "seven_day"
    assert budget_reached({"seven_day": reading(0.81)}, {"seven_day": 80}, now)[0] == "seven_day"
    assert budget_reached({"seven_day": reading(0.79)}, {"seven_day": 80}, now) is None
    assert budget_reached({"seven_day": reading(0.3, status="rejected")}, {"seven_day": 80}, now)[0] == "seven_day"
    assert budget_reached({"seven_day": reading(0.95, seconds=-5)}, {"seven_day": 80}, now) is None  # reset
    assert budget_reached({"five_hour": reading(0.99)}, {"seven_day": 80}, now) is None  # not budgeted
    both = {"five_hour": reading(0.99), "seven_day": reading(0.99)}
    assert budget_reached(both, {"seven_day": 80, "five_hour": 90}, now)[0] == "seven_day"  # budget order
    assert budget_reached(None, {"seven_day": 80}, now) is None


def test_held_windows_exempt():
    now = time.time()
    usage = {"five_hour": reading(0.91), "seven_day": reading(0.91)}
    assert [n for n, _ in held_windows(usage, 90, now)] == ["five_hour", "seven_day"]
    assert [n for n, _ in held_windows(usage, 90, now, {"seven_day"})] == ["five_hour"]
    assert held_windows({"seven_day": reading(0.2, status="rejected")}, 90, now, {"seven_day"}) == []


# ---- ending the run (task 1.3)

def test_budget_reached_after_a_session(env):
    with_task(env)
    reset = int(time.time()) + 86400
    env.set_claude([{"steps": [START, usage_step(seven_day=(0.81, reset))], "result": {}},
                    {"steps": [START], "result": {}}])
    lines = []
    assert disp(env, lines, seven_day=80).loop() == 0
    assert len(env.claude_calls()) == 1
    ev = log_events(env, "usage_budget_reached")
    assert len(ev) == 1 and (ev[0]["window"], ev[0]["utilization"], ev[0]["budget"]) == ("seven_day", 0.81, 80)
    end = [x for x in lines if "budget reached: seven_day" in x and "ending the run" in x]
    assert len(end) == 1 and "81% (budget 80%)" in end[0]


@pytest.mark.parametrize("once", [False, True])
def test_budget_already_reached_at_start(env, once):
    with_task(env)
    store(env, seven_day=(0.82, 86400))
    assert disp(env, seven_day=80).loop(once=once) == 0
    assert env.claude_calls() == [] and len(log_events(env, "usage_budget_reached")) == 1
    assert log_events(env, "usage_wait") == []


def test_below_budget_runs(env):
    with_task(env)
    store(env, seven_day=(0.78, 86400))
    env.set_claude([{"steps": [START], "result": {}}])
    assert disp(env, seven_day=80).loop(once=True) == 0
    assert len(env.claude_calls()) == 1 and log_events(env, "usage_budget_reached") == []


def test_unbudgeted_window_still_waits(env):
    with_task(env)
    store(env, five_hour=(0.91, 40 * 60), seven_day=(0.5, 86400))
    assert disp(env, seven_day=80).loop(once=True) == 0
    assert env.claude_calls() == []
    wait = log_events(env, "usage_wait")
    assert len(wait) == 1 and wait[0]["window"] == "five_hour"
    assert log_events(env, "usage_budget_reached") == []


def test_budgeted_window_above_threshold_not_held(env):
    with_task(env)
    store(env, seven_day=(0.91, 86400))
    env.set_claude([{"steps": [START], "result": {}}])
    assert disp(env, seven_day=95).loop(once=True) == 0
    assert len(env.claude_calls()) == 1 and log_events(env, "usage_wait") == []


def test_goal_run_ends_with_limit(env):
    with_task(env)
    reset = int(time.time()) + 86400
    env.set_claude([{"steps": [START, usage_step(seven_day=(0.80, reset))], "result": {}},
                    {"steps": [START], "result": {}}])
    d = disp(env, seven_day=80)
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    assert d.loop() == 6
    assert len(env.claude_calls()) == 1
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "limit" and "seven_day" in result["reason"] and "80%" in result["reason"]
    assert log_events(env, "goal_start")[0]["budget"] == {"seven_day": 80}


# ---- reporting (tasks 2.1, 2.2)

def test_start_line_and_log(env):
    store(env, seven_day=(0.77, 86400))
    lines = []
    disp(env, lines, seven_day=80).start_budget()
    assert lines == ["Usage budget for this run: seven_day up to 80% (now 77%)"]
    ev = log_events(env, "usage_budget")
    assert len(ev) == 1 and ev[0]["budget"] == {"seven_day": 80} and ev[0]["threshold"] == 90
    assert log_events(env, "usage_budget_warning") == []


def test_warning_above_threshold(env):
    lines = []
    disp(env, lines, seven_day=95).start_budget()
    assert lines[0] == "Usage budget for this run: seven_day up to 95% (now no current reading)"
    assert len(lines) == 2 and "! warning: seven_day budget 95% is above the global usage_pause_percent 90%" in lines[1]
    ev = log_events(env, "usage_budget_warning")
    assert len(ev) == 1 and (ev[0]["window"], ev[0]["budget"], ev[0]["threshold"]) == ("seven_day", 95, 90)


def test_no_budget_prints_nothing(env):
    lines = []
    disp(env, lines).start_budget()
    assert lines == [] and log_events(env, "usage_budget") == []


def test_crossing_uses_budget_per_window(env):
    with_task(env)
    reset = int(time.time()) + 86400
    env.set_claude([{"steps": [START, usage_step(seven_day=(0.79, reset), five_hour=(0.5, reset)),
                               usage_step(seven_day=(0.81, reset), five_hour=(0.5, reset)),
                               usage_step(seven_day=(0.82, reset), five_hour=(0.5, reset))], "result": {}}])
    lines = []
    disp(env, lines, seven_day=80).loop(once=True)
    crossing = [x for x in lines if "usage: seven_day" in x]
    assert len(crossing) == 1
    assert "81% - run budget reached - the run ends after this session (budget 80%)" in crossing[0]
    assert log_events(env, "usage_threshold")[0]["budget"] == 80


def test_no_crossing_below_budget_above_threshold(env):
    with_task(env)
    reset = int(time.time()) + 86400
    env.set_claude([{"steps": [START, usage_step(seven_day=(0.92, reset))], "result": {}}])
    lines = []
    disp(env, lines, seven_day=95).loop(once=True)
    assert not [x for x in lines if "usage: seven_day" in x] and log_events(env, "usage_threshold") == []


def test_dry_run_budget_reached(env, capsys):
    with_task(env)
    store(env, seven_day=(0.77, 86400))
    assert run(env, "dry-run", "--budget-7d", "75") == 0
    out = capsys.readouterr().out
    assert "budget: seven_day 77% >= 75% - the run would end without starting a step" in out
    assert run(env, "dry-run", "--budget-7d", "80") == 0
    assert "budget: below (seven_day 77% < 80%)" in capsys.readouterr().out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []
