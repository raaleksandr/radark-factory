"""An item held while its team waits for a handover's result (change wait-for-handover-result)."""
import json

from harness.__main__ import Dispatcher, main
from harness.tests.conftest import START, item, show

V = "HO-20261025-vozr"  # app's item
G = "HO-20261025-ghyl"  # its handover to `backend`
OLD, NEW = "2026-10-25T11:03:38.126Z", "2026-10-25T12:30:00.000Z"


def sent(recipients=None, status="open"):
    return {"id": G, "title": "Build ST-35", "from": "app", "to": ["backend"], "expects": "done",
            "status": status, "refs": [V], "recipients": recipients or {"backend": "pending"},
            "created": OLD, "last_activity": OLD}


def setup(env, site_inbox=True):
    """`app` sent G to the configured team `backend`; V has newer hub activity than G."""
    env.set_hub({"list:app": {"items": [sent()]},
                 f"show:{V}": show(V, [(NEW, "owner", "respond", "ok")], title="BL-003"),
                 f"show:{G}": show(G, created=OLD, title="Build ST-35"),
                 "inbox:app": {"action_required": [item(V, title="BL-003", my_state="acknowledged", last=NEW)]},
                 "inbox:backend": {"action_required": [item(G, title="Build ST-35", sender="app", last=OLD)]
                                if site_inbox else []}})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    rec = d.state.ensure(V, "app")
    rec.update(phase="apply", change="add-run-end-reason", title="BL-003")
    d.state.save()
    return d, lines


def update_hub(env, fn):
    data = json.loads(env.ho_data.read_text())
    fn(data)
    env.ho_data.write_text(json.dumps(data))


def log_events(env, kind):
    lines = (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["event"] == kind]


def list_calls(env):
    return [c for c in env.ho_calls() if c["args"][0] == "list"]


def test_held_item_runs_no_session_and_the_awaited_team_goes_first(env):
    d, lines = setup(env)
    assert [c.handover for c in d.plan()] == [V, G]  # newer activity: V would go first without the hold
    env.set_claude([{"steps": [START], "result": {"result": "Created.\nCHANGE: add-st-35"}}])
    assert d.loop(once=True) == 0
    [call] = env.claude_calls()
    assert call["cwd"].endswith("backend") and G in call["argv"][1]
    assert d.state.get(V)["waiting_for"] == [{"handover": G, "team": "backend", "state": "pending"}]
    assert d.state.get(V)["sessions"] == []
    [start] = [x for x in lines if f"{V} (app) waits for" in x]
    assert start.endswith(f"waits for {G} (backend, pending); not selected until it is finished")
    [event] = log_events(env, "waiting_for_handover")
    assert (event["handover"], event["team"], event["waits"]) == (V, "app", d.state.get(V)["waiting_for"])


def test_one_start_line_one_list_per_team_and_no_stall(env):
    d, lines = setup(env, site_inbox=False)
    for n in range(3):
        before = len(list_calls(env))
        assert d.loop(once=True) == 0
        assert len(list_calls(env)) - before == len(d.cfg.teams)  # one `ho list` per team per iteration
    assert env.claude_calls() == []
    assert len([x for x in lines if "waits for" in x]) == 1 and len(log_events(env, "waiting_for_handover")) == 1
    rec = d.state.get(V)
    assert rec["no_progress"] == 0 and not rec["flags"]["stalled"] and not rec["flags"]["escalated"]


def test_result_arrives_releases_the_item(env):
    d, lines = setup(env, site_inbox=False)
    d.loop(once=True)

    def done(data):
        data["list:app"]["items"][0]["recipients"] = {"backend": "done"}
        data["inbox:app"]["to_review"] = [item(G, title="Build ST-35", sender="app", last=NEW)]
    update_hub(env, done)
    held = d.update_holds(d.scan_sent())
    assert held == {} and "waiting_for" not in d.state.get(V)
    assert [x for x in lines if "selectable again" in x] == [lines[-1]]
    assert lines[-1].endswith(f"{V} (app): {G} finished; selectable again")
    [event] = log_events(env, "wait_ended")
    assert (event["handover"], event["team"], event["handovers"]) == (V, "app", [G])
    assert sorted((c.kind, c.handover) for c in d.plan()) == [("review", G), ("work", V)]


def test_returned_part_holds_again(env):
    d, lines = setup(env, site_inbox=False)
    update_hub(env, lambda data: data["list:app"]["items"][0].update(recipients={"backend": "done"}))
    assert d.update_holds(d.scan_sent()) == {}
    update_hub(env, lambda data: data["list:app"]["items"][0].update(recipients={"backend": "returned"}))
    assert d.update_holds(d.scan_sent())[V][0]["state"] == "returned"
    assert d.plan() == []


def test_failing_list_keeps_the_stored_hold(env):
    d, lines = setup(env, site_inbox=False)
    d.loop(once=True)
    update_hub(env, lambda data: data.update({"list:app": {"exit": 1, "error": {"code": "usage",
                                                                                        "message": "broken"}}}))
    held = d.update_holds(d.scan_sent())
    assert held == {V: d.state.get(V)["waiting_for"]} and d.plan(held) == []
    assert log_events(env, "wait_ended") == [] and any("! ho list --from app failed" in x for x in lines)


def test_dry_run_lists_held_items_and_sends_nothing(env, capsys):
    setup(env)
    capsys.readouterr()
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"Held (waits for a handover's result): {V} (app) waits for {G} (backend, pending)" in out
    assert f"Would start: backend" in out and f"handover {G}" in out
    candidates = out.split("Candidates (newest first):")[1].split("Would start")[0]
    assert V not in candidates
    assert [c for c in env.ho_calls() if c["args"][0] in ("new", "close", "sync")] == []
    assert env.claude_calls() == []
    assert "waiting_for" not in json.loads((env.root / "run" / "state.json").read_text())["handovers"][V]


# ---- harness-no-loop-while-blocked N1: a return releases a held item for one session

RET1, SESS, RET2 = "2026-10-25T12:40:00.000Z", "2026-10-25T12:45:00.000Z", "2026-10-25T12:50:00.000Z"


def returned_setup(env, returns=(RET1,)):
    """V is held (G to `backend` pending) and was returned by its sender at the given times."""
    d, lines = setup(env)
    events = [(NEW, "owner", "respond", "ok")] + [(at, "product", "return", "Fix X.", "app")
                                                   for at in returns]
    update_hub(env, lambda data: data.update({
        f"show:{V}": show(V, events, title="BL-003"),
        "inbox:app": {"action_required": [item(V, title="BL-003", my_state="returned", last=returns[-1])]}}))
    return d, lines


def held_plan(d):
    return d.plan(d.update_holds(d.scan_sent()))


def add_session(d, started, team="app"):
    d.state.get(V)["sessions"].append({"id": "s", "team": team, "phase": "apply", "outcome": "finished",
                                       "started": started, "ended": started})
    d.state.save()


def test_returned_held_item_selected_once(env):
    d, _ = returned_setup(env)
    assert [c.handover for c in held_plan(d)][0] == V
    add_session(d, "2026-10-25T12:30:00.000Z")  # a session before the return does not use it
    assert V in [c.handover for c in held_plan(d)]
    add_session(d, SESS)
    assert [c.handover for c in held_plan(d)] == [G]


def test_session_of_another_team_does_not_use_the_return(env):
    d, _ = returned_setup(env)
    add_session(d, SESS, team="product")
    assert V in [c.handover for c in held_plan(d)]


def test_returned_again_selected_once_more(env):
    d, _ = returned_setup(env, returns=(RET1, RET2))
    add_session(d, SESS)
    assert [c.handover for c in held_plan(d)][0] == V
    add_session(d, "2026-10-25T12:55:00.000Z")
    assert [c.handover for c in held_plan(d)] == [G]


def test_resume_after_timeout_still_selected(env):
    d, _ = returned_setup(env)
    add_session(d, SESS)
    d.state.get(V)["resume_after_timeout"] = {"session": "s", "team": "app", "phase": "apply",
                                              "reason": "max_time"}
    d.state.save()
    assert V in [c.handover for c in held_plan(d)]


# 2026-10-31: product returned 7q4q to app while app's 3yyl to backend was pending
Q7, Y3 = "HO-20261031-7q4q", "HO-20261031-3yyl"
R_AT, Y_AT = "2026-10-31T17:27:00.000Z", "2026-10-31T16:00:00.000Z"


def replay_hub(env):
    env.set_hub({
        "list:app": {"items": [{"id": Y3, "title": "Backend part", "from": "app", "to": ["backend"],
                                        "expects": "done", "status": "open", "refs": [Q7],
                                        "recipients": {"backend": "pending"}, "created": Y_AT, "last_activity": Y_AT}]},
        f"show:{Q7}": show(Q7, [(R_AT, "product", "return", "Report done again once backend has it.",
                                 "app")], title="Flash provider"),
        f"show:{Y3}": show(Y3, created=Y_AT, title="Backend part"),
        "inbox:app": {"action_required": [item(Q7, title="Flash provider", my_state="returned", last=R_AT)]},
        "inbox:backend": {"action_required": [item(Y3, title="Backend part", sender="app", last=Y_AT)]}})
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.state.ensure(Q7, "app").update(phase="apply", change="flash-provider", title="Flash provider")
    d.state.save()
    return d


def test_replay_7q4q_site_goes_after_one_return_session(env):
    d = replay_hub(env)
    assert [(c.team, c.handover) for c in held_plan(d)] == [("app", Q7), ("backend", Y3)]
    env.set_claude([{"steps": [START], "result": {"result": "Backend part still pending; stopping."}}])
    assert d.loop(once=True) == 0
    [call] = env.claude_calls()
    assert call["cwd"].endswith("app") and Q7 in call["argv"][1]
    assert [(c.team, c.handover) for c in held_plan(d)] == [("backend", Y3)]


def test_replay_7q4q_plan_predicts_the_same_order(env, capsys):
    replay_hub(env)
    capsys.readouterr()
    assert main(["--config", str(env.config_path), "plan", "--steps", "2"]) == 0
    out = capsys.readouterr().out
    first, second = [x for x in out.splitlines() if x.lstrip().startswith(("1.", "2."))][:2]
    assert "app" in first and Q7 in first
    assert "backend" in second and Y3 in second
