"""A handover waiting for a team the dispatcher does not run (change unconfigured-team-escalation)."""
import json
import os
import subprocess

from harness.__main__ import Dispatcher, main
from harness.tests.conftest import START, TEAMS, item, show, write_config

V = "HO-20261025-vozr"  # the sender's item
G = "HO-20261025-ghyl"  # its handover to `backend`
G_TITLE = "Build ST-35 now: store why a the product run ended (BL-003)"
SESSION = "72435567-f1f6-4a4d-8c1e-17d393fff2eb"


def two_teams(env):
    """The configuration without `backend`, which stays a team of the hub."""
    env.config_path = write_config(env.root, triage=False, teams=TEAMS[:2])


def sent(hid, to="backend", recipients=None, status="open", refs=(V,), title=G_TITLE):
    h = {"id": hid, "title": title, "from": "app", "to": [to], "expects": "done", "status": status,
         "refs": list(refs), "created": "2026-10-25T11:03:38.126Z", "last_activity": "2026-10-25T11:03:38.126Z"}
    if recipients is not False:
        h["recipients"] = recipients or {to: "pending"}
    return h


def disp(env):
    return Dispatcher(env.cfg(), out=lambda *a: None)


def with_item(env):
    """`app` worked on V and sent G to `backend`; V is still in its inbox."""
    two_teams(env)
    env.set_hub({"list:app": {"items": [sent(G)]}, f"show:{V}": show(V, title="BL-003"),
                 f"show:{G}": show(G, title=G_TITLE),
                 "inbox:app": {"action_required": [item(V, title="BL-003", my_state="acknowledged")]}})
    d = disp(env)
    rec = d.state.ensure(V, "app")
    rec.update(phase="apply", title="BL-003")
    rec["sessions"].append({"id": SESSION, "team": "app", "phase": "apply", "outcome": "finished",
                            "started": "2026-10-25T11:02:55.774Z", "ended": "2026-10-25T11:41:53.888Z"})
    d.state.save()
    return d


def new_calls(env):
    return [c for c in env.ho_calls() if c["args"][0] == "new"]


def log_events(env, kind):
    lines = (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["event"] == kind]


def arg(call, name):
    return call["args"][call["args"].index(name) + 1]


# ---- detection (task 1.1)

def test_waits_only_for_unfinished_recipients_of_teams_not_set_up(env):
    two_teams(env)
    env.set_hub({"list:app": {"items": [
        sent("HO-1"), sent("HO-2", recipients={"backend": "acknowledged"}), sent("HO-3", recipients=False),
        sent("HO-4", recipients={"backend": "done"}), dict(sent("HO-5", recipients={"backend": "answered"}), expects="response"),
        sent("HO-6", recipients={"backend": "declined"}), sent("HO-7", recipients={"backend": "returned"}),
        sent("HO-8", status="closed"), sent("HO-9", to="product"), sent("HO-10", to="owner"),
        dict(sent("HO-11", recipients={"backend": "acknowledged"}), expects="ack"),
    ]}})
    waits = disp(env).unconfigured_waits()
    assert [(w["handover"], w["sender"], w["team"], w["state"]) for w in waits] == [
        ("HO-1", "app", "backend", "pending"), ("HO-2", "app", "backend", "acknowledged"),
        ("HO-3", "app", "backend", "pending"), ("HO-7", "app", "backend", "returned")]


def test_returned_part_is_escalated_as_a_new_wait(env):
    d = with_item(env)
    update = json.loads(env.ho_data.read_text())
    update["list:app"]["items"][0]["recipients"] = {"backend": "done"}
    env.ho_data.write_text(json.dumps(update))
    d.escalate_unconfigured()
    assert new_calls(env) == []
    update["list:app"]["items"][0]["recipients"] = {"backend": "returned"}
    env.ho_data.write_text(json.dumps(update))
    d.escalate_unconfigured()
    [call] = new_calls(env)
    assert arg(call, "--ref") == V and d.state.get(V)["flags"]["escalated"]
    assert log_events(env, "unconfigured_team")[0]["state"] == "returned"


def test_failing_list_skips_the_check(env):
    two_teams(env)
    env.set_hub({"list:app": {"exit": 1, "error": {"code": "usage", "message": "broken"}}})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    assert d.unconfigured_waits() is None
    d.escalate_unconfigured()
    assert new_calls(env) == [] and any("! ho list --from app failed" in x for x in lines)


# ---- escalation (task 1.2)

def test_waiting_item_escalated_once(env):
    d = with_item(env)
    assert [c.handover for c in d.plan()] == [V]
    lines = []
    d._print = lines.append
    assert d.loop(once=True) == 0
    assert env.claude_calls() == []  # no session for the waiting item
    [call] = new_calls(env)
    assert call["team"] == "app" and arg(call, "--to") == "owner" and arg(call, "--ref") == V
    assert arg(call, "--tag") == "escalation" and "--auto-close" in call["args"]
    title = arg(call, "--title")
    assert title == f"app: {G} waits for team backend, which the dispatcher does not run"
    body = call["stdin"]
    assert G in body and G_TITLE in body and "`backend`" in body and str(env.config_path) in body
    assert "[[teams]]" in body and 'id = "backend"' in body and "kind = " in body and V in body and SESSION in body
    rec = d.state.get(V)
    assert rec["flags"]["escalated"] and "waits for team backend, which is not set up" in rec["reason"]
    assert rec["escalation"]["session"] == SESSION and rec["escalation"]["phase"] == "apply"
    assert d.plan() == []
    assert any("! ESCALATED" in x and "backend" in x for x in lines)
    [event] = log_events(env, "unconfigured_team")
    assert (event["handover"], event["sender"], event["team"], event["state"], event["item"], event["escalation"]) \
        == (G, "app", "backend", "pending", V, "HO-FAKE-0001")
    assert d.state.meta["unconfigured"][G]["escalation"] == "HO-FAKE-0001"
    assert d.loop(once=True) == 0 and len(new_calls(env)) == 1  # escalated once
    assert len(log_events(env, "unconfigured_team")) == 1


def test_entry_dropped_when_the_handover_no_longer_waits(env):
    d = with_item(env)
    d.loop(once=True)
    data = json.loads(env.ho_data.read_text())
    data["list:app"]["items"][0]["recipients"] = {"backend": "done"}
    env.ho_data.write_text(json.dumps(data))
    d.loop(once=True)
    assert "unconfigured" not in d.state.meta and len(new_calls(env)) == 1


def test_no_waiting_item_sends_standalone_handover(env):
    two_teams(env)
    env.set_hub({"list:app": {"items": [sent(G, refs=("HO-20261010-aybd",))]}})
    d = disp(env)
    d.loop(once=True)
    [call] = new_calls(env)
    assert call["team"] == "app" and arg(call, "--ref") == G
    assert "which the dispatcher does not run" in arg(call, "--title") and "[[teams]]" in call["stdin"]
    assert all(not d.state.blocked(h) for h in d.state.records)
    assert d.state.meta["unconfigured"][G]["item"] is None


def test_blocked_item_gets_standalone_handover(env):
    d = with_item(env)
    d.state.escalate(V, "app", "asked something else")
    d.state.save()
    d.loop(once=True)
    [call] = new_calls(env)
    assert arg(call, "--ref") == G and d.state.get(V)["reason"] == "asked something else"


def test_escalation_does_not_trigger_an_idle_ask(env):
    with_item(env)
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\nidle_ask = true"))
    d = disp(env)
    d.state.meta["last_idle_ask"] = "2026-10-25T12:00:00.000Z"  # asked after G was sent
    d.state.save()
    assert d.loop(once=True) == 0
    assert len(new_calls(env)) == 1 and env.claude_calls() == [] and log_events(env, "idle_ask") == []


# ---- owner answer (task 1.3)

def test_owner_answer_after_adding_the_team_resumes_the_session(env):
    with_item(env).loop(once=True)
    subprocess.run(env.cfg().ho + ["respond", "HO-FAKE-0001", "-m", "backend is set up now; continue"],
                   env=dict(os.environ, HO_TEAM="owner"), check=True, capture_output=True)
    env.config_path = write_config(env.root, triage=False)  # the owner adds `backend` and restarts
    data = json.loads(env.ho_data.read_text())
    data["inbox:backend"] = {"action_required": [item(G, title=G_TITLE, sender="app")]}
    env.ho_data.write_text(json.dumps(data))
    env.set_claude([{"steps": [START], "result": {"result": "Continued."}}])
    d = disp(env)
    assert d.loop(once=True) == 0
    [call] = env.claude_calls()
    assert call["argv"][call["argv"].index("--resume") + 1] == SESSION
    assert "backend is set up now; continue" in call["argv"][1] and "waits for team backend" in call["argv"][1]
    assert not d.state.blocked(V) and "unconfigured" not in d.state.meta
    assert len(new_calls(env)) == 1
    assert ("backend", G) in [(c.team, c.handover) for c in d.plan()]


# ---- dry run (task 1.4)

def test_dry_run_lists_the_wait_and_sends_nothing(env, capsys):
    with_item(env)
    capsys.readouterr()
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"Waits for a team not set up: {G} from app to backend (pending); would escalate {V}" in out
    assert "Would start" not in out
    assert new_calls(env) == [] and env.claude_calls() == []
