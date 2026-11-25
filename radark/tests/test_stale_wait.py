"""A stored threshold wait follows the current run's thresholds (change threshold-wait-follows-run-budget), with fake
`ho` and `claude` and temporary folders only."""
import json
import time

import pytest

import radark.__main__ as hm
from radark.__main__ import Dispatcher, main, stale_threshold_wait
from radark.machine import Machine
from radark.tests.conftest import START, item, show

A = "HO-20261125-aaaa"
DAY = 86400


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


def set_loop(env, line):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", f"[loop]\n{line}"))


def stored(env, window, utilization, seconds=DAY, cause="threshold", backoff_extra=0.0, others=None):
    """The state of an earlier run: the reading of `window` (plus `others`) and a wait on it with `cause`."""
    d = disp(env)
    reset = time.time() + seconds
    d.state.meta["usage"] = {window: {"utilization": utilization, "resets_at": reset, "status": "allowed",
                                      "seen": "x"}}
    for name, (u, s) in (others or {}).items():
        d.state.meta["usage"][name] = {"utilization": u, "resets_at": time.time() + s, "status": "allowed",
                                       "seen": "x"}
    until = reset + hm.USAGE_MARGIN_S
    d.state.meta["backoff_until"] = until + backoff_extra
    d.state.meta["usage_wait"] = {"until": until, "window": window, "utilization": utilization, "cause": cause}
    d.state.save()
    return until


def state_meta(env):
    return disp(env).state.meta


# ---- helper (task 1.1)

def test_helper():
    now = time.time()
    usage = {"seven_day": {"utilization": 0.90, "resets_at": now + DAY, "status": "allowed"}}
    until = now + DAY + 60
    meta = {"backoff_until": until, "usage_wait": {"until": until, "window": "seven_day", "cause": "threshold"}}
    assert stale_threshold_wait(meta, usage, 90, {}, now) is None  # still at the threshold
    assert stale_threshold_wait(meta, usage, 95, {}, now)["window"] == "seven_day"  # raised threshold
    assert stale_threshold_wait(meta, usage, 90, {"seven_day": 95}, now)["window"] == "seven_day"  # budget
    assert stale_threshold_wait(meta, usage, 90, {"seven_day": 90}, now) is None  # budget reached: the run ends
    assert stale_threshold_wait({**meta, "backoff_until": until + 5}, usage, 95, {}, now) is None  # longer back-off
    assert stale_threshold_wait({**meta, "backoff_until": now - 1}, usage, 95, {}, now) is None  # wait over
    limit = {**meta, "usage_wait": {**meta["usage_wait"], "cause": "limit_hit"}}
    assert stale_threshold_wait(limit, usage, 95, {"seven_day": 95}, now) is None
    rejected = {"seven_day": {**usage["seven_day"], "status": "rejected"}}
    assert stale_threshold_wait(meta, rejected, 95, {}, now) is None
    assert stale_threshold_wait(meta, {}, 90, {}, now)["window"] == "seven_day"  # reset / no reading
    assert stale_threshold_wait({}, usage, 95, {}, now) is None


# ---- dropping (tasks 2.1 - 2.6)

def test_higher_budget_drops_the_wait(env):
    with_task(env)
    stored(env, "seven_day", 0.90)
    env.set_claude([{"steps": [START], "result": {}}])
    lines = []
    assert disp(env, lines, seven_day=95).loop(once=True) == 0
    assert len(env.claude_calls()) == 1
    meta = state_meta(env)
    assert "usage_wait" not in meta and meta.get("backoff_until", 0) <= time.time()
    line = [x for x in lines if "stored usage wait no longer applies" in x]
    assert len(line) == 1 and "seven_day 90% used is below 95% (run budget)" in line[0]
    assert not line[0].lstrip().startswith("!")
    ev = log_events(env, "usage_wait_dropped")
    assert len(ev) == 1
    assert (ev[0]["window"], ev[0]["utilization"], ev[0]["threshold"], ev[0]["budget"]) == ("seven_day", 0.9, 95, True)
    assert log_events(env, "usage_wait") == [] and log_events(env, "usage_resume") == []


