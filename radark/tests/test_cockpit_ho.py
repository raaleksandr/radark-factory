"""The owner cockpit end to end with the installed `ho` (the runtime dependency) on a throw-away neutral hub made
with `ho init` in the test's temporary directory (owner-cockpit D9): never the owner's hub, never a browser.
Without `ho` on PATH the test fails with a clear message; it is not skipped (hub AGENTS.md section 10)."""
import json
import os
import shutil
import subprocess
import sys
import threading

import pytest

from radark import cockpit
from radark.tests.conftest import FAKES, toml_path
from radark.tests.test_cockpit import Running


def ho_cmd() -> str:
    found = shutil.which("ho")
    if not found:
        pytest.fail("the installed `ho` (radark-handover) is not on PATH; this test needs it: install the engine's "
                    "dependency (pip install radark-handover) or put its scripts directory on PATH")
    return found


def ho(hub, team, *args, body=None) -> dict:
    env = dict(os.environ, HO_HUB=str(hub), HO_TEAM=team)
    proc = subprocess.run([ho_cmd(), *args, "--json"], input=(body or "").encode("utf-8"), capture_output=True,
                          env=env, timeout=120)
    assert proc.returncode == 0, proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
    return json.loads(proc.stdout.decode("utf-8"))


@pytest.fixture
def hub(tmp_path):
    path = tmp_path / "hub"
    proc = subprocess.run([ho_cmd(), "init", str(path), "--teams", "product=Product,app=App,owner=Owner", "--json"],
                          capture_output=True, timeout=120, env={k: v for k, v in os.environ.items()
                                                                  if k not in ("HO_HUB", "HO_TEAM")})
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    return path


def config_for(tmp_path, hub) -> str:
    root = tmp_path / "alpha"
    lines = ['name = "alpha"', f"hub = {toml_path(hub)}", 'run_dir = ".radark"', 'ho = "ho"',
             f"claude = [{toml_path(sys.executable)}, {toml_path(FAKES / 'fake_claude.py')}]"]
    for tid, kind in (("product", "product"), ("app", "technical")):
        repo = root / "repos" / tid
        repo.mkdir(parents=True)
        lines += ["[[teams]]", f'id = "{tid}"', f"repo = {toml_path(repo)}", f'kind = "{kind}"']
    path = root / "radark.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def new(hub, title, expects, *extra):
    return ho(hub, "product", "new", "--to", "owner", "--expects", expects, "--title", title, "--body", "-", *extra,
              body=f"Invented request: {title}.\n\n<script>alert(1)</script>\n")["id"]


def test_answers_through_the_installed_ho(tmp_path, hub, machine_home):
    esc = new(hub, "Pick a variant", "response", "--tag", "escalation")
    task = new(hub, "Place the test key", "done")
    note = new(hub, "Release notes are ready", "ack")
    other = new(hub, "Spend more on hosting", "response")
    server = cockpit.Server(0, cockpit.Cockpit(machine_home, [config_for(tmp_path, hub)]))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        c = Running(server)
        data = c.items()
        assert data["hubs"][0]["error"] is None, data["hubs"]
        assert {i["id"] for i in data["pending"]} == {esc, task, note, other} and data["done"] == []
        by_id = {i["id"]: i for i in data["pending"]}
        assert by_id[esc]["escalation"] is True and by_id[esc]["pipelines"] == ["alpha"]
        assert "<script>alert(1)</script>" in by_id[esc]["body"]  # raw text; the page escapes it
        assert "respond" in by_id[esc]["allowed"] and "done" in by_id[task]["allowed"]
        key = data["hubs"][0]["hub_key"]
        for hid, action, text in ((esc, "respond", "Take the plain variant."), (task, "done", "Placed."),
                                  (note, "ack", ""), (other, "decline", "Not this month.")):
            status, answer = c.act(key, hid, action, text)
            assert status == 200 and answer["ok"] is True, answer
        status, answer = c.act(key, esc, "respond", "Again.")
        assert status == 409 and answer["error"] == "not allowed now"
        expected = {esc: "answered", task: "done", note: "acknowledged", other: "declined"}
        for hid, state in expected.items():
            shown = ho(hub, "owner", "show", hid)
            assert shown["my_state"] == state, (hid, shown["my_state"])
        events = ho(hub, "owner", "show", esc)["events"]
        assert events[-1]["team"] == "owner" and events[-1]["body"].strip() == "Take the plain variant."
        after = c.items()
        assert after["pending"] == [] and {i["id"] for i in after["done"]} == set(expected)
    finally:
        server.shutdown()
        server.server_close()
