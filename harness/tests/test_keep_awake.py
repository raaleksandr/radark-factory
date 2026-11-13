"""Keeping the computer awake during a run: parsing, configuration, option, keeper thread, reporting
(keep-computer-awake)."""
import datetime as dt
import json
import os
import queue
import time

import pytest

import harness.__main__ as hm
from harness import config as config_mod
from harness.__main__ import Dispatcher, keep_awake_text, main
from harness.awake import KeepAwake, Keeper, parse_keep_awake, wanted
from harness.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
NOW = dt.datetime(2026, 10, 29, 14, 0)
FORMS = "off, on, HH:MM, YYYY-MM-DD HH:MM or HH:MM-HH:MM (local time)"


def at(day, hour, minute=0):
    return dt.datetime(2026, 10, day, hour, minute)


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def run(env, *args):
    return main(["--config", str(env.config_path), *args])


def with_task(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


def set_key(env, value):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", f"[loop]\nkeep_awake = {value}"))


class FakeKeeper:
    """Stands in for the keeper thread in `main`: records the setting, start and stop."""
    made = []

    def __init__(self, setting):
        self.setting, self.started, self.stopped = setting, False, False
        self.changes = queue.SimpleQueue()
        FakeKeeper.made.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


@pytest.fixture
def fake_keeper(monkeypatch):
    FakeKeeper.made = []
    monkeypatch.setattr(hm, "Keeper", FakeKeeper)
    monkeypatch.setattr(hm.os, "name", "nt")
    return FakeKeeper.made


# ---- parsing and the predicate (task 1.1)

@pytest.mark.parametrize("text, now, expected", [
    ("off", NOW, KeepAwake("off", text="off")),
    ("on", NOW, KeepAwake("on", text="on")),
    ("23:00", NOW, KeepAwake("until", until=at(29, 23), text="23:00")),
    ("07:00", at(29, 22, 10), KeepAwake("until", until=at(30, 7), text="07:00")),
    ("2026-11-01 08:00", NOW, KeepAwake("until", until=dt.datetime(2026, 11, 1, 8), text="2026-11-01 08:00")),
    ("2026-11-01T08:00", NOW, KeepAwake("until", until=dt.datetime(2026, 11, 1, 8), text="2026-11-01T08:00")),
    ("08:00-23:00", NOW, KeepAwake("range", start=dt.time(8), end=dt.time(23), text="08:00-23:00")),
    ("22:00-02:00", NOW, KeepAwake("range", start=dt.time(22), end=dt.time(2), text="22:00-02:00")),
    ("8:00-23:00", NOW, KeepAwake("range", start=dt.time(8), end=dt.time(23), text="08:00-23:00")),
])
def test_parse(text, now, expected):
    assert parse_keep_awake(text, now) == expected


@pytest.mark.parametrize("text", ["25:00", "soon", "23:00-23:00", "8-23", "2026-10-28 08:00", "08:00-24:00", ""])
def test_parse_refused(text):
    assert parse_keep_awake(text, NOW) is None


DAY = parse_keep_awake("08:00-23:00", NOW)
NIGHT = parse_keep_awake("22:00-02:00", NOW)


@pytest.mark.parametrize("setting, now, expected", [
    (KeepAwake("on"), NOW, True),
    (KeepAwake("off"), NOW, False),
    (KeepAwake("until", until=at(29, 23)), at(29, 22, 59), True),
    (KeepAwake("until", until=at(29, 23)), at(29, 23), False),
    (DAY, at(29, 12), True),
    (DAY, at(29, 7, 59), False),
    (DAY, at(29, 8), True),  # start edge: in
    (DAY, at(29, 22, 59), True),
    (DAY, at(29, 23), False),  # end edge: out
    (NIGHT, at(29, 1, 30), True),
    (NIGHT, at(29, 12), False),
    (NIGHT, at(29, 22), True),
    (NIGHT, at(29, 21, 59), False),
    (NIGHT, at(29, 2), False),
    (NIGHT, at(29, 1, 59), True),
])
def test_wanted(setting, now, expected):
    assert wanted(setting, now) is expected


# ---- configuration (task 1.2)

def test_config_default_off(env):
    assert env.cfg().keep_awake.mode == "off"


@pytest.mark.parametrize("value, mode", [('"off"', "off"), ('"on"', "on"), ('"22:00-02:00"', "range")])
def test_config_accepted(env, value, mode):
    set_key(env, value)
    assert env.cfg().keep_awake.mode == mode


@pytest.mark.parametrize("value", ['"23:00"', '"2099-01-01 08:00"', '"soon"', "true", "5"])
def test_config_refused(env, value):
    set_key(env, value)
    with pytest.raises(config_mod.ConfigError, match="loop.keep_awake must be off, on or HH:MM-HH:MM"):
        env.cfg()


# ---- option (task 1.3)

def test_bare_flag_is_on(env, capsys):
    with_task(env)
    assert run(env, "dry-run", "--keep-awake") == 0
    assert "Would keep awake: whole run" in capsys.readouterr().out


def test_valid_value(env, capsys):
    with_task(env)
    assert run(env, "dry-run", "--keep-awake", "2099-01-01 08:00") == 0
    assert "Would keep awake: until 08:00 on 2099-01-01" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["25:00", "soon", "23:00-23:00", "2020-01-01 08:00"])
@pytest.mark.parametrize("command", [["run"], ["run", "--once"], ["dry-run"]])
def test_invalid_value_refused(env, capsys, value, command):
    with_task(env)
    assert run(env, *command, "--keep-awake", value) == 2
    assert f"--keep-awake must be {FORMS}, not '{value}'." in capsys.readouterr().err
    assert env.claude_calls() == [] and not (env.root / "run" / "lock").exists()


def test_option_off_overrides_config(env, fake_keeper, capsys):
    set_key(env, '"on"')
    assert run(env, "run", "--once", "--keep-awake", "off") == 0
    assert fake_keeper == [] and log_events(env, "keep_awake_setting") == []
    assert "Keep awake" not in capsys.readouterr().out


def test_config_default_used(env, fake_keeper):
    set_key(env, '"08:00-23:00"')
    assert run(env, "run", "--once") == 0
    assert [k.setting.text for k in fake_keeper] == ["08:00-23:00"]


# ---- keeper thread (task 2.1)

class Fake:
    """A settable clock and a recorder of `set_state` calls."""

    def __init__(self, now):
        self.t, self.calls = now, []

    def now(self):
        return self.t

    def set_state(self, on):
        self.calls.append(on)


def changes(keeper):
    out = []
    while not keeper.changes.empty():
        out.append(keeper.changes.get())
    return out


def test_on_sets_once():
    f = Fake(NOW)
    k = Keeper(KeepAwake("on"), set_state=f.set_state, now=f.now)
    for _ in range(3):
        k.check()
        f.t += dt.timedelta(minutes=10)
    assert f.calls == [True] and changes(k) == []  # the first state is reported by the start line


def test_until_releases_at_the_moment():
    f = Fake(at(29, 22, 59))
    k = Keeper(parse_keep_awake("23:00", NOW), set_state=f.set_state, now=f.now)
    k.check()
    f.t = at(29, 23)
    k.check()
    f.t = at(29, 23, 30)
    k.check()
    assert f.calls == [True, False] and changes(k) == [(at(29, 23).timestamp(), False)]


def test_day_range_over_two_days():
    f = Fake(at(29, 20))
    k = Keeper(DAY, set_state=f.set_state, now=f.now)
    while f.t <= at(30, 10):
        k.check()
        f.t += dt.timedelta(seconds=30)
    assert f.calls == [True, False, True]
    assert changes(k) == [(at(29, 23).timestamp(), False), (at(30, 8).timestamp(), True)]


def test_thread_sets_and_stop_releases():
    f = Fake(NOW)
    k = Keeper(KeepAwake("on"), set_state=f.set_state, now=f.now, interval=0.01)
    k.start()
    deadline = time.monotonic() + 5
    while not f.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    k.stop()
    assert f.calls == [True, False] and k._thread is None


def test_stop_while_off_calls_nothing():
    f = Fake(at(29, 23, 30))
    k = Keeper(DAY, set_state=f.set_state, now=f.now, interval=0.01)
    k.start()
    time.sleep(0.05)
    k.stop()
    assert f.calls == []


def test_off_starts_no_thread():
    f = Fake(NOW)
    k = Keeper(KeepAwake("off"), set_state=f.set_state, now=f.now)
    k.start()
    assert k._thread is None
    k.stop()
    assert f.calls == []


# ---- wiring into the dispatcher (task 2.2)

class QueueDuringSession:
    """A sleep watch that, once a session runs, queues one keeper change, as the keeper thread would."""

    def __init__(self, d, change):
        self.d, self.change, self.done = d, change, False

    def check(self):
        if self.d._running is not None and not self.done:
            self.done = True
            self.d.keeper.changes.put(self.change)
        return None


def test_change_during_a_session_is_printed_and_logged(env):
    with_task(env)
    env.set_claude([{"steps": [START, {"sleep": 1}], "result": {}}])  # runner polls, and drains, every 0.2 s
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.keeper = FakeKeeper(KeepAwake("on"))
    change = (time.time() - 120, False)
    d.watch = QueueDuringSession(d, change)
    assert d.loop(once=True) == 0
    events = [e["event"] for e in log_events(env)]
    assert events.index("session_start") < events.index("keep_awake") < events.index("session_end")
    ev = log_events(env, "keep_awake")[0]
    assert ev["on"] is False and ev["at"] == hm.local_iso(change[0])
    assert f"{hm.stamp(change[0])}  Keep awake ended; the computer may sleep." in lines


