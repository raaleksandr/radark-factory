"""A permission denial in a session that completed its phase is not escalated (change
escalate-denial-only-if-phase-incomplete)."""
import json

import pytest

from harness import prompts
from harness.__main__ import Dispatcher, goal_report
from harness.runner import SessionResult
from harness.select import Candidate
from harness.state import GoalRun
from harness.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
BEFORE = "2026-10-16T09:30:00.000Z"
LATER = "2099-01-01T00:00:00.000Z"
SINCE = "2026-10-16T10:00:00.000Z"
STOP = {"tool_name": "PowerShell", "tool_use_id": "t1",
        "tool_input": {"command": "Get-CimInstance Win32_Process | Stop-Process -Force"}}
DONE = [(LATER, "app", "done", "All tasks finished.")]


def disp(env, lines=None):
    return Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))


def log_events(env, kind=None):
    events = [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    return [e for e in events if kind is None or e["event"] == kind]


def new_calls(env):
    return [c for c in env.ho_calls() if c["args"][0] == "new"]


def prompt_of(call) -> str:
    return call["argv"][call["argv"].index("-p") + 1] if "-p" in call["argv"] else call["argv"][1]


def apply_item(env, events=(), lines=None):
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]},
                 f"show:{A}": show(A, events)})
    d = disp(env, lines)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    d.state.save()
    return d


def denied(*steps, result="Done; stopped the test run with TaskStop instead.", denials=(STOP,)):
    return {"steps": [START, *steps], "result": {"result": result, "permission_denials": list(denials)}}


def result(phase="apply", **kw):
    base = dict(run_id="run-1", session_id="sess-1", team="app", handover=A, phase=phase, started=SINCE,
                outcome="waiting_for_owner", exit_code=0, has_result=True, hooks_loaded=True, denials=[STOP])
    base.update(kw)
    return SessionResult(**base)


def cand_for(d, phase, team="app"):
    return Candidate(kind=phase if phase in ("review", "archive") else "work", team=team, handover=A, title="Task",
                     phase=phase, recency="", team_index=0, change="add-x")


# ---- the completion check (task 1.1)

@pytest.mark.parametrize("phase, events, complete", [
    ("apply", DONE, True),
    ("apply", [(LATER, "app", "decline", "Not possible.")], True),
    ("apply", [(LATER, "app", "comment", "Half way.")], False),
    ("apply", [(BEFORE, "app", "done", "An earlier round.")], False),
    ("act", DONE, True),
    ("review", [(LATER, "product", "close", "")], True),
    ("review", [(LATER, "product", "return", "Add a header.", "app")], True),
    ("review", [(LATER, "product", "comment", "Looking.")], False),
    ("review", [(BEFORE, "product", "close", "")], False),
])
def test_phase_complete_from_hub_events(env, phase, events, complete):
    env.set_hub({f"show:{A}": show(A, events)})
    d = disp(env)
    team = "product" if phase == "review" else "app"
    rec = d.state.ensure(A, "app")
    assert d.phase_complete(cand_for(d, phase, team), rec, result(phase), SINCE) is complete


def test_phase_complete_when_ho_show_fails(env):
    env.set_hub({f"show:{A}": {"exit": 1, "error": {"code": "io", "message": "hub unreadable"}}})
    d = disp(env)
    assert d.phase_complete(cand_for(d, "apply"), d.state.ensure(A, "app"), result(), SINCE) is False


def test_phase_complete_propose_and_archive(env):
    env.set_hub({})
    d = disp(env)
    rec = d.state.ensure(A, "app")
    assert d.phase_complete(cand_for(d, "propose"), rec, result("propose", result_text="CHANGE: add-x"), SINCE)
    assert not d.phase_complete(cand_for(d, "propose"), rec, result("propose", result_text="No change."), SINCE)
    rec["change"] = "add-x"
    changes = env.root / "repos" / "app" / "openspec" / "changes"
    (changes / "add-x").mkdir()
    assert not d.phase_complete(cand_for(d, "archive"), rec, result("archive"), SINCE)
    (changes / "add-x").rmdir()
    assert d.phase_complete(cand_for(d, "archive"), rec, result("archive"), SINCE)
    rec["change"] = None
    assert not d.phase_complete(cand_for(d, "archive"), rec, result("archive"), SINCE)


# ---- the outcome (task 1.2)

def test_denial_in_completed_apply_is_not_escalated(env):
    d = apply_item(env, DONE)
    env.set_claude([denied()])
    d.loop(once=True)
    rec = d.state.get(A)
    assert new_calls(env) == [] and not d.state.blocked(A)
    assert rec["phase"] == "done" and rec["no_progress"] == 0
    data = json.loads(env.ho_data.read_text())
    data.pop("inbox:app")
    data["inbox:product"] = {"to_review": [item(A, sender="product")]}
    env.set_hub(data)
    (cand,) = d.plan()
    assert (cand.kind, cand.team, cand.phase) == ("review", "product", "review")


def test_denial_without_done_escalates(env):
    d = apply_item(env)
    env.set_claude([denied(result="Could not stop the test run.")])
    d.loop(once=True)
    assert d.state.blocked(A) and "permission denied: PowerShell" in d.state.get(A)["reason"]
    [call] = new_calls(env)
    assert "permission denied: PowerShell" in call["stdin"]
    assert log_events(env, "denial_not_escalated") == []


def test_denial_and_escalation_marker_escalate_with_both_reasons(env):
    d = apply_item(env, DONE)
    risky = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion",
                                             "tool_input": {"questions": [{"question": "Push to the remote?"}]}}}
    env.set_claude([denied(risky)])
    d.loop(once=True)
    reason = d.state.get(A)["reason"]
    assert d.state.blocked(A) and "asked:" in reason and "permission denied: PowerShell" in reason


