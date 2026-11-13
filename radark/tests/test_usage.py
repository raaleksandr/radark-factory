"""Usage reading, pre-start guard, reset-time wait and their console / log lines (change usage-limit-guard)."""
import json
import time

import pytest

import radark.__main__ as hm
from radark.__main__ import Dispatcher, main
from radark.tests.conftest import START, item, show, usage_step

A = "HO-20261016-aaaa"


def disp(env, lines=None):
    return Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))


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


def set_percent(env, value):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", f"[loop]\nusage_pause_percent = {value}"))


# ---- stored reading (task 2.2)

def test_reading_stored_merged_and_survives_restart(env):
    with_task(env)
    reset = int(time.time()) + 3600
    env.set_claude([{"steps": [START, usage_step(five_hour=(0.61, reset), seven_day=(0.34, reset + 99))],
                     "result": {}},
                    {"steps": [START, usage_step(five_hour=(0.65, reset))], "result": {}}])
    d = disp(env)
    d.loop(once=True)
    usage = d.state.meta["usage"]
    assert (usage["five_hour"]["utilization"], usage["five_hour"]["resets_at"]) == (0.61, reset)
    assert usage["seven_day"]["utilization"] == 0.34 and usage["five_hour"]["seen"]
    d.loop(once=True)
    usage = disp(env).state.meta["usage"]  # a new dispatcher on the same run dir
    assert usage["five_hour"]["utilization"] == 0.65 and usage["seven_day"]["utilization"] == 0.34


# ---- guard (task 3.1)

def test_guard_holds_at_91_percent_and_once_prints_it(env):
    with_task(env)
    store(env, five_hour=(0.91, 40 * 60))
    lines = []
    assert disp(env, lines).loop(once=True) == 0
    assert env.claude_calls() == []
    text = "\n".join(lines)
    assert "Usage: five_hour 91% used, resets" in text and "waiting 41 min" in text
    assert "guard: holding until" in text and "nothing run" in text
    wait = log_events(env, "usage_wait")
    assert len(wait) == 1 and wait[0]["cause"] == "threshold" and wait[0]["window"] == "five_hour"
    assert wait[0]["minutes"] == 41 and wait[0]["utilization"] == 0.91
    disp(env).loop(once=True)
    assert len(log_events(env, "usage_wait")) == 1  # logged once per wait


@pytest.mark.parametrize("windows", [dict(five_hour=(0.89, 3600)), dict(five_hour=(0.95, -10)), {}])
def test_guard_lets_the_step_run(env, windows):
    """89 %, a window past its reset, no reading at all."""
    with_task(env)
    if windows:
        store(env, **windows)
    env.set_claude([{"steps": [START], "result": {}}])
    disp(env).loop(once=True)
    assert len(env.claude_calls()) == 1 and log_events(env, "usage_wait") == []


def test_configured_threshold(env):
    set_percent(env, 80)
    with_task(env)
    store(env, five_hour=(0.82, 3600))
    disp(env).loop(once=True)
    assert env.claude_calls() == []


def test_rejected_status_holds_below_threshold(env):
    with_task(env)
    store(env, seven_day=(0.5, 3600, "rejected"))
    disp(env).loop(once=True)
    assert env.claude_calls() == []


def test_latest_reset_wins(env):
    with_task(env)
    store(env, five_hour=(0.95, 600), seven_day=(0.92, 7200))
    d = disp(env)
    d.loop(once=True)
    assert d.state.meta["usage_wait"]["window"] == "seven_day"
    assert d.state.meta["backoff_until"] == pytest.approx(time.time() + 7200 + 60, abs=5)


def test_owner_answer_is_held_too(env, monkeypatch):
    store(env, five_hour=(0.95, 600))
    d = disp(env)
    monkeypatch.setattr(d, "owner_answers", lambda: pytest.fail("checked owner answers while held"))
    assert d.loop(once=True) == 0


# ---- reset-time wait after a hit (task 3.2)