def test_raised_threshold_drops_the_wait(env):
    with_task(env)
    set_loop(env, "usage_pause_percent = 95")
    stored(env, "five_hour", 0.91, seconds=3600)
    env.set_claude([{"steps": [START], "result": {}}])
    lines = []
    assert disp(env, lines).loop(once=True) == 0
    assert len(env.claude_calls()) == 1 and "usage_wait" not in state_meta(env)
    assert any("five_hour 91% used is below 95% (usage_pause_percent)" in x for x in lines)
    ev = log_events(env, "usage_wait_dropped")
    assert len(ev) == 1 and (ev[0]["threshold"], ev[0]["budget"]) == (95, False)


@pytest.mark.parametrize("once", [False, True])
def test_budget_still_reached_ends_the_run(env, once):
    with_task(env)
    until = stored(env, "seven_day", 0.95)
    assert disp(env, seven_day=95).loop(once=once) == 0
    assert env.claude_calls() == [] and len(log_events(env, "usage_budget_reached")) == 1
    assert state_meta(env)["usage_wait"]["until"] == until and log_events(env, "usage_wait_dropped") == []


def test_unbudgeted_window_still_at_the_threshold_keeps_the_wait(env):
    with_task(env)
    until = stored(env, "five_hour", 0.92, seconds=3600, others={"seven_day": (0.5, DAY)})
    assert disp(env, seven_day=95).loop(once=True) == 0
    assert env.claude_calls() == []
    meta = state_meta(env)
    assert meta["usage_wait"]["until"] == until and meta["backoff_until"] == until
    assert log_events(env, "usage_wait_dropped") == []


def test_limit_hit_wait_not_dropped(env):
    with_task(env)
    until = stored(env, "seven_day", 0.90, cause="limit_hit")
    lines = []
    assert disp(env, lines, seven_day=95).loop(once=True) == 0
    assert env.claude_calls() == [] and state_meta(env)["backoff_until"] == until
    assert log_events(env, "usage_wait_dropped") == []
    assert any("(cause limit_hit)" in x for x in lines)


def test_longer_back_off_kept(env):
    with_task(env)
    until = stored(env, "seven_day", 0.90, backoff_extra=600)
    assert disp(env, seven_day=95).loop(once=True) == 0
    assert env.claude_calls() == [] and state_meta(env)["backoff_until"] == until + 600
    assert log_events(env, "usage_wait_dropped") == []


def test_other_pipeline_hold_not_dropped(env, machine_home):
    with_task(env)
    other = Machine(machine_home, "pipeline-a/harness.toml")
    other.enter()
    hold_until = time.time() + 1800
    other.write_hold(hold_until, "seven_day")
    stored(env, "seven_day", 0.90)
    d = disp(env, seven_day=95)
    d.machine = Machine(machine_home, d.cfg.path, d.cfg.run_dir)
    d.machine.enter()
    assert d.loop(once=True) == 0
    assert env.claude_calls() == []
    meta = state_meta(env)
    assert meta["backoff_until"] == hold_until and meta["usage_wait"]["cause"] == "other_pipeline"


def test_parallel_loop_drops_the_wait(env):
    with_task(env)
    env.config_path.write_text(env.config_path.read_text() + "parallel_sessions = 2\n")
    stored(env, "seven_day", 0.90)
    env.set_claude([{"steps": [START], "result": {}}])
    lines = []
    assert disp(env, lines, seven_day=95).loop(once=True) == 0
    assert len(env.claude_calls()) == 1 and "usage_wait" not in state_meta(env)
    assert len(log_events(env, "usage_wait_dropped")) == 1


# ---- dry-run (task 2.7)

def test_dry_run_reports_a_stale_and_a_kept_wait(env, capsys):
    with_task(env)
    stored(env, "seven_day", 0.90)
    assert main(["--config", str(env.config_path), "dry-run", "--budget-7d", "95"]) == 0
    out = capsys.readouterr().out
    assert "guard: a stored threshold wait (seven_day, until" in out
    assert "no longer applies with this run's thresholds; next step would start" in out
    assert "usage_wait" in state_meta(env)  # dry-run writes nothing
    stored(env, "seven_day", 0.90, cause="limit_hit")
    assert main(["--config", str(env.config_path), "dry-run", "--budget-7d", "95"]) == 0
    assert "in usage-limit back-off until" in (out := capsys.readouterr().out) and "(cause limit_hit)" in out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []
