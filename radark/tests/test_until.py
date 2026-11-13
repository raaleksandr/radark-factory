"""End time of a run: `--until`, ending the run between sessions, capped waits, reporting (run-until-time)."""
import datetime as dt
import json
import time

import pytest

import radark.__main__ as hm
from radark.__main__ import Dispatcher, main, parse_until, until_text
from radark.state import GoalRun
from radark.tests.conftest import START, item, show
from radark.tests.test_sleep import Watch, a_sleep

A = "HO-20261016-aaaa"
NOW = dt.datetime(2026, 10, 29, 22, 10)


def disp(env, lines=None, until=None, watch=None):
    d = Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)), watch=watch)
    d.until = until
    return d


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def with_task(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


def run(env, *args):
    return main(["--config", str(env.config_path), *args])


class Clock:
    """Fake wall clock for the dispatcher: `time.time()` stands still, `sleep` (when patched) moves it on."""

    def __init__(self, monkeypatch, sleep=False):
        self.t, self.naps = time.time(), []
        monkeypatch.setattr(hm.time, "time", lambda: self.t)
        if sleep:  # only without a session: the runner polls its process with time.sleep
            monkeypatch.setattr(hm.time, "sleep", self.sleep)

    def sleep(self, seconds):
        self.naps.append(seconds)
        self.t += seconds


def after_session(d, clock, seconds):
    """Move the clock on by `seconds` once each session has ended."""
    real = d.run_candidate

    def run_candidate(cand):
        r = real(cand)
        clock.t += seconds
        return r
    d.run_candidate = run_candidate


def goal_file(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    return path


# ---- parsing (task 1.1)

@pytest.mark.parametrize("text, now, expected", [
    ("07:00", NOW, dt.datetime(2026, 10, 30, 7, 0)),
    ("17:30", NOW.replace(hour=9, minute=0), dt.datetime(2026, 10, 29, 17, 30)),
    ("7:05", NOW.replace(hour=6), dt.datetime(2026, 10, 29, 7, 5)),
    ("22:10", NOW, dt.datetime(2026, 10, 30, 22, 10)),  # the current minute: tomorrow
    ("22:10", NOW.replace(second=30), dt.datetime(2026, 10, 30, 22, 10)),
    ("2026-10-31 08:00", NOW, dt.datetime(2026, 10, 31, 8, 0)),
    ("2026-10-31T08:00", NOW, dt.datetime(2026, 10, 31, 8, 0)),
])
def test_parse_until(text, now, expected):
    assert parse_until(text, now) == expected


@pytest.mark.parametrize("text", ["25:00", "12:60", "tomorrow", "7", "", "2026-13-01 08:00", "2026-10-29 22:10",
                                  "2026-10-28 08:00", "+3h"])
def test_parse_until_refused(text):
    assert parse_until(text, NOW) is None


# ---- option (task 1.2)

def test_valid_until_accepted(env, capsys):
    with_task(env)
    assert run(env, "dry-run", "--until", "2099-01-01 08:00") == 0
    assert "Would end: 08:00 on 2099-01-01" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["25:00", "tomorrow", "2020-01-01 08:00"])
@pytest.mark.parametrize("command", [["run"], ["run", "--goal", "goal.md"], ["dry-run"]])
def test_invalid_until_refused(env, capsys, value, command):
    with_task(env)
    goal_file(env)
    assert run(env, *command, "--until", value) == 2
    err = capsys.readouterr().err
    assert f"--until must be HH:MM or YYYY-MM-DD HH:MM (local time) in the future, not '{value}'." in err
    assert env.claude_calls() == [] and not (env.root / "run" / "lock").exists()


def test_until_not_stored(env):
    d = disp(env, until=time.time() + 3600)
    d.start_until()
    d.state.save()
    assert "until" not in json.dumps(d.state.meta)
    assert Dispatcher(env.cfg(), out=lambda *a: None).until is None


# ---- ending the run (task 1.3)

def test_end_time_reached_after_a_session(env, monkeypatch):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {}}, {"steps": [START], "result": {}}])
    clock = Clock(monkeypatch)
    lines = []
    d = disp(env, lines, until=clock.t + 600)
    after_session(d, clock, 720)
    assert d.loop() == 0
    assert len(env.claude_calls()) == 1
    at = dt.datetime.fromtimestamp(d.until)
    ev = log_events(env, "run_until_reached")
    assert len(ev) == 1 and ev[0]["until"] == at.isoformat(timespec="minutes")
    assert [x for x in lines if x.endswith(f"End time {at:%H:%M} reached; ending the run.")]


@pytest.mark.parametrize("once", [False, True])
def test_end_time_already_passed_at_start(env, once):
    with_task(env)
    assert disp(env, until=time.time() - 1).loop(once=once) == 0
    assert env.claude_calls() == [] and len(log_events(env, "run_until_reached")) == 1


def test_end_time_passed_while_the_computer_slept(env, monkeypatch):
    with_task(env)
    clock = Clock(monkeypatch)
    d = disp(env, until=clock.t + 3600, watch=Watch(a_sleep(6 * 3600)))
    clock.t += 6 * 3600
    assert d.loop() == 0
    assert env.claude_calls() == []
    assert len(log_events(env, "suspend")) == 1 and len(log_events(env, "run_until_reached")) == 1