def test_denial_in_session_cut_by_max_time_escalates(env):
    env.set_hub({f"show:{A}": show(A, DONE)})
    d = disp(env)
    rec = d.state.ensure(A, "app")
    r = result(exit_code=None, has_result=False, timed_out=True, timeout_reason="max_time", killed=True)
    d.after_session(cand_for(d, "apply"), rec, r, SINCE)
    assert r.outcome == "waiting_for_owner" and d.state.blocked(A)
    assert "permission denied: PowerShell" in rec["reason"]


def test_denial_in_propose_that_created_its_change(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([denied(result="Created the change.\nCHANGE: add-x")])
    d = disp(env)
    d.loop(once=True)
    rec = d.state.get(A)
    assert not d.state.blocked(A) and (rec["change"], rec["phase"]) == ("add-x", "propose")


# ---- visibility (tasks 2.1, 2.2)

def test_console_and_run_log(env, monkeypatch):
    monkeypatch.setattr("harness.__main__.utf8_console", lambda: True)
    lines = []
    d = apply_item(env, DONE, lines)
    env.set_claude([denied()])
    d.loop(once=True)
    marked = [x[9:] for x in lines if x[5:9] == "  ! "]
    assert marked == [f"app {A}: permission denied: PowerShell",
                      f"app {A}: phase completed despite the permission denial (PowerShell); not escalated"]
    assert [e["event"] for e in log_events(env) if e["event"].startswith("denial")] == [
        "denial", "denial_not_escalated"]
    [event] = log_events(env, "denial_not_escalated")
    session = log_events(env, "session_end")[0]["session"]
    assert (event["team"], event["handover"], event["phase"], event["session"]) == ("app", A, "apply", session)
    [x] = event["denials"]
    assert (x["tool"], x["input"], x["phase"], x["session"]) == (
        "PowerShell", STOP["tool_input"]["command"], "apply", session)
    assert log_events(env, "session_end")[0]["outcome"] == "waiting_for_owner"  # the raw outcome (design D1)


def test_review_prompt_names_denials():
    c = Candidate(kind="review", team="product", handover=A, title="Task", phase="review", recency="",
                  team_index=0)
    text = prompts.phase_prompt(c, denials=[{"tool": "PowerShell", "input": "Stop-Process -Force"}])
    assert "were denied by the permission mode" in text and "- PowerShell: `Stop-Process -Force`" in text
    assert "if something was, return the handover" in text
    assert "denied" not in prompts.phase_prompt(c) and prompts.phase_prompt(c) == prompts.phase_prompt(c, denials=[])


def test_long_input_is_shortened(env):
    d = apply_item(env, DONE)
    env.set_claude([denied(denials=[{"tool_name": "Bash", "tool_input": {"command": "x" * 500}},
                                    {"tool_name": "WebFetch", "tool_input": {"url": "https://example.org"}}])])
    d.loop(once=True)
    first, second = d.state.get(A)["unescalated_denials"]
    assert len(first["input"]) == 200 and first["input"].startswith("xxx")
    assert second["input"] == '{"url": "https://example.org"}'


def test_review_after_not_escalated_denial(env):
    d = apply_item(env, DONE)
    env.set_claude([denied(), {"steps": [START], "result": {"result": "Returned."}},
                    {"steps": [START], "result": {"result": "Fixed."}}])
    d.loop(once=True)
    assert d.state.get(A)["unescalated_denials"][0]["tool"] == "PowerShell"
    data = json.loads(env.ho_data.read_text())
    data.pop("inbox:app")
    data["inbox:product"] = {"to_review": [item(A, sender="product")]}
    env.set_hub(data)
    d.loop(once=True)
    review = prompt_of(env.claude_calls()[1])
    assert "Phase: review" in review and "- PowerShell: `Get-CimInstance Win32_Process | Stop-Process -Force`" in review
    assert "unescalated_denials" not in d.state.get(A)
    data = json.loads(env.ho_data.read_text())  # returned to the worker: a fresh apply
    data.pop("inbox:product")
    data["inbox:app"] = {"action_required": [item(A, my_state="returned")]}
    data[f"show:{A}"]["events"].append({"at": LATER, "team": "product", "action": "return",
                                        "body": "Add a header.", "target": "app"})
    env.set_hub(data)
    d.loop(once=True)
    apply = prompt_of(env.claude_calls()[2])
    assert "Phase: apply" in apply and "denied" not in apply and "unescalated_denials" not in d.state.get(A)


# ---- the goal report (task 2.3)

def test_goal_report_lists_denials_not_escalated(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    d = apply_item(env, DONE)
    d.start_goal(GoalRun(path, "Finish B-1.", 1, 12))
    env.set_claude([denied()])
    assert d.loop() == 6  # the session limit ends the run
    [x] = log_events(env, "goal_result")[0]["unescalated_denials"]
    assert (x["handover"], x["team"], x["phase"], x["tool"]) == (A, "app", "apply", "PowerShell")
    report = goal_report(d.goal, "product")
    assert "## Permission denials not escalated" in report
    assert (f"- {A} (app, apply): PowerShell `Get-CimInstance Win32_Process | Stop-Process -Force`"
            in report)


def test_goal_report_without_denials(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    d = apply_item(env, DONE)
    d.start_goal(GoalRun(path, "Finish B-1.", 1, 12))
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    assert d.loop() == 6
    assert log_events(env, "goal_result")[0]["unescalated_denials"] == []
    assert "Permission denials not escalated" not in goal_report(d.goal, "product")
