"""The cockpit's Now tab (change cockpit-now): the read-only lock probe, the instance scan and the cards as pure
functions on invented instance records, `goal.json` and run logs in a temporary machine directory, and `GET /api/now`
through the part-1 server harness with fake `ho`. Invented IDs and neutral names only; no browser."""
import datetime as dt
import json
import os
import re
from pathlib import Path

import pytest

from radark import cockpit
from radark import cockpit_history as ch
from radark import cockpit_now as cn
from radark import config as config_mod
from radark import machine as machine_mod
from radark.machine import FileLock, probe_readonly, record_path, write_record
from radark.tests.test_cockpit import WRITES, named, page_source, second_pipeline, start  # noqa: F401
from radark.tests.test_cockpit_history import boot, end_rec, snapshot, start_rec, write_log
from radark.tests.test_machine import hold_in_child, kill

A, B, C = (f"HO-20990101-{x * 4}" for x in "abc")
NOW = dt.datetime(2099, 1, 10, 12, 0, tzinfo=dt.timezone.utc)


def at(hh: int, mm: int = 0, day: int = 10) -> str:
    return f"2099-01-{day:02d}T{hh:02d}:{mm:02d}:00.000Z"


class Instances:
    """Instance records in the machine directory: live ones hold their lock in this process (a second handle of the
    same file cannot take it, on Windows and POSIX alike), stale ones leave it free."""

    def __init__(self, home: Path):
        self.home = home
        self.locks: list[FileLock] = []
        self.n = 0

    def add(self, config=None, run_dir=None, pid=4242, sessions=0, started="2099-01-10T10:00:00", live=True,
            record=True) -> Path:
        self.n += 1
        lock_path = self.home / "instances" / f"{pid}-{1000 + self.n}.lock"
        lock = FileLock(lock_path)
        assert lock.try_acquire()
        if record:
            write_record(record_path(lock_path), {"id": lock_path.stem, "config": str(config) if config else None,
                                                  "run_dir": str(run_dir) if run_dir else None, "pid": pid,
                                                  "started": started, "sessions": sessions})
        if live:
            self.locks.append(lock)
        else:
            lock.release()
        return lock_path

    def close(self):
        for lock in self.locks:
            lock.release()


@pytest.fixture
def inst(machine_home):
    found = Instances(machine_home)
    yield found
    found.close()


def pipe(name="alpha", root: Path | None = None, records=(), goal=None, items=None, log=None, **extra):
    root = root or Path(f"/pipelines/{name}")
    return cn.PipelineNow(name, str(root / "radark.toml"), root / "run", log=log or ch.Log("ok", list(records)),
                          goal=goal, items={} if items is None else items, **extra)


def cards_of(home, *pipes, at_=NOW):
    return {c["name"]: c for c in cn.now(home, list(pipes), at=at_)["pipelines"]}


# ---- 1.1 the read-only probe

def test_probe_readonly_held_free_and_missing(machine_home):
    lock_path = machine_home / "instances" / "1-1.lock"
    proc = hold_in_child(lock_path, {"id": "1-1", "pid": 1})
    try:
        assert probe_readonly(lock_path) is True
    finally:
        kill(proc)
    assert probe_readonly(lock_path) is False
    assert lock_path.exists() and record_path(lock_path).exists()  # a stale record is the dispatcher's to remove
    missing = machine_home / "instances" / "2-2.lock"
    assert probe_readonly(missing) is False and not missing.exists()


def test_probe_readonly_unopenable_is_unknown(machine_home, monkeypatch):
    lock_path = machine_home / "x.lock"
    lock_path.write_text("")

    def refuse(*a, **k):
        raise PermissionError("denied")
    monkeypatch.setattr(machine_mod.os, "open", refuse)
    assert probe_readonly(lock_path) is None


# ---- 1.2 instances and matching

def test_live_stale_and_orphan_records(machine_home, inst):
    live = inst.add("/pipelines/alpha/radark.toml", pid=11)
    inst.add("/pipelines/beta/radark.toml", pid=12, live=False)
    write_record(machine_home / "instances" / "13-1.json", {"pid": 13, "config": "/pipelines/alpha/radark.toml"})
    found = cn.live_instances(machine_home)
    assert [i.id for i in found] == [live.stem] and found[0].pid == 11


def test_no_instances_folder_creates_nothing(machine_home):
    assert cn.live_instances(machine_home) == [] and not (machine_home / "instances").exists()


def test_unknown_probe_kept_apart(machine_home, inst, monkeypatch):
    inst.add("/pipelines/alpha/radark.toml")
    monkeypatch.setattr(machine_mod, "probe_readonly", lambda path: None)
    (found,) = cn.live_instances(machine_home)
    assert found.unknown and found.record == {}
    data = cn.now(machine_home, [pipe("alpha")], at=NOW)
    assert data["pipelines"][0]["state"] == "not running" and data["machine"]["unknown_instances"] == 1