def test_change_drained_at_the_start_of_the_loop(env):
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.keeper = FakeKeeper(DAY)
    d.keeper.changes.put((time.time(), True))
    assert d.loop(once=True) == 0
    assert lines[0].endswith("  Keep awake started.") and len(log_events(env, "keep_awake")) == 1


def test_stop_file_stops_the_keeper(env, fake_keeper):
    (env.root / "run").mkdir(exist_ok=True)
    (env.root / "run" / "STOP").write_text("")
    assert run(env, "run", "--keep-awake", "on") == 0
    assert len(fake_keeper) == 1 and fake_keeper[0].started and fake_keeper[0].stopped


def test_goal_limit_stops_the_keeper(env, fake_keeper):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {}}])
    goal = env.root / "goal.md"
    goal.write_text("Finish B-1.", encoding="utf-8")
    assert run(env, "run", "--goal", str(goal), "--max-sessions", "1", "--no-wait", "--keep-awake", "on") == 6
    assert fake_keeper[0].stopped
    assert log_events(env, "goal_start")[0]["keep_awake"] == "on"


def test_ctrl_c_stops_the_keeper(env, fake_keeper, monkeypatch):
    def interrupted(self, once=False):
        raise KeyboardInterrupt
    monkeypatch.setattr(Dispatcher, "loop", interrupted)
    assert run(env, "run", "--keep-awake", "on") == 130
    assert fake_keeper[0].stopped and not (env.root / "run" / "lock").exists()


# ---- not Windows (task 2.4)

def test_not_windows_one_line_and_no_thread(env, monkeypatch):
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.keep_awake = KeepAwake("on", text="on")
    with monkeypatch.context() as m:
        m.setattr(os, "name", "posix")
        d.start_keep_awake()
    assert d.keeper is None
    assert len(lines) == 1 and lines[0].endswith("  ! keeping the computer awake is not available on this system")


# ---- reporting (tasks 3.1, 3.2)

def start_lines(env, setting):
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.keep_awake = setting
    d.start_keep_awake()
    d.stop_keep_awake()
    return lines


def test_no_line_for_off(env):
    assert start_lines(env, KeepAwake()) == [] and log_events(env) == []


def test_start_line_whole_run(env, fake_keeper):
    assert start_lines(env, KeepAwake("on", text="on")) == ["Keep awake: whole run"]
    rec = log_events(env, "keep_awake_setting")[0]
    assert rec["mode"] == "on" and rec["text"] == "on" and rec["until"] is None
    assert fake_keeper[0].started and fake_keeper[0].stopped


def test_start_line_until(env, fake_keeper):
    setting = parse_keep_awake("23:00", dt.datetime.now())
    assert start_lines(env, setting)[0].startswith("Keep awake: until 23:00 ")
    assert log_events(env, "keep_awake_setting")[0]["until"] == setting.until.isoformat(timespec="minutes")


def test_until_text_at_14():
    assert keep_awake_text(parse_keep_awake("23:00", NOW), NOW.timestamp()) == "until 23:00 today, in 9 h 00 min"


def test_range_text_now_on_and_off():
    assert keep_awake_text(DAY, at(29, 14).timestamp()) == "daily 08:00-23:00 (now: on)"
    assert keep_awake_text(DAY, at(29, 23, 30).timestamp()) == "daily 08:00-23:00 (now: off, from 08:00)"


def test_start_line_range(env, fake_keeper):
    line = start_lines(env, DAY)[0]
    assert line.startswith("Keep awake: daily 08:00-23:00 (now: ")
    rec = log_events(env, "keep_awake_setting")[0]
    assert rec["mode"] == "range" and (rec["start"], rec["end"]) == ("08:00", "23:00")


def test_goal_start_records_off(env):
    goal = env.root / "goal.md"
    goal.write_text("Finish B-1.", encoding="utf-8")
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.start_goal(hm.GoalRun(goal, "Finish B-1.", 40, 12))
    assert log_events(env, "goal_start")[0]["keep_awake"] == "off"


def test_dry_run_range(env, capsys):
    with_task(env)
    assert run(env, "dry-run", "--keep-awake", "08:00-23:00") == 0
    out = capsys.readouterr().out
    assert "Would keep awake: daily 08:00-23:00 (now: " in out
    assert env.claude_calls() == []


def test_dry_run_without_the_option(env, capsys):
    with_task(env)
    assert run(env, "dry-run") == 0
    assert "keep awake" not in capsys.readouterr().out.lower()
