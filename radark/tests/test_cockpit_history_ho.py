"""The cockpit History end to end with the installed `ho` on a throw-away neutral hub made with `ho init` in the
test's temporary directory (cockpit-history H9): never the owner's hub, never a browser. Without `ho` on PATH the
test fails with a clear message; it is not skipped (hub AGENTS.md section 10)."""
import json
import sys
import threading

from radark import cockpit
from radark.tests.conftest import FAKES, toml_path
from radark.tests.test_cockpit import Running
from radark.tests.test_cockpit_ho import ho, hub  # noqa: F401 - `hub` is the fixture

UNKNOWN = "HO-20200101-zzzz"  # an ID the hub does not know


def config_for(tmp_path, hub, name) -> str:
    root = tmp_path / name
    lines = [f'name = "{name}"', f"hub = {toml_path(hub)}", 'run_dir = ".radark"', 'ho = "ho"',
             f"claude = [{toml_path(sys.executable)}, {toml_path(FAKES / 'fake_claude.py')}]"]
    for tid, kind in (("product", "product"), ("app", "technical")):
        repo = root / "repos" / tid
        repo.mkdir(parents=True)
        lines += ["[[teams]]", f'id = "{tid}"', f"repo = {toml_path(repo)}", f'kind = "{kind}"']
    path = root / "radark.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def write_log(tmp_path, name, ids):
    run_dir = tmp_path / name / ".radark"
    run_dir.mkdir(parents=True)
    lines = []
    for i, hid in enumerate(ids):
        start, end = f"2020-01-10T{9 + i:02d}:00:00.000Z", f"2020-01-10T{9 + i:02d}:30:00.000Z"
        lines.append({"time": start, "event": "session_start", "team": "app", "handover": hid, "phase": "apply"})
        lines.append({"time": end, "event": "session_end", "team": "app", "handover": hid, "phase": "apply",
                      "outcome": "finished", "duration_s": 1800, "session": f"s-{i}"})
    (run_dir / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


def new(hub, title, *extra):
    return ho(hub, "product", "new", "--to", "app", "--expects", "done", "--title", title, "--body", "-", *extra,
              body=f"Invented task: {title}.\n")["id"]


def test_history_results_through_the_installed_ho(tmp_path, hub, machine_home):
    accepted = new(hub, "Accepted work", "--auto-close")
    review = new(hub, "Work in review")
    returned = new(hub, "Returned work")
    opened = new(hub, "Open work")
    declined = new(hub, "Declined work")
    ho(hub, "app", "done", accepted, "-m", "Done.")
    ho(hub, "app", "done", review, "-m", "Done.")
    ho(hub, "app", "done", returned, "-m", "Done.")
    ho(hub, "product", "return", returned, "--to", "app", "-m", "One more thing.")
    ho(hub, "app", "ack", opened)
    ho(hub, "app", "decline", declined, "-m", "Not ours.")
    ho(hub, "product", "close", declined, "-m", "Closed after the decline.")
    write_log(tmp_path, "alpha", [accepted, review, returned, UNKNOWN])
    write_log(tmp_path, "beta", [opened, declined, accepted])
    configs = [config_for(tmp_path, hub, "alpha"), config_for(tmp_path, hub, "beta")]
    server = cockpit.Server(0, cockpit.Cockpit(machine_home, configs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, data = Running(server).json("GET", "/api/history?period=all")
        assert status == 200, data
        assert [p["hub_error"] for p in data["pipelines"]] == [None, None], data["pipelines"]
        got = {(r["pipeline"], r["id"]): r["result"] for r in data["rows"]}
        assert got == {("alpha", accepted): "accepted", ("alpha", review): "in review",
                       ("alpha", returned): "returned", ("alpha", UNKNOWN): "unknown",
                       ("beta", opened): "open", ("beta", declined): "declined", ("beta", accepted): "accepted"}
        titles = {r["id"]: r["title"] for r in data["rows"]}
        assert titles[review] == "Work in review" and titles[UNKNOWN] == UNKNOWN
        assert data["summary"]["handovers"] == 7 and data["summary"]["accepted"] == 2
    finally:
        server.shutdown()
        server.server_close()
