"""The cockpit Now tab end to end with the installed `ho` on a throw-away neutral hub made with `ho init` in the
test's temporary directory (cockpit-now N10), invented run logs and instance records, one live instance whose lock a
helper process holds: never the owner's hub or machine directory, never a browser. Without `ho` on PATH the test
fails with a clear message; it is not skipped (hub AGENTS.md section 10)."""
import datetime as dt
import json
import os
import threading

from radark import cockpit
from radark.cockpit_history import iso
from radark.machine import record_path, write_record
from radark.tests.test_cockpit import Running
from radark.tests.test_cockpit_history_ho import UNKNOWN, config_for, new
from radark.tests.test_cockpit_ho import hub  # noqa: F401 - `hub` is the fixture
from radark.tests.test_machine import hold_in_child, kill


def write_log(tmp_path, name, records):
    run_dir = tmp_path / name / ".radark"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return run_dir


def rec(time, event, **fields):
    return {"time": time, "event": event, **fields}


def test_now_through_the_installed_ho(tmp_path, hub, machine_home):  # noqa: F811
    task = new(hub, "Invented running task")
    old = new(hub, "Invented earlier task")
    now = dt.datetime.now(dt.timezone.utc)
    ago = lambda minutes: iso(now - dt.timedelta(minutes=minutes))  # noqa: E731
    alpha, beta = config_for(tmp_path, hub, "alpha"), config_for(tmp_path, hub, "beta")
    write_log(tmp_path, "alpha", [rec(ago(40), "dispatcher_start", pid=1, goal=None),
                                  rec(ago(30), "session_start", team="app", handover=task, phase="apply"),
                                  rec(ago(25), "session_start", team="app", handover=UNKNOWN, phase="apply")])
    write_log(tmp_path, "beta", [rec(ago(300), "dispatcher_start", pid=2, goal=None),
                                 rec(ago(290), "session_start", team="app", handover=old, phase="apply"),
                                 rec(ago(280), "session_end", team="app", handover=old, phase="apply",
                                     outcome="finished", duration_s=600),
                                 rec(ago(270), "session_start", team="product", handover=task, phase="propose")])
    live = machine_home / "instances" / "5001-1.lock"
    proc = hold_in_child(live, {"id": "5001-1", "config": os.path.realpath(alpha), "pid": 5001,
                                "run_dir": str(tmp_path / "alpha" / ".radark"),
                                "started": dt.datetime.now().isoformat(timespec="seconds"), "sessions": 2})
    stale = machine_home / "instances" / "5002-1.lock"
    stale.write_text("")
    write_record(record_path(stale), {"id": "5002-1", "config": os.path.realpath(beta), "pid": 5002, "sessions": 1})
    server = cockpit.Server(0, cockpit.Cockpit(machine_home, [alpha, beta]))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, data = Running(server).json("GET", "/api/now")
        assert status == 200, data
        cards = {c["name"]: c for c in data["pipelines"]}
        a, b = cards["alpha"], cards["beta"]
        assert a["state"] == "running" and [i["pid"] for i in a["instances"]] == [5001], a
        assert a["hub_error"] is None and a["goal"] is None
        assert [(s["handover"], s["title"], s["state"]) for s in a["running"]] == [
            (task, "Invented running task", "running"), (UNKNOWN, "unknown", "running")]
        assert b["state"] == "not running" and b["instances"] == []
        assert [(s["handover"], s["state"]) for s in b["running"]] == [(task, "interrupted")]
        assert b["last_session"]["outcome"] == "finished" and b["last_session"]["handover"] == old
        assert b["last_start"] == ago(300) and b["last_stop"] is None
        assert data["machine"]["slots_used"] == 2 and data["machine"]["running"] == 1
        assert stale.exists() and record_path(stale).exists()  # the stale record is left to the dispatcher
    finally:
        server.shutdown()
        server.server_close()
        kill(proc)
