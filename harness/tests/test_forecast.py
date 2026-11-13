"""Predicted next steps on recorded hub snapshots (change predict-next-steps, tasks 2.1–2.6)."""
import copy

from harness import forecast
from harness.state import new_record
from harness.tests.conftest import TEAMS, item, show

A, B, C = "HO-20261016-aaaa", "HO-20261016-bbbb", "HO-20261016-cccc"
T1, T2 = "2026-10-16T10:00:00.000Z", "2026-10-16T11:00:00.000Z"
NOW = "2026-10-16T12:00:00.000Z"


def inbox(ar=(), tr=()):
    return {"action_required": list(ar), "to_review": list(tr), "updates": []}


def rec(team, **kw):
    return {**new_record(team), **kw}


def hshow(hid, sender="product", to=("app",), expects="done", events=(), status="open",
          created=T1, title="Task", states=None, auto_close=False):
    """`ho show` with the fields the simulation reads: from, to, expects, recipients, auto_close."""
    s = show(hid, events, status=status, created=created, title=title)
    s.update({"from": sender, "to": list(to), "expects": expects, "auto_close": auto_close,
              "recipients": states or {t: "pending" for t in to}})
    return s


def sim(inboxes, shows, records=None, held=None, steps=5, **kw):
    return forecast.simulate(TEAMS, inboxes, shows, records or {}, held, steps, NOW, **kw)


def path(f):
    return [(s.team, s.phase, s.handover) for s in f.steps]


# ---- 2.1 stops and inputs

def test_goal_check_ends_the_prediction():
    f = sim({}, {}, goal=True, product="product")
    assert path(f) == [("product", "goal check", None)]
    assert "verdict" in f.stop


def test_idle_without_a_goal():
    f = sim({}, {})
    assert f.steps == [] and "idle" in f.stop and "idle ask" not in f.stop
    assert "idle ask" in sim({}, {}, idle_ask=True).stop


def test_step_count_reached_has_no_stop_reason():
    f = sim({"app": inbox([item(A)])}, {A: hshow(A)}, steps=1)
    assert path(f) == [("app", "propose", A)] and f.stop is None


def test_inputs_not_changed():
    inboxes = {"app": inbox([item(A)])}
    shows = {A: hshow(A)}
    records = {B: rec("app", phase="done", change="x")}
    held = {C: [{"handover": A, "team": "app", "state": "pending", "title": ""}]}
    before = copy.deepcopy((inboxes, shows, records, held))
    sim(inboxes, shows, records, held, steps=10, goal=True)
    assert (inboxes, shows, records, held) == before


def test_synthetic_time_starts_after_the_snapshot():
    later = "2026-10-17T00:00:00.000Z"
    assert forecast.ts(forecast.start_time(NOW, {}, {A: hshow(A, created=later)})) == "2026-10-17T00:00:01.000Z"
    assert forecast.ts(forecast.start_time(NOW, {}, {})) == "2026-10-16T12:00:01.000Z"


# ---- 2.2 propose -> apply

def test_propose_then_apply_on_the_same_handover():
    inboxes = {"app": inbox([item(A, last=T1)]), "backend": inbox([item(B, sender="app", last=T2)])}
    shows = {A: hshow(A, created=T2), B: hshow(B, sender="app", to=("backend",), created=T1)}
    f = sim(inboxes, shows, steps=2)
    assert path(f) == [("app", "propose", A), ("app", "apply", A)]
    assert f.steps[0].outcome == "change to be proposed"


# ---- 2.3 apply / act outcomes

def test_apply_per_expects():
    for expects in ("done", "response", "ack"):
        inboxes = {"app": inbox([item(A, my_state="acknowledged", expects=expects)])}
        shows = {A: hshow(A, expects=expects, states={"app": "acknowledged"})}
        records = {A: rec("app", change="add-x", phase="propose")}
        f = sim(inboxes, shows, records, steps=3)
        archive = [("app", "archive", A)] if expects == "done" else []
        assert path(f) == [("app", "apply", A), ("product", "review", A)] + archive, expects


def test_product_act_finishes_a_technical_teams_request():
    inboxes = {"product": inbox([item(A, sender="app", expects="response")])}
    shows = {A: hshow(A, sender="app", to=("product",), expects="response")}
    f = sim(inboxes, shows)
    assert path(f) == [("product", "act", A), ("app", "review", A)]
    assert "idle" in f.stop


def test_two_recipients_review_only_after_both():
    inboxes = {"app": inbox([item(A, my_state="acknowledged", last=T2)]),
               "backend": inbox([item(A, my_state="acknowledged", last=T2)])}
    shows = {A: hshow(A, to=("app", "backend"), states={"app": "acknowledged", "backend": "acknowledged"},
                      created=T2)}
    records = {A: rec("app", change="add-x", phase="propose")}
    f = sim(inboxes, shows, records, steps=3)
    assert path(f)[:2] == [("app", "apply", A), ("backend", "apply", A)]
    assert f.steps[0].outcome.startswith("part finished") and path(f)[2] == ("product", "review", A)


def test_auto_close_needs_no_review():
    inboxes = {"app": inbox([item(A, my_state="acknowledged")])}
    shows = {A: hshow(A, auto_close=True, states={"app": "acknowledged"})}
    f = sim(inboxes, shows, {A: rec("app", change="add-x", phase="propose")})
    assert path(f) == [("app", "apply", A), ("app", "archive", A)]


def test_unconfigured_sender_gets_no_review_step():
    inboxes = {"app": inbox([item(A, sender="owner", my_state="acknowledged")])}
    shows = {A: hshow(A, sender="owner", states={"app": "acknowledged"})}
    f = sim(inboxes, shows, {A: rec("app", change="add-x", phase="propose")})
    assert path(f) == [("app", "apply", A)]
    assert f.steps[0].outcome == "finished; waits for owner" and any(f"{A} waits for owner" in n for n in f.notes)


# ---- 2.4 review -> archive

def test_apply_review_archive_in_order_and_archive_by_close_time():
    old = "2026-10-15T09:00:00.000Z"
    inboxes = {"app": inbox([item(A, my_state="acknowledged")])}
    shows = {A: hshow(A, states={"app": "acknowledged"}),
             B: hshow(B, to=("backend",), status="closed", events=[(old, "product", "close", "")])}
    records = {A: rec("app", change="add-x", phase="propose"), B: rec("backend", change="y", phase="done")}
    f = sim(inboxes, shows, records, goal=True, product="product")
    assert path(f) == [("app", "apply", A), ("product", "review", A),
                       ("app", "archive", A), ("backend", "archive", B),
                       ("product", "goal check", None)]
    assert sum(1 for s in f.steps if s.handover == A and s.phase == "archive") == 1


# ---- 2.5 holds and time-limited sessions

def test_held_item_released_after_the_other_teams_apply():
    inboxes = {"app": inbox([item(A, my_state="acknowledged", last=T2)]),
               "backend": inbox([item(B, sender="app", my_state="acknowledged", last=T1)])}
    shows = {A: hshow(A, states={"app": "acknowledged"}, created=T2),
             B: hshow(B, sender="app", to=("backend",), states={"backend": "acknowledged"}, created=T1)}
    records = {A: rec("app", change="add-x", phase="apply"), B: rec("backend", change="y", phase="propose")}
    held = {A: [{"handover": B, "team": "backend", "state": "acknowledged", "title": ""}]}
    f = sim(inboxes, shows, records, held, steps=4)
    assert path(f) == [("backend", "apply", B), ("app", "review", B), ("backend", "archive", B),
                       ("app", "apply", A)]