def test_running_not_running_and_other_instances(machine_home, inst):
    inst.add(Path("/pipelines/alpha/radark.toml"), pid=21, sessions=1)
    inst.add(Path("/pipelines/beta/radark.toml"), pid=22, live=False)
    inst.add(Path("/pipelines/gamma/radark.toml"), pid=23, sessions=1)
    data = cn.now(machine_home, [pipe("alpha"), pipe("beta")], at=NOW)
    cards = {c["name"]: c for c in data["pipelines"]}
    assert cards["alpha"]["state"] == "running" and [i["pid"] for i in cards["alpha"]["instances"]] == [21]
    assert cards["beta"]["state"] == "not running" and cards["beta"]["instances"] == []
    assert data["machine"]["running"] == 1 and data["machine"]["other_instances"] == 1


def test_two_live_instances_of_one_pipeline(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml", pid=32, started="2099-01-10T11:00:00")
    inst.add("/pipelines/alpha/radark.toml", pid=31, started="2099-01-10T10:00:00")
    card = cards_of(machine_home, pipe("alpha"))["alpha"]
    assert card["state"] == "running" and [i["pid"] for i in card["instances"]] == [31, 32]


def test_match_by_run_directory(machine_home, inst):
    inst.add("/elsewhere/moved.toml", run_dir=Path("/pipelines/alpha/run"), pid=41)
    assert cards_of(machine_home, pipe("alpha"))["alpha"]["state"] == "running"


def test_instance_start_is_local_time_sent_as_utc(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml", started="2099-01-10T10:00:00")
    (i,) = cards_of(machine_home, pipe("alpha"))["alpha"]["instances"]
    expected = dt.datetime(2099, 1, 10, 10, 0).astimezone().astimezone(dt.timezone.utc)
    assert ch.parse_time(i["started"]) == expected
    inst.add("/pipelines/beta/radark.toml", started="not a time")
    (j,) = cards_of(machine_home, pipe("beta"))["beta"]["instances"]
    assert j["started"] is None


# ---- 1.3 state, goal, sessions, facts

def test_broken_configuration_and_unreadable_log_are_unknown(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml", pid=51)
    cards = cards_of(machine_home,
                     cn.PipelineNow("alpha", "/pipelines/alpha/radark.toml", state="error", message="bad key"),
                     cn.PipelineNow("beta", "/pipelines/beta/radark.toml", state="missing"),
                     pipe("gamma", log=ch.Log("error", error="denied")),
                     pipe("delta", dir_readable=False),
                     pipe("eps", log=ch.Log("missing")))
    assert cards["alpha"]["state"] == "unknown" and cards["alpha"]["message"] == "bad key"
    assert [i["pid"] for i in cards["alpha"]["instances"]] == [51]  # the owner sees why
    assert cards["beta"]["state"] == "unknown"
    assert cards["gamma"]["state"] == "unknown" and cards["delta"]["state"] == "unknown"
    assert cards["eps"]["state"] == "not running" and cards["eps"]["log"] == "missing"


GOAL = {"path": "/goals/sub/goal.md", "started": at(9), "status": "running", "pid": 61}


@pytest.mark.parametrize("goal, expected", [
    (GOAL, {"name": "goal.md", "started": at(9)}),
    ({**GOAL, "path": "C:\\goals\\win-goal.md"}, {"name": "win-goal.md", "started": at(9)}),
    ({**GOAL, "status": "complete"}, None),
    ({**GOAL, "pid": 99}, None),
])
def test_goal_or_regular_run(machine_home, inst, goal, expected):
    inst.add("/pipelines/alpha/radark.toml", pid=61)
    card = cards_of(machine_home, pipe("alpha", goal=goal))["alpha"]
    assert card["goal"] == expected and card["last_goal"] is None
    assert "/goals" not in json.dumps(card) and "C:\\\\goals" not in json.dumps(card)


def test_last_goal_on_a_card_not_running(machine_home):
    goal = {**GOAL, "status": "complete", "ended": "2099-01-10T11:00:00"}
    card = cards_of(machine_home, pipe("alpha", goal=goal))["alpha"]
    assert card["goal"] is None and card["last_goal"]["name"] == "goal.md"
    assert card["last_goal"]["status"] == "complete" and card["last_goal"]["ended"] is not None


LOG = [start_rec(at(8), C), boot(at(9)), start_rec(at(9, 5), A, team="app"),
       start_rec(at(9, 10), B, phase="propose", team="product"), end_rec(at(10), B, phase="propose", team="product",
                                                                         duration=3000),
       start_rec(at(11, 30), None, phase="idle", team="product")]


def test_running_sessions_after_the_latest_start_with_a_live_instance(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml")
    card = cards_of(machine_home, pipe("alpha", records=LOG, items={A: {"id": A, "title": "Invented task"}}))["alpha"]
    got = [(s["handover"], s["title"], s["phase"], s["state"], s["elapsed_s"]) for s in card["running"]]
    assert got == [(A, "Invented task", "apply", "running", 2 * 3600 + 55 * 60),
                   (None, None, "idle", "running", 30 * 60)]
    assert card["running"][0]["start"] == at(9, 5) and card["running"][0]["team"] == "app"


def test_open_sessions_without_a_live_instance_are_interrupted(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml", live=False)
    card = cards_of(machine_home, pipe("alpha", records=LOG))["alpha"]
    assert card["state"] == "not running"
    assert [(s["handover"], s["state"], s["elapsed_s"]) for s in card["running"]] == [(A, "interrupted", None),
                                                                                       (None, "interrupted", None)]
    assert card["running"][0]["title"] == "unknown"  # not in the hub's list


def test_hub_failure_gives_unknown_titles(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml")
    card = cards_of(machine_home, pipe("alpha", records=LOG, items=None, hub_error="hub broken"))["alpha"]
    card_items = cn.card(pipe("alpha", records=LOG, hub_error="x"), [], NOW)
    assert card["running"][0]["title"] == "unknown" and card["hub_error"] == "hub broken"
    assert card_items["running"][0]["title"] == "unknown"


def test_last_event_session_start_and_stop(machine_home):
    recs = [boot(at(7)), {"time": at(7, 30), "event": "stop"}, boot(at(8)), start_rec(at(8, 5), A),
            end_rec(at(8, 40), A, duration=2100, outcome="finished"), {"time": at(8, 41), "event": "stop"}]
    card = cards_of(machine_home, pipe("alpha", records=recs))["alpha"]
    assert card["last_event"] == {"time": at(8, 41), "event": "stop"}
    assert card["last_session"] == {"end": at(8, 40), "outcome": "finished", "team": "app", "handover": A,
                                    "phase": "apply"}
    assert card["last_start"] == at(8) and card["last_stop"] == at(8, 41)
    recs = recs[:-1]  # the stop before the last start is not this run's
    card = cards_of(machine_home, pipe("alpha", records=recs))["alpha"]
    assert card["last_stop"] is None and card["last_event"]["event"] == "session_end"


def test_no_prompt_or_result_text_in_a_card(machine_home, inst):
    inst.add("/pipelines/alpha/radark.toml")
    text = json.dumps(cards_of(machine_home, pipe("alpha", records=LOG + [end_rec(at(11), A)])))
    for secret in ("secret prompt", "secret result text", "stream.jsonl", "/pipelines/"):
        assert secret not in text


# ---- 1.4 the machine line

def test_machine_line_slots_and_limit(machine_home, inst):
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 3\n", encoding="utf-8")
    inst.add("/pipelines/alpha/radark.toml", sessions=1)
    inst.add("/pipelines/beta/radark.toml", sessions=2)
    inst.add("/pipelines/beta/radark.toml", sessions=5, live=False)
    line = cn.now(machine_home, [pipe("alpha"), pipe("beta")], at=NOW)["machine"]
    assert line == {"slots_used": 3, "slots_limit": 3, "running": 2, "other_instances": 0, "unknown_instances": 0,
                    "note": None}


def test_machine_line_invalid_machine_toml(machine_home):
    (machine_home / "machine.toml").write_text("[machine]\nsessions = 0\n", encoding="utf-8")
    line = cn.now(machine_home, [], at=NOW)["machine"]
    assert line["slots_limit"] == machine_mod.DEFAULT_SESSIONS and "invalid" in line["note"]


# ---- 2.1 the server

def run_dir_of(cfg: Path) -> Path:
    return config_mod.load(cfg).run_dir


def test_api_now_two_pipelines_one_hub(env, start, inst, machine_home):
    env.set_hub({f"show:{A}": {"id": A, "title": "Invented task", "to": ["app"], "status": "open",
                               "recipients": {"app": "acknowledged"}, "expects": "done"}})
    alpha = named(env, "alpha")
    beta = second_pipeline(env, "beta")
    recent = ch.iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20))
    write_log(alpha, [boot(recent), start_rec(recent, A)])
    write_log(beta, [boot(recent), start_rec(recent, B)])
    inst.add(os.path.realpath(alpha), run_dir_of(alpha), pid=71, sessions=1)
    c = start([alpha, beta])
    before = len(env.ho_calls())
    status, data = c.json("GET", "/api/now")
    assert status == 200
    cards = {p["name"]: p for p in data["pipelines"]}
    assert [p["name"] for p in data["pipelines"]] == ["alpha", "beta"]
    assert cards["alpha"]["state"] == "running" and cards["alpha"]["running"][0]["title"] == "Invented task"
    assert 19 * 60 <= cards["alpha"]["running"][0]["elapsed_s"] <= 25 * 60
    assert cards["beta"]["state"] == "not running" and cards["beta"]["running"][0]["state"] == "interrupted"
    assert cards["beta"]["running"][0]["title"] == "unknown"
    assert data["machine"]["slots_used"] == 1 and data["machine"]["running"] == 1
    lists = [x for x in env.ho_calls()[before:] if x["args"][0] == "list"]
    assert len(lists) == 1 and lists[0]["args"] == ["list", "--status", "all"]
    assert c.json("GET", "/api/now")[0] == 200
    assert len([x for x in env.ho_calls()[before:] if x["args"][0] == "list"]) == 1  # reused within 30 s
    assert not [x for x in env.ho_calls() if x["args"][0] in WRITES]
    text = json.dumps(data)
    for secret in (str(env.root), "runs.jsonl", "goal.json", "instances/", "instances\\\\", "secret prompt"):
        assert secret not in text and secret.replace("\\", "\\\\") not in text


def test_api_now_list_refreshed_after_30_s(env, start, monkeypatch):
    env.set_hub({})
    c = start([named(env, "alpha")])
    before = len(env.ho_calls())
    c.json("GET", "/api/now")
    clock = cockpit.time.monotonic() + cockpit.NOW_LIST_S + 1
    monkeypatch.setattr(cockpit.time, "monotonic", lambda: clock)
    c.json("GET", "/api/now")
    assert len([x for x in env.ho_calls()[before:] if x["args"][0] == "list"]) == 2


def test_api_now_foreign_host(env, start):
    c = start([named(env, "alpha")])
    before = len(env.ho_calls())
    status, _, _ = c.request("GET", "/api/now", headers={"Host": f"attacker.invalid:{c.port}"})
    assert status == 403 and len(env.ho_calls()) == before
    status, headers, _ = c.request("GET", "/api/now")
    assert status == 200 and headers["Cache-Control"] == "no-store"


def test_api_now_unreadable_run_log(env, start):
    env.set_hub({})
    alpha = named(env, "alpha")
    (run_dir_of(alpha) / "runs.jsonl").mkdir(parents=True)  # a directory where the log should be: cannot be read
    beta = second_pipeline(env, "beta")
    status, data = start([alpha, beta]).json("GET", "/api/now")
    assert status == 200
    assert [(p["name"], p["state"]) for p in data["pipelines"]] == [("alpha", "unknown"), ("beta", "not running")]


# ---- 2.2 read only

def test_api_now_changes_no_file(env, start, inst, machine_home):
    env.set_hub({})
    alpha = named(env, "alpha")
    beta = second_pipeline(env, "beta")
    write_log(alpha, [boot(at(9)), start_rec(at(9, 5), A)])
    write_log(beta, [boot(at(9)), start_rec(at(9, 5), B)])
    (run_dir_of(alpha) / "goal.json").write_text(json.dumps({**GOAL, "pid": 81}), encoding="utf-8")
    inst.add(os.path.realpath(alpha), pid=81, sessions=1)
    stale = inst.add(os.path.realpath(beta), pid=82, live=False)
    write_record(machine_home / "instances" / "83-1.json", {"pid": 83})  # an orphan record without a lock file
    c = start([alpha, beta])
    files = snapshot(machine_home, run_dir_of(alpha), run_dir_of(beta))
    assert str(stale) in files and str(record_path(stale)) in files
    for _ in range(2):
        assert c.json("GET", "/api/now")[0] == 200
    assert snapshot(machine_home, run_dir_of(alpha), run_dir_of(beta)) == files


# ---- 2.3 the page

def test_page_now_tab():
    src = page_source()
    nav = src[src.index("<nav>"):src.index("</nav>")]
    now = re.search(r"<button[^>]*>Now</button>", nav).group(0)
    assert "disabled" not in now and 'data-tab="now"' in now
    assert "coming later" not in src and "placeholder" not in src.split("<body>")[1].split("<script>")[0]
    for text in ("/api/now", "NOW_REFRESH_MS = 10000", "Session slots", "Goal run", "Regular run", "Interrupted sessions",
                 "not recorded", "toLocaleString"):
        assert text in src
    code = src[src.index("// ---- Now:"):src.index("function showTab(")]
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert not re.search(r"""(src|href)\s*=\s*["']?\s*(https?:)?//""", src)


def test_page_served_has_the_now_tab(env, start):
    status, _, body = start().request("GET", "/")
    html = body.decode("utf-8")
    assert status == 200 and 'id="tab-now"' in html and "coming later" not in html