def test_usage_limit_with_known_reset(env):
    with_task(env)
    reset = int(time.time()) + 52 * 60
    env.set_claude([{"steps": [START, usage_step(five_hour=(0.99, reset), seven_day=(0.5, reset + 9999)),
                               {"hook": "StopFailure", "input": {"error": "rate_limit"}}], "exit": 1}])
    lines = []
    d = disp(env, lines)
    d.loop(once=True)
    assert d.state.meta["backoff_until"] == reset + 60 and "backoff_minutes" not in d.state.meta
    assert d.state.meta["usage_wait"]["cause"] == "limit_hit"
    assert any("! Usage limit hit: five_hour resets" in x for x in lines)
    assert log_events(env, "usage_wait")[0]["cause"] == "limit_hit"
    assert log_events(env, "usage_limit")[0]["window"] == "five_hour"
    calls = len(env.claude_calls())
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls


def test_usage_limit_prefers_window_not_allowed(env):
    d = disp(env)
    now = time.time()
    r = hm.SessionResult(run_id="r", session_id="s", team="app", handover=None, phase="apply", started="")
    r.usage = {"five_hour": {"utilization": 0.7, "resets_at": now + 600, "status": "allowed"},
               "seven_day": {"utilization": 0.4, "resets_at": now + 9000, "status": "rejected"}}
    d.start_backoff(r)
    assert d.state.meta["backoff_until"] == now + 9000 + 60


def test_usage_limit_with_stored_reset_only(env):
    store(env, five_hour=(0.97, 1800))
    d = disp(env)
    d.start_backoff()
    assert d.state.meta["backoff_until"] == pytest.approx(time.time() + 1860, abs=5)
    assert "backoff_minutes" not in d.state.meta


# ---- a running session is not cut (task 3.3)

def test_crossing_mid_session_finishes_then_holds(env):
    with_task(env)
    reset = int(time.time()) + 3600
    env.set_claude([{"steps": [START, usage_step(five_hour=(0.89, reset)), {"text": "working"},
                               usage_step(five_hour=(0.9, reset)), usage_step(five_hour=(0.93, reset)),
                               {"text": "done"}], "result": {"result": "Done."}}])
    lines = []
    d = disp(env, lines)
    d.loop(once=True)
    assert d.state.get(A)["sessions"][0]["outcome"] == "finished"
    crossing = [x for x in lines if "usage: five_hour" in x]
    assert len(crossing) == 1 and "90% - no new step after this session (resets" in crossing[0]
    ev = log_events(env, "usage_threshold")
    assert len(ev) == 1 and ev[0]["utilization"] == 0.9 and ev[0]["handover"] == A
    calls = len(env.claude_calls())
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls


# ---- console: reminder and resume (task 4.1)

def test_wait_then_resume_and_start(env, monkeypatch):
    monkeypatch.setattr(hm, "USAGE_MARGIN_S", 0)
    with_task(env)
    store(env, five_hour=(0.93, 1.5))
    env.set_claude([{"steps": [START], "result": {}}])
    lines = []
    d = disp(env, lines)
    d.stop_after_session = True  # return after the first session
    assert d.loop() == 0
    assert len(env.claude_calls()) == 1
    kinds = [e["event"] for e in log_events(env)]
    assert kinds.index("usage_wait") < kinds.index("usage_resume") < kinds.index("session_start")
    assert any("Usage window five_hour has reset; resuming." in x for x in lines)
    assert "usage_wait" not in d.state.meta


def test_hourly_reminder(env, monkeypatch):
    store(env, seven_day=(0.95, 3 * 86400))
    lines = []
    d = disp(env, lines)
    monkeypatch.setattr(hm.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        d.loop()
    assert len(lines) == 1 and "-" in lines[0].split("resets ")[1][:10]  # the date is shown: not today
    d._usage_note -= hm.USAGE_REMINDER_S
    with pytest.raises(KeyboardInterrupt):
        d.loop()
    assert len(lines) == 2 and "still waiting for the seven_day usage window" in lines[1]
    with pytest.raises(KeyboardInterrupt):
        d.loop()
    assert len(lines) == 2


# ---- dry-run (task 4.2)

def test_dry_run_shows_reading_and_verdict(env, capsys):
    with_task(env)
    store(env, five_hour=(0.72, 3600), seven_day=(0.40, 86400 * 3))
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Usage: five_hour 72% resets" in out and "Usage: seven_day 40% resets" in out
    assert "guard: next step would start" in out and "Would start: app" in out
    store(env, five_hour=(0.93, 3600))
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "guard: holding until" in out and "five_hour 93%" in out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []


def test_dry_run_without_reading(env, capsys):
    with_task(env)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Usage: no reading yet" in out and "guard: next step would start" in out