def test_once_before_the_end_time_runs(env):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {}}])
    assert disp(env, until=time.time() + 3600).loop(once=True) == 0
    assert len(env.claude_calls()) == 1 and log_events(env, "run_until_reached") == []


def test_goal_run_ends_with_limit(env, monkeypatch):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {}}, {"steps": [START], "result": {}}])
    clock = Clock(monkeypatch)
    d = disp(env, until=clock.t + 600)
    after_session(d, clock, 900)
    d.start_goal(GoalRun(goal_file(env), "Finish B-1.", 40, 12))
    assert d.loop() == 6
    assert len(env.claude_calls()) == 1
    at = dt.datetime.fromtimestamp(d.until)
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "limit" and result["reason"] == f"end time {at:%Y-%m-%d %H:%M} reached"
    assert log_events(env, "goal_start")[0]["until"] == at.isoformat(timespec="minutes")


def test_earlier_max_hours_wins(env, monkeypatch):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {}}, {"steps": [START], "result": {}}])
    clock = Clock(monkeypatch)
    d = disp(env, until=clock.t + 5 * 3600)
    after_session(d, clock, 2.5 * 3600)
    d.start_goal(GoalRun(goal_file(env), "Finish B-1.", 40, 2))
    assert d.loop() == 6
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "limit" and result["reason"] == "the maximum duration of 2 h is reached"
    assert log_events(env, "run_until_reached") == []


# ---- capped waits (task 1.4)

def test_idle_poll_ends_at_the_end_time(env, monkeypatch):
    env.config_path.write_text(env.config_path.read_text().replace("poll_seconds = 0", "poll_seconds = 120"))
    clock = Clock(monkeypatch, sleep=True)
    d = disp(env, until=clock.t + 30)
    assert d.loop() == 0
    assert sum(clock.naps) <= 30 and max(clock.naps) <= 30
    assert env.claude_calls() == [] and len(log_events(env, "run_until_reached")) == 1


def test_usage_wait_past_the_end_time_ends_at_it(env, monkeypatch):
    with_task(env)
    clock = Clock(monkeypatch, sleep=True)
    d = disp(env, until=clock.t + 30 * 60)
    d.state.meta["usage"] = {"five_hour": {"utilization": 0.95, "resets_at": clock.t + 2 * 3600, "status": "allowed",
                                           "seen": "x"}}
    d.state.save()
    assert d.loop() == 0
    assert env.claude_calls() == [] and len(log_events(env, "usage_wait")) == 1
    assert sum(clock.naps) == pytest.approx(30 * 60) and len(log_events(env, "run_until_reached")) == 1


def test_pause_ends_at_the_end_time(env, monkeypatch):
    with_task(env)
    (env.root / "run").mkdir(exist_ok=True)
    (env.root / "run" / "PAUSE").write_text("")
    clock = Clock(monkeypatch, sleep=True)
    assert disp(env, until=clock.t + 12).loop() == 0
    assert sum(clock.naps) == pytest.approx(12) and env.claude_calls() == []


def test_nap_without_end_time_sleeps_in_full(env, monkeypatch):
    clock = Clock(monkeypatch, sleep=True)
    disp(env).nap(120)
    assert clock.naps == [120]


# ---- reporting (tasks 2.1, 2.2)

def test_until_text():
    now = NOW.timestamp()
    assert until_text(dt.datetime(2026, 10, 30, 7, 0).timestamp(), now) == "07:00 tomorrow (2026-10-30), in 8 h 50 min"
    assert until_text(dt.datetime(2026, 10, 29, 23, 0).timestamp(), now) == "23:00 today, in 50 min"
    assert until_text(dt.datetime(2026, 10, 31, 8, 0).timestamp(), now).startswith("08:00 on 2026-10-31, in ")


def test_start_line_and_log(env, monkeypatch):
    monkeypatch.setattr(hm.time, "time", lambda: NOW.timestamp())
    lines = []
    disp(env, lines, until=parse_until("07:00", NOW).timestamp()).start_until()
    assert lines == ["Run ends at 07:00 tomorrow (2026-10-30), in 8 h 50 min"]
    ev = log_events(env, "run_until")
    assert len(ev) == 1 and ev[0]["until"] == "2026-10-30T07:00"


def test_no_until_prints_nothing(env):
    lines = []
    disp(env, lines).start_until()
    assert lines == [] and log_events(env, "run_until") == []


def test_goal_start_without_until(env):
    disp(env).start_goal(GoalRun(goal_file(env), "Finish B-1.", 40, 12))
    assert log_events(env, "goal_start")[0]["until"] is None


def test_dry_run_line(env, capsys, monkeypatch):
    with_task(env)
    real = dt.datetime

    class Fixed(real):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(hm.dt, "datetime", Fixed)
    monkeypatch.setattr(hm.time, "time", lambda: NOW.timestamp())
    assert run(env, "run", "--dry-run", "--until", "07:00") == 0
    assert "Would end: 07:00 tomorrow (2026-10-30), in 8 h 50 min" in capsys.readouterr().out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []
