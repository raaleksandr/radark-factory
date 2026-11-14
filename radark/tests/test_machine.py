"""Machine-wide layer for several dispatcher instances on one computer (change machine-wide-instances), with fake `ho`
and `claude` and a temporary machine directory (`machine_home` in conftest)."""
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import radark.__main__ as hm
from radark import machine as machine_mod
from radark import prompts
from radark.__main__ import Dispatcher, main
from radark.awake import KeepAwake, Keeper
from radark.machine import FileLock, Limits, Machine, MachineError, load_limits, machine_dir, record_path, repo_key
from radark.runner import SessionResult, session_env
from radark.state import GoalRun
from radark.tests.conftest import START, item, show, usage_step, write_config

A = "HO-20261114-aaaa"
ROOT = Path(__file__).resolve().parents[2]  # the repository root: `-m radark` of a child process imports it
DONE = {"result": "Done."}


def log_events(run_dir: Path, kind=None):
    path = run_dir / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def with_task(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


def config_b(env, share_app: bool = False, app_path: str | None = None) -> Path:
    """A second pipeline: its own run directory, hub and repositories; `share_app` lists A's `app` repository."""
    root = env.root / "pipeline-b"
    root.mkdir(exist_ok=True)
    path = write_config(root)
    if share_app or app_path:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(str(root / "repos" / "app"), app_path or str(env.root / "repos" / "app")),
                        encoding="utf-8")
    return path


def instance(cfg, home: Path, enter: bool = True) -> Machine:
    m = Machine(home, cfg.path, cfg.run_dir)
    if enter:
        m.enter()
    return m


def dispatcher(cfg, home: Path, lines=None, enter: bool = True) -> Dispatcher:
    d = Dispatcher(cfg, out=(lines.append if lines is not None else (lambda *a: None)))
    d.machine = instance(cfg, home, enter)
    d.machine.report = d.machine_report
    return d


HOLD = """
import json, sys, time
sys.path.insert(0, sys.argv[3])
from pathlib import Path
from radark.machine import FileLock, record_path, write_record
p = Path(sys.argv[1])
lock = FileLock(p)
assert lock.acquire(10)
if sys.argv[2]:
    write_record(record_path(p), json.loads(sys.argv[2]))
print("ready", flush=True)
time.sleep(300)
"""


def hold_in_child(path: Path, record: dict | None = None) -> subprocess.Popen:
    """A process that holds the OS lock on `path` (and wrote its record) until it is killed."""
    proc = subprocess.Popen([sys.executable, "-c", HOLD, str(path), json.dumps(record) if record else "", str(ROOT)],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "ready"
    return proc


def kill(proc: subprocess.Popen) -> None:
    proc.kill()
    proc.wait(10)


# ---- machine directory, limits, locks (task 1.1)

def test_override_used(machine_home):
    assert machine_dir() == machine_home


def test_default_directory_per_platform(tmp_path):
    assert machine_dir({"LOCALAPPDATA": str(tmp_path)}, "nt") == tmp_path / "radark" / "machine"
    assert machine_dir({"XDG_STATE_HOME": str(tmp_path)}, "posix") == tmp_path / "radark" / "machine"
    assert machine_dir({}, "posix") == Path.home() / ".local" / "state" / "radark" / "machine"
    assert machine_dir({"RADARK_MACHINE_DIR": str(tmp_path / "x"), "LOCALAPPDATA": "y"}, "nt") == tmp_path / "x"


def test_limits_default_and_valid(machine_home):
    assert load_limits(machine_home) == Limits(2, 1)
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 3\n")
    assert load_limits(machine_home) == Limits(3, 1)
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 1\ntest_runs = 2\n")
    assert load_limits(machine_home) == Limits(1, 2)


@pytest.mark.parametrize("key", ["sessions", "test_runs"])
@pytest.mark.parametrize("value", ["0", "-1", '"two"', "true", "1.5"])
def test_limits_refused_naming_the_key(machine_home, key, value):
    (machine_home / "machine.toml").write_text(f"[machine]\n{key} = {value}\n")
    with pytest.raises(MachineError, match=rf"machine\.toml.*machine\.{key}"):
        load_limits(machine_home)


def test_later_invalid_limits_keep_last_valid_reported_once(machine_home):
    reports = []
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 3\n")
    m = Machine(machine_home, report=lambda event, text, **f: reports.append(event))
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 0\n")
    assert m.limits().sessions == 3 and m.limits().sessions == 3
    assert reports == ["machine_config_invalid"]
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 1\n")
    assert m.limits().sessions == 1


def test_lock_held_by_child_then_free_after_kill(machine_home):
    path = machine_home / "x.lock"
    proc = hold_in_child(path)
    try:
        assert not FileLock(path).try_acquire()
    finally:
        kill(proc)
    lock = FileLock(path)
    assert lock.acquire(5)
    lock.release()


def test_two_handles_of_one_process_conflict(machine_home):
    a, b = FileLock(machine_home / "y.lock"), FileLock(machine_home / "y.lock")
    assert a.try_acquire() and not b.try_acquire()
    a.release()
    assert b.try_acquire()
    b.release()


def test_stale_record_ignored_and_removed(machine_home):
    lock = machine_home / "instances" / "123-456.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    record_path(lock).write_text(json.dumps({"config": "pipeline-a/harness.toml", "pid": 123}))
    m = Machine(machine_home)
    assert m.instances() == []
    assert not record_path(lock).exists()


# ---- start checks (task 1.2)

def test_machine_directory_inside_repository_refused(env, monkeypatch, capsys):
    inside = env.root / "repos" / "app" / "machine"
    monkeypatch.setenv("RADARK_MACHINE_DIR", str(inside))
    assert main(["--config", str(env.config_path), "once"]) == 2
    err = capsys.readouterr().err
    assert str(inside) in err and "team repository" in err and env.claude_calls() == []


@pytest.mark.parametrize("command", ["once", "dry-run"])
def test_machine_directory_inside_run_directory_refused(env, monkeypatch, capsys, command):
    monkeypatch.setenv("RADARK_MACHINE_DIR", str(env.root / "run" / "machine"))
    assert main(["--config", str(env.config_path), command]) == 2
    assert "run directory" in capsys.readouterr().err


def test_unusable_machine_directory_refused(env, monkeypatch, capsys):
    blocker = env.root / "a-file"
    blocker.write_text("x")
    monkeypatch.setenv("RADARK_MACHINE_DIR", str(blocker / "machine"))
    assert main(["--config", str(env.config_path), "once"]) == 2
    assert "cannot be created or written" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["run", "once", "dry-run"])
def test_invalid_limits_refused(env, machine_home, capsys, command):
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 0\n")
    assert main(["--config", str(env.config_path), command]) == 2
    err = capsys.readouterr().err
    assert "machine.toml" in err and "sessions" in err and env.claude_calls() == []


# ---- instance record (task 1.3)

def test_instance_record_while_running_and_gone_after(env, machine_home):
    with_task(env)
    started, go = env.root / "started", env.root / "go"
    env.set_claude([{"steps": [START, {"touch": str(started)}, {"wait_for": str(go), "within": 30}], "result": DONE}])
    codes = []
    t = threading.Thread(target=lambda: codes.append(main(["--config", str(env.config_path), "once"])))
    t.start()
    try:
        deadline = time.time() + 30
        while not started.exists() and time.time() < deadline:
            time.sleep(0.05)
        records = [json.loads(p.read_text()) for p in (machine_home / "instances").glob("*.json")]
        assert len(records) == 1 and records[0]["config"] == str(env.cfg().path) and records[0]["sessions"] == 1
        assert records[0]["pid"] == os.getpid()
        repos = [json.loads(p.read_text()) for p in (machine_home / "repos").glob("*.json")]
        assert len(repos) == 3
    finally:
        go.touch()
        t.join(60)
    assert codes == [0]
    assert list((machine_home / "instances").glob("*.json")) == []
    assert list((machine_home / "repos").glob("*.json")) == []
    assert list((machine_home / "slots").glob("*.json")) == []


def test_killed_instance_reported_stale(machine_home):
    path = machine_home / "instances" / "999-1.lock"
    proc = hold_in_child(path, {"id": "999-1", "config": "pipeline-a/harness.toml", "pid": 999, "sessions": 1})
    try:
        assert [r["config"] for r in Machine(machine_home).instances()] == ["pipeline-a/harness.toml"]
    finally:
        kill(proc)
    assert Machine(machine_home).instances() == []
    assert not record_path(path).exists()


# ---- shared usage (task 2.1)

def test_reading_of_one_instance_holds_the_other(env, machine_home):
    with_task(env)
    reset = int(time.time()) + 3600
    env.set_claude([{"steps": [START, usage_step(five_hour=(0.92, reset))], "result": DONE}])
    a = dispatcher(env.cfg(), machine_home)
    a.loop(once=True)
    assert json.loads((machine_home / "usage.json").read_text())["windows"]["five_hour"]["utilization"] == 0.92
    calls = len(env.claude_calls())
    lines = []
    b = dispatcher(hm.config_mod.load(config_b(env)), machine_home, lines)
    assert b.loop(once=True) == 0
    assert len(env.claude_calls()) == calls
    assert any("Usage: five_hour 92% used" in x for x in lines)


def test_reading_written_during_the_session(env, machine_home):
    """Another instance sees the reading while the session still runs, not only after it."""
    with_task(env)
    reset, seen = int(time.time()) + 3600, env.root / "seen"
    env.set_claude([{"steps": [START, usage_step(five_hour=(0.55, reset)), {"wait_for": str(seen), "within": 30}],
                     "result": DONE}])
    a = dispatcher(env.cfg(), machine_home)
    t = threading.Thread(target=lambda: a.loop(once=True))
    t.start()
    try:
        deadline, found = time.time() + 30, None
        while found is None and time.time() < deadline:
            try:
                found = json.loads((machine_home / "usage.json").read_text())["windows"]["five_hour"]
            except (OSError, ValueError, KeyError):
                time.sleep(0.05)
        assert found and found["utilization"] == 0.55
    finally:
        seen.touch()
        t.join(60)


def test_budget_against_the_shared_reading(env, machine_home):
    with_task(env)
    a = instance(env.cfg(), machine_home)
    a.merge_usage({"five_hour": {"utilization": 0.72, "resets_at": time.time() + 3600, "status": "allowed"}})
    lines = []
    b = dispatcher(hm.config_mod.load(config_b(env)), machine_home, lines)
    b.budget = {"five_hour": 70}
    assert b.loop(once=True) == 0 and env.claude_calls() == []
    assert log_events(b.cfg.run_dir, "usage_budget_reached")[0]["utilization"] == 0.72
    assert any("Usage budget reached: five_hour 72%" in x for x in lines)


def test_newest_reading_wins_per_window(env, machine_home):
    d = dispatcher(env.cfg(), machine_home)
    m = d.machine
    reset = time.time() + 3600
    m.merge_usage({"five_hour": {"utilization": 0.5, "resets_at": reset}}, seen_ts=time.time() - 100)
    m.merge_usage({"five_hour": {"utilization": 0.4, "resets_at": reset}}, seen_ts=time.time() - 200)  # older
    assert json.loads((machine_home / "usage.json").read_text())["windows"]["five_hour"]["utilization"] == 0.5
    d.state.meta["usage"] = {"five_hour": {"utilization": 0.3, "resets_at": reset, "status": None,
                                           "seen": hm.now_ts()},
                             "seven_day": {"utilization": 0.2, "resets_at": reset, "status": None,
                                           "seen": "2020-01-01T00:00:00.000Z"}}
    m.merge_usage({"seven_day": {"utilization": 0.6, "resets_at": reset}})
    usage = d.effective_usage()
    assert usage["five_hour"]["utilization"] == 0.3  # own reading is newer
    assert usage["seven_day"]["utilization"] == 0.6  # the machine reading is newer


def test_usage_lock_timeout_falls_back_and_logs_once(env, machine_home, monkeypatch):
    monkeypatch.setattr(machine_mod, "USAGE_LOCK_S", 0.2)
    lines = []
    d = dispatcher(env.cfg(), machine_home, lines)
    d.state.meta["usage"] = {"five_hour": {"utilization": 0.3, "resets_at": time.time() + 600, "status": None,
                                           "seen": hm.now_ts()}}
    busy = FileLock(machine_home / "usage.lock")
    assert busy.try_acquire()
    try:
        assert d.effective_usage()["five_hour"]["utilization"] == 0.3
        assert d.effective_usage()["five_hour"]["utilization"] == 0.3
    finally:
        busy.release()
    assert len(log_events(d.cfg.run_dir, "machine_usage_unavailable")) == 1
    assert sum("shared usage record" in x for x in lines) == 1


# ---- shared hold after a usage-limit hit (task 2.2)

def limit_result(usage=None):
    r = SessionResult(run_id="r", session_id="s", team="app", handover=None, phase="apply", started="")
    r.usage = usage or {}
    return r


def test_limit_hit_with_known_reset_holds_the_other(env, machine_home):
    reset = time.time() + 1800
    a = dispatcher(env.cfg(), machine_home)
    a.start_backoff(limit_result({"five_hour": {"utilization": 1.0, "resets_at": reset, "status": "rejected"}}))
    hold = json.loads((machine_home / "usage.json").read_text())["hold"]
    assert hold["until"] == reset + 60 and hold["window"] == "five_hour" and hold["by"] == a.machine.id
    with_task(env)
    lines = []
    b = dispatcher(hm.config_mod.load(config_b(env)), machine_home, lines)
    assert b.loop(once=True) == 0 and env.claude_calls() == []
    assert b.state.meta["backoff_until"] == reset + 60 and "backoff_minutes" not in b.state.meta
    assert any("Usage limit hit: five_hour resets" in x and "(hit in another pipeline)" in x for x in lines)
    assert log_events(b.cfg.run_dir, "usage_wait")[0]["cause"] == "other_pipeline"


def test_limit_hit_with_unknown_reset_holds_until_the_back_off_end(env, machine_home):
    a = dispatcher(env.cfg(), machine_home)
    a.start_backoff(limit_result())
    until = a.state.meta["backoff_until"]
    assert json.loads((machine_home / "usage.json").read_text())["hold"]["until"] == until
    lines = []
    b = dispatcher(hm.config_mod.load(config_b(env)), machine_home, lines)
    b.usage_hold()
    assert b.state.meta["backoff_until"] == until and "backoff_minutes" not in b.state.meta
    assert any("no new session for" in x and "(hit in another pipeline)" in x for x in lines)


def test_other_pipeline_starts_after_the_hold(env, machine_home):
    with_task(env)
    a = instance(env.cfg(), machine_home)
    until = time.time() + 2
    a.write_hold(until, "five_hour")
    env.set_claude([{"steps": [START, {"touch": str(env.root / "pipeline-b" / "run" / "STOP")}], "result": DONE}])
    lines = []
    b = dispatcher(hm.config_mod.load(config_b(env)), machine_home, lines)
    assert b.loop() == 0
    assert len(env.claude_calls()) == 1 and time.time() >= until
    assert any("(hit in another pipeline)" in x for x in lines)
    assert any("has reset; resuming" in x for x in lines)


def test_own_hold_is_not_waited_twice(env, machine_home):
    a = dispatcher(env.cfg(), machine_home)
    a.start_backoff(limit_result())
    first = a.state.meta["backoff_until"]
    a.usage_hold()
    assert a.state.meta["backoff_until"] == first and a.state.meta["backoff_minutes"] == a.cfg.usage_backoff_minutes


# ---- machine session limit (tasks 3.1, 3.2, 3.3)

def fill(home: Path, n: int = 2) -> Machine:
    """Pipeline A (another instance) running `n` sessions."""
    other = Machine(home, "pipeline-a/harness.toml")
    other.enter()
    for _ in range(n):
        assert other.try_session_slot() is not None
    return other


def test_second_pipeline_waits_and_starts_after_a_slot_frees(env, machine_home):
    other = fill(machine_home, 2)
    first = next(iter(other.slots))
    with_task(env)
    env.set_claude([{"steps": [START], "result": DONE}])
    lines = []
    b = dispatcher(env.cfg(), machine_home, lines)
    t = threading.Thread(target=lambda: b.loop(once=True))
    t.start()
    time.sleep(2.5)
    try:
        assert env.claude_calls() == []
        assert sum("machine limit: 2 sessions running in other pipelines" in x for x in lines) == 1
        assert log_events(b.cfg.run_dir, "machine_wait")[0] == {**log_events(b.cfg.run_dir, "machine_wait")[0],
                                                                 "limit": 2, "own": 0, "other": 2}
    finally:
        other.release_session_slot(first)
        t.join(60)
    assert len(env.claude_calls()) == 1
    assert any("machine slot free - starting" in x for x in lines)
    assert log_events(b.cfg.run_dir, "machine_wait_end")
    assert b.machine.slots == {}
    other.close()


def test_second_pipeline_starts_when_the_other_slot_frees(env, machine_home):
    other = fill(machine_home, 2)
    last = sorted(other.slots)[-1]
    with_task(env)
    env.set_claude([{"steps": [START], "result": DONE}])
    b = dispatcher(env.cfg(), machine_home)
    t = threading.Thread(target=lambda: b.loop(once=True))
    t.start()
    time.sleep(1.5)
    assert env.claude_calls() == []
    other.release_session_slot(last)
    t.join(60)
    assert len(env.claude_calls()) == 1
    other.close()


def test_limit_caps_the_sum(env, machine_home):
    env.config_path.write_text(env.config_path.read_text() + "parallel_sessions = 2\n")
    other = fill(machine_home, 1)
    lines = []
    a = dispatcher(env.cfg(), machine_home, lines)
    assert a.machine_slot() is not None  # its first session
    assert a.machine_slot() is None
    assert any("machine limit: 2 sessions running (1 in this pipeline, 1 in other pipelines)" in x for x in lines)
    assert log_events(a.cfg.run_dir, "machine_wait")[-1]["own"] == 1
    other.close()
    assert a.machine_slot() is not None
    assert any("machine slot free - starting" in x for x in lines)


@pytest.mark.parametrize("scenario", [
    {"steps": [START], "result": None, "exit": 1},  # error
    {"steps": [START, {"hook": "StopFailure", "input": {"error": "rate_limit"}}], "exit": 1},  # usage limit
])
@pytest.mark.parametrize("n", [1, 2])
def test_slot_released_after_error_and_usage_limit(env, machine_home, scenario, n):
    env.config_path.write_text(env.config_path.read_text() + f"parallel_sessions = {n}\n")
    with_task(env)
    env.set_claude([scenario])
    d = dispatcher(env.cfg(), machine_home)
    d.loop(once=True)
    assert len(env.claude_calls()) == 1
    assert d.machine.slots == {} and list((machine_home / "slots").glob("*.json")) == []


def test_slot_released_after_an_interruption(env, machine_home):
    with_task(env)
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": DONE}])
    d = dispatcher(env.cfg(), machine_home)
    t = threading.Thread(target=lambda: d.loop(once=True))
    t.start()
    deadline = time.time() + 30
    while not d.machine.slots and time.time() < deadline:
        time.sleep(0.05)
    while d.get_runner().proc is None and time.time() < deadline:
        time.sleep(0.05)
    d.stop_after_session = True
    d.get_runner().kill()
    t.join(60)
    assert d.machine.slots == {}


def test_stop_during_the_machine_wait(env, machine_home):
    other = fill(machine_home, 2)
    with_task(env)
    d = dispatcher(env.cfg(), machine_home)
    t = threading.Thread(target=lambda: d.loop())
    t.start()
    time.sleep(1.5)
    (env.root / "run" / "STOP").touch()
    t.join(30)
    assert not t.is_alive() and env.claude_calls() == []
    other.close()


def test_goal_check_waits_without_stalling(env, machine_home):
    other = fill(machine_home, 2)
    goal = env.root / "goal.md"
    goal.write_text("Ship it.", encoding="utf-8")
    d = dispatcher(env.cfg(), machine_home)
    d.start_goal(GoalRun(goal, "Ship it.", 10, 1.0))
    codes = []
    t = threading.Thread(target=lambda: codes.append(d.loop()))
    t.start()
    time.sleep(3)
    (env.root / "run" / "STOP").touch()
    t.join(30)
    assert codes == [0] and env.claude_calls() == []
    assert d.goal.empty_continues == 0 and d.goal.status == "stopped"
    other.close()


def test_lone_instance_never_waits(env, machine_home):
    with_task(env)
    env.set_claude([{"steps": [START], "result": DONE}])
    assert main(["--config", str(env.config_path), "once"]) == 0
    assert len(env.claude_calls()) == 1
    assert log_events(env.root / "run", "machine_wait") == []


# ---- one repository, one instance (tasks 4.1, 4.2)

def test_shared_repository_refused(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    assert a.claim_repos(hm.repos_of(env.cfg())) is None
    path_b = config_b(env, share_app=True)
    assert main(["--config", str(path_b), "once"]) == 2
    err = capsys.readouterr().err
    assert os.path.realpath(env.root / "repos" / "app") in err and str(env.cfg().path) in err
    assert "is in use by another running pipeline" in err and f"PID {os.getpid()}" in err
    assert not (env.root / "pipeline-b" / "run" / "lock").exists() and env.claude_calls() == []
    assert [p.stem for p in (machine_home / "instances").glob("*.json")] == [a.id]
    assert len(list((machine_home / "repos").glob("*.json"))) == 3  # only A's claims
    a.close()


def test_two_teams_of_one_configuration_share_a_repository(machine_home, tmp_path):
    m = Machine(machine_home)
    repo = tmp_path / "repo"
    repo.mkdir()
    assert m.claim_repos([repo, repo, tmp_path / "repo" / ".." / "repo"]) is None
    assert len(m.repos) == 1
    m.close()


def test_relative_path_is_the_same_repository(machine_home, tmp_path, monkeypatch):
    (tmp_path / "repo").mkdir()
    monkeypatch.chdir(tmp_path)
    assert repo_key(Path("repo")) == repo_key(tmp_path / "repo")


@pytest.mark.skipif(os.name != "nt", reason="letter case of paths matters only on Windows")
def test_other_letter_case_refused_on_windows(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    assert a.claim_repos(hm.repos_of(env.cfg())) is None
    path_b = config_b(env, app_path=str(env.root / "repos" / "app").upper())
    assert main(["--config", str(path_b), "once"]) == 2
    assert "is in use by another running pipeline" in capsys.readouterr().err
    a.close()


def test_killed_holder_does_not_block(env, machine_home):
    repo = env.root / "repos" / "app"
    proc = hold_in_child(machine_home / "repos" / f"{repo_key(repo)}.lock",
                         {"repo": str(repo), "config": "pipeline-a/harness.toml", "instance": "1-1", "pid": 1})
    path_b = config_b(env, share_app=True)
    try:
        assert main(["--config", str(path_b), "once"]) == 2
    finally:
        kill(proc)
    assert main(["--config", str(path_b), "once"]) == 0


def test_dry_run_shows_the_conflict(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    a.claim_repos(hm.repos_of(env.cfg()))
    a.try_session_slot()
    with_task(env)
    path_b = config_b(env, share_app=True)
    assert main(["--config", str(path_b), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert (f"! repository {os.path.realpath(env.root / 'repos' / 'app')} is in use by another running pipeline "
            f"({env.cfg().path}); run would refuse") in out
    assert f"Other pipeline running: {env.cfg().path} (1 session running)" in out
    assert "Machine: " in out and "limits 2 sessions, 1 test run" in out and "Machine slot: free" in out
    assert "Would start: app" in out
    assert len(list((machine_home / "instances").glob("*.json"))) == 1
    a.close()


def test_dry_run_machine_slot_none_free(env, machine_home, capsys):
    other = fill(machine_home, 2)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert "Machine slot: none free (2 running in other pipelines) - would wait" in capsys.readouterr().out
    other.close()


# ---- test-run slot (task 5.1)

SLOT_CMD = ("import sys, time; f = open(sys.argv[1], 'a'); f.write(f'start {time.time()}\\n'); f.flush(); "
            "time.sleep(float(sys.argv[2])); f.write(f'end {time.time()}\\n'); f.close(); sys.exit(int(sys.argv[3]))")


def slot_process(home: Path, out: Path, seconds: float = 1.5, code: int = 0, extra_env=None):
    env = {**os.environ, "RADARK_MACHINE_DIR": str(home), **(extra_env or {})}
    env.pop("HARNESS_TEST_SLOT_HELD", None)
    if extra_env and "HARNESS_TEST_SLOT_HELD" in extra_env:
        env["HARNESS_TEST_SLOT_HELD"] = extra_env["HARNESS_TEST_SLOT_HELD"]
    return subprocess.Popen([sys.executable, "-m", "radark", "test-slot", "--", sys.executable, "-c", SLOT_CMD,
                             str(out), str(seconds), str(code)], cwd=str(ROOT), env=env, stderr=subprocess.PIPE,
                            text=True)




def times(path: Path) -> dict[str, float]:
    return {line.split()[0]: float(line.split()[1]) for line in path.read_text().splitlines()}


def test_two_test_runs_one_after_the_other(machine_home, tmp_path):
    first = slot_process(machine_home, tmp_path / "a.txt")
    deadline = time.time() + 20
    while not (tmp_path / "a.txt").exists() and time.time() < deadline:
        time.sleep(0.05)
    second = slot_process(machine_home, tmp_path / "b.txt", seconds=0.1)
    assert first.wait(60) == 0 and second.wait(60) == 0
    a, b = times(tmp_path / "a.txt"), times(tmp_path / "b.txt")
    assert b["start"] >= a["end"]
    assert "radark-test-slot: waiting - 1 test run in progress on this computer" in second.stderr.read()
    assert list((machine_home / "slots").glob("test-*.json")) == []


def test_two_test_runs_at_once_with_limit_two(machine_home, tmp_path):
    (machine_home / "machine.toml").write_text("[machine]\ntest_runs = 2\n")
    first = slot_process(machine_home, tmp_path / "a.txt", seconds=3)
    second = slot_process(machine_home, tmp_path / "b.txt", seconds=3)
    assert first.wait(60) == 0 and second.wait(60) == 0
    a, b = times(tmp_path / "a.txt"), times(tmp_path / "b.txt")
    assert b["start"] < a["end"] and a["start"] < b["end"]


def test_exit_code_passed_through_and_slot_free(machine_home, tmp_path):
    assert slot_process(machine_home, tmp_path / "a.txt", seconds=0, code=1).wait(60) == 1
    lock = FileLock(machine_home / "slots" / "test-1.lock")
    assert lock.try_acquire()
    lock.release()


def test_nested_call_does_not_wait(machine_home, tmp_path):
    held = FileLock(machine_home / "slots" / "test-1.lock")
    assert held.try_acquire()
    try:
        proc = slot_process(machine_home, tmp_path / "a.txt", seconds=0,
                                 extra_env={"HARNESS_TEST_SLOT_HELD": "1"})
        assert proc.wait(30) == 0 and "waiting" not in proc.stderr.read()
    finally:
        held.release()


def test_command_that_cannot_start(machine_home, capsys):
    assert machine_mod.run_test_slot(["--", "no-such-command-radark-xyz"], poll=0.1) == 127
    assert "cannot start" in capsys.readouterr().err


def test_killed_test_slot_frees_its_slot(machine_home, tmp_path):
    proc = slot_process(machine_home, tmp_path / "a.txt", seconds=60)
    deadline = time.time() + 20
    while not (tmp_path / "a.txt").exists() and time.time() < deadline:
        time.sleep(0.05)
    lock = FileLock(machine_home / "slots" / "test-1.lock")
    assert not lock.try_acquire()
    kill(proc)  # the command it started may live on; the slot is the wrapper's
    assert lock.acquire(10)
    lock.release()


def test_session_env_has_the_machine_and_the_wrapper(env, machine_home):
    cfg = env.cfg()
    e = session_env({"PATH": "/usr/bin", "RADARK_MACHINE_DIR": str(machine_home)}, cfg, "app", A, "s", "r")
    assert e["RADARK_MACHINE_DIR"] == os.path.realpath(machine_home)
    assert e["HARNESS_TEST_SLOT"] == str(machine_mod.wrapper_path(cfg.run_dir))
    assert e["PATH"] == str(cfg.run_dir / "bin") + os.pathsep + "/usr/bin"


def test_wrappers_written_when_changed(tmp_path):
    path = machine_mod.write_wrappers(tmp_path, python="/opt/py")
    cmd, sh = tmp_path / "bin" / "radark-test-slot.cmd", tmp_path / "bin" / "radark-test-slot"
    assert path.name == ("radark-test-slot.cmd" if os.name == "nt" else "radark-test-slot")
    assert cmd.read_text() .strip() == '@"/opt/py" -P -m radark test-slot %*'
    assert '"/opt/py" -P -m radark test-slot "$@"' in sh.read_text()
    before = cmd.stat().st_mtime_ns
    time.sleep(0.02)
    machine_mod.write_wrappers(tmp_path, python="/opt/py")
    assert cmd.stat().st_mtime_ns == before


def note_prompt(env, machine_home, n: int, other: bool) -> str:
    env.config_path.write_text(env.config_path.read_text() + f"parallel_sessions = {n}\n")
    a = fill(machine_home, 0) if other else None
    d = dispatcher(env.cfg(), machine_home)
    try:
        return d.parallel_note()
    finally:
        if a:
            a.close()


@pytest.mark.parametrize("n, other, expected", [(1, False, False), (2, False, True), (1, True, True)])
def test_test_slot_note(env, machine_home, n, other, expected):
    assert (prompts.TEST_SLOT_NOTE in note_prompt(env, machine_home, n, other)) == expected


def test_test_slot_note_in_the_work_prompt(env, machine_home):
    other = fill(machine_home, 0)
    with_task(env)
    env.set_claude([{"steps": [START], "result": DONE}])
    d = dispatcher(env.cfg(), machine_home)
    d.loop(once=True)
    prompt = env.claude_calls()[0]["argv"][env.claude_calls()[0]["argv"].index("-p") + 1]
    assert prompts.TEST_SLOT_NOTE in prompt and prompts.PARALLEL_NOTE not in prompt
    other.close()


# ---- keep-awake with two instances (task 5.2)

def test_two_keepers_clear_only_their_own_request():
    calls = {"a": [], "b": []}
    now = lambda: dt.datetime(2026, 11, 14, 12, 0)
    a = Keeper(KeepAwake("on"), set_state=calls["a"].append, now=now, interval=0.01)
    b = Keeper(KeepAwake("on"), set_state=calls["b"].append, now=now, interval=0.01)
    a.start()
    b.start()
    deadline = time.monotonic() + 5
    while not (calls["a"] and calls["b"]) and time.monotonic() < deadline:
        time.sleep(0.01)
    a.stop()
    assert calls == {"a": [True, False], "b": [True]}
    b.stop()
    assert calls["b"] == [True, False]


# ---- visibility (task 6.1)

def test_status_lists_the_other_pipeline(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    a.try_session_slot()
    a.merge_usage({"five_hour": {"utilization": 0.57, "resets_at": time.time() + 3600, "status": "allowed"}})
    path_b = config_b(env)
    assert main(["--config", str(path_b), "status"]) == 0
    out = capsys.readouterr().out
    assert f"Machine directory: {machine_home}" in out
    assert "Limits: 2 sessions, 1 test run" in out
    assert f"  {env.cfg().path} (PID {os.getpid()}, started " in out and "1 session running)" in out
    assert "Session slots in use: 1/2" in out and "Test-run slots in use: 0/1" in out
    assert "Usage: five_hour 57% resets" in out
    assert f"Repository conflicts of {path_b}: none" in out
    for hidden in (A, "app", "backend", "Task"):  # no handover, team or title of A
        assert hidden not in out.replace(str(env.root), "")
    a.close()


def test_status_without_configuration_and_with_invalid_limits(env, machine_home, capsys):
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 0\n")
    assert main(["--config", str(env.root / "missing.toml"), "status"]) == 2
    out = capsys.readouterr().out
    assert "Limits: error:" in out and "repository conflicts are not checked" in out


def test_status_after_a_killed_instance(env, machine_home, capsys):
    path = machine_home / "instances" / "999-1.lock"
    proc = hold_in_child(path, {"id": "999-1", "config": "pipeline-a/harness.toml", "pid": 999, "sessions": 1})
    assert main(["--config", str(env.config_path), "status"]) == 0
    assert "pipeline-a/harness.toml" in capsys.readouterr().out
    kill(proc)
    assert main(["--config", str(env.config_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "pipeline-a/harness.toml" not in out and "Running pipelines: none" in out


def test_status_shows_a_conflict_and_the_hold(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    a.claim_repos(hm.repos_of(env.cfg()))
    a.write_hold(time.time() + 600, "five_hour")
    path_b = config_b(env, share_app=True)
    assert main(["--config", str(path_b), "status"]) == 0
    out = capsys.readouterr().out
    assert "is in use by another running pipeline" in out
    assert "Usage hold: no new session until" in out
    a.close()


def test_start_line_names_the_other_pipeline(env, machine_home, capsys):
    a = instance(env.cfg(), machine_home)
    a.try_session_slot()
    path_b = config_b(env)
    assert main(["--config", str(path_b), "once"]) == 0
    out = capsys.readouterr().out
    assert "limits 2 sessions, 1 test run" in out
    assert f"Other pipeline running: {env.cfg().path} (1 session running)" in out
    a.close()