def test_returned_held_item_gets_one_session_then_the_awaited_team():
    """2026-10-31 shape (no-loop N1): product returned A while app's B to backend is pending."""
    inboxes = {"app": inbox([item(A, my_state="returned", last=T2)]),
               "backend": inbox([item(B, sender="app", last=T1)])}
    shows = {A: hshow(A, states={"app": "returned"},
                      events=[(T2, "product", "return", "Report done once backend has it.", "app")]),
             B: hshow(B, sender="app", to=("backend",), created=T1)}
    records = {A: rec("app", change="add-x", phase="apply")}
    held = {A: [{"handover": B, "team": "backend", "state": "pending", "title": ""}]}
    f = sim(inboxes, shows, records, held, steps=3)
    assert path(f)[:2] == [("app", "apply", A), ("backend", "propose", B)]
    assert "held again" in f.steps[0].outcome
    assert records[A]["sessions"] == []  # the input is not changed


def test_timed_out_apply_finishes_its_phase():
    cut = {"session": "sess-1", "team": "app", "phase": "apply", "reason": "max_time", "duration_s": 10800}
    inboxes = {"app": inbox([item(A, my_state="acknowledged")])}
    shows = {A: hshow(A, states={"app": "acknowledged"})}
    records = {A: rec("app", change="add-x", phase="apply", resume_after_timeout=cut)}
    f = sim(inboxes, shows, records, steps=3)
    assert path(f) == [("app", "apply", A), ("product", "review", A), ("app", "archive", A)]
    assert f.steps[0].resume and not f.steps[2].resume


def test_skipped_items_are_not_predicted():
    f = sim({"app": inbox([item(A)])}, {A: hshow(A)}, skip={A})
    assert f.steps == []


# ---- 2.6 the spec's "Five steps ahead" (hub of 2026-10-26)

RBKB, VOZR, GHYL = "HO-20261026-rbkb", "HO-20261025-vozr", "HO-20261025-ghyl"


def test_five_steps_ahead():
    ack = "2026-10-26T15:00:57.335Z"
    inboxes = {"backend": inbox([item(RBKB, title="Deploy ST-35 to production now", my_state="acknowledged", last=ack)]),
               "app": inbox(), "product": inbox()}
    shows = {RBKB: hshow(RBKB, to=("backend",), states={"backend": "acknowledged"}, created="2026-10-26T13:55:05.700Z",
                         events=[(ack, "backend", "ack", "")], title="Deploy ST-35 to production now"),
             VOZR: hshow(VOZR, status="closed", title="BL-003", created="2026-10-25T08:00:00.000Z",
                         events=[("2026-10-25T16:20:00.000Z", "app", "done", ""),
                                 ("2026-10-25T17:10:00.000Z", "product", "close", "")])}
    records = {RBKB: rec("backend", change="deploy-st-35", phase="propose"),
               VOZR: rec("app", change="add-run-end-reason", phase="done"),
               GHYL: rec("backend", change="app-run-close-reason", phase="archived")}
    f = forecast.simulate(TEAMS, inboxes, shows, records, {}, 5, "2026-10-26T15:30:00.000Z", goal=True,
                          product="product")
    assert path(f) == [("backend", "apply", RBKB), ("product", "review", RBKB), ("backend", "archive", RBKB),
                       ("app", "archive", VOZR), ("product", "goal check", None)]
    assert "verdict" in f.stop


# ---- 3.1, 3.2 the `plan` command with the fake `ho`

def plan_hub(env):
    """app has a proposed change for A; backend has a new handover B from app (newer)."""
    from harness.__main__ import Dispatcher
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged", last=T1)]},
                 "inbox:backend": {"action_required": [item(B, sender="app", last=T2)]},
                 f"show:{A}": hshow(A, states={"app": "acknowledged"}, events=[(T1, "app", "ack", "")]),
                 f"show:{B}": hshow(B, sender="app", to=("backend",), created=T2)})
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    d.state.save()


def goal_files(env, given=None):
    import json
    goal = env.root / "goal.md"
    goal.write_text("Finish B-1.", encoding="utf-8")
    (env.root / "run" / "goal.json").write_text(json.dumps(
        {"path": str(goal), "status": "limit", "given_text": "Finish B-1." if given is None else given}))
    return goal


def files(env):
    run = env.root / "run"
    return {p.name: p.read_bytes() for p in [env.ho_data, run / "state.json", run / "goal.json"] if p.exists()}


def test_plan_prints_the_steps_and_writes_nothing(env, capsys):
    from harness.__main__ import main
    plan_hub(env)
    goal = goal_files(env)
    before = files(env)
    assert main(["--config", str(env.config_path), "plan", "--goal", str(goal), "--max-sessions", "2",
                 "--steps", "6"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert files(env) == before
    run = env.root / "run"
    assert not (run / "runs.jsonl").exists() and not (run / "console.log").exists() and not (run / "lock").exists()
    assert [c for c in env.claude_calls()] == []
    assert lines[0].startswith("Usage:") and "Plan (if every step succeeds):" in lines
    steps = [x.split()[1:4] for x in lines if x.startswith("  ") and x.strip()[0].isdigit()]
    assert steps == [["backend", "propose", B], ["backend", "apply", B], ["app", "review", B],
                     ["backend", "archive", B], ["app", "apply", A], ["product", "review", A]]
    marker = lines.index("  --max-sessions 2 ends the run here")
    assert lines[marker - 1].split()[1:3] == ["backend", "apply"]
    assert lines[-1].startswith("Assumes: reviews accept the work")


def test_plan_stops_at_the_goal_check(env, capsys):
    from harness.__main__ import main
    plan_hub(env)
    assert main(["--config", str(env.config_path), "plan", "--goal", str(goal_files(env)), "--steps", "20"]) == 0
    lines = capsys.readouterr().out.splitlines()
    last = [x for x in lines if x.startswith("  ") and x.strip()[0].isdigit()][-1]
    assert last.split()[1:] == ["product", "goal", "check"]
    assert lines[lines.index(last) + 1] == "Stops: the next steps depend on the goal check's verdict."


def test_plan_with_carried_guidance_is_one_goal_check(env, capsys):
    from harness.__main__ import main
    plan_hub(env)
    goal = goal_files(env, given="Finish B-0.")
    before = files(env)
    assert main(["--config", str(env.config_path), "plan", "--goal", str(goal)]) == 0
    lines = capsys.readouterr().out.splitlines()
    steps = [x for x in lines if x.startswith("  1.")]
    assert len(steps) == 1 and "goal check" in steps[0] and not any(x.startswith("  2.") for x in lines)
    assert any(x.startswith("Stops: the product team has not received") for x in lines)
    assert files(env) == before


def test_plan_with_an_owner_answer_resumes_it_first(env, capsys):
    from harness.__main__ import Dispatcher, main
    import json
    plan_hub(env)
    data = json.loads(env.ho_data.read_text())
    data["show:HO-ESC-1"] = hshow("HO-ESC-1", sender="app", to=("owner",), expects="response",
                                  events=[(T2, "owner", "respond", "Go ahead.")])
    env.ho_data.write_text(json.dumps(data))
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.state.escalate(A, "app", "asked: deploy?")
    d.state.get(A)["escalation"] = {"handover": "HO-ESC-1", "team": "app", "session": "s-1", "phase": "apply",
                                    "answered": False}
    d.state.save()
    before = files(env)
    assert main(["--config", str(env.config_path), "plan"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [x.split()[1:4] for x in lines if x.startswith("  1.")] == [["app", "apply", A]]
    assert any("owner's answer on HO-ESC-1" in x for x in lines) and files(env) == before


def test_plan_without_a_goal_ends_idle_and_refuses_max_sessions(env, capsys):
    from harness.__main__ import main
    plan_hub(env)
    assert main(["--config", str(env.config_path), "plan", "--steps", "20"]) == 0
    assert "Stops: nothing left to pick: the dispatcher would be idle" in capsys.readouterr().out
    assert main(["--config", str(env.config_path), "plan", "--max-sessions", "2"]) == 2


def test_first_plan_step_is_what_dry_run_would_start(env, capsys):
    from harness.__main__ import main
    plan_hub(env)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    start = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("Would start:"))
    assert main(["--config", str(env.config_path), "plan", "--steps", "1"]) == 0
    first = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("  1."))
    team, phase, hid = first.split()[1:4]
    assert start.startswith(f"Would start: {team} in ") and f"phase {phase}, handover {hid}" in start
