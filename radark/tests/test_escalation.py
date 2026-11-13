"""Escalation to the owner through the hub and the owner's answer (change owner-escalation-via-hub)."""
import json
import os
import subprocess

import pytest

from radark.__main__ import Dispatcher, main
from radark.tests.conftest import ASK_STEP, START, item, show, stop_step

A = "HO-20261016-aaaa"
LATER = "2099-01-01T00:00:00.000Z"
RISKY = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion",
                                          "tool_input": {"questions": [{"question": "Push to the remote?"}]}}}


def disp(env):
    return Dispatcher(env.cfg(), out=lambda *a: None)


def log_events(env, kind=None):
    events = [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    return [e for e in events if kind is None or e["event"] == kind]


def hub_data(env):
    return json.loads(env.ho_data.read_text())


def new_calls(env):
    return [c for c in env.ho_calls() if c["args"][0] == "new"]


def owner(env, action, hid, message):
    cfg = env.cfg()
    subprocess.run(cfg.ho + [action, hid, "-m", message], env=dict(os.environ, HO_TEAM="owner"),
                   check=True, capture_output=True)


def escalated_by_question(env, inbox=True):
    """inbox=False: A leaves the inbox after the session, so only the owner's answer can start work again."""
    env.set_hub({f"show:{A}": show(A), "inbox:app": {"action_required": [item(A)]}})
    env.set_claude([{"steps": [START, RISKY, stop_step("The owner must decide whether to push.")],
                     "result": {"result": "I need the owner to decide whether to push."}}])
    d = disp(env)
    d.loop(once=True)
    if not inbox:
        data = hub_data(env)
        data.pop("inbox:app")
        env.set_hub(data)
    return d


# ---- escalation out (tasks 3.1, 3.2)

def test_keyword_question_sends_escalation_handover(env):
    d = escalated_by_question(env)
    [call] = new_calls(env)
    session = env.claude_calls()[0]["argv"][env.claude_calls()[0]["argv"].index("--session-id") + 1]
    assert call["team"] == "app"
    args = call["args"]
    assert args[args.index("--to") + 1] == "owner" and args[args.index("--expects") + 1] == "response"
    assert args[args.index("--tag") + 1] == "escalation" and args[args.index("--ref") + 1] == A
    assert "--auto-close" in args and args[args.index("--title") + 1].startswith("app: asked:")
    body = call["stdin"]
    assert "Push to the remote?" in body and session in body and "phase propose" in body
    assert "I need the owner to decide" in body and f"python -m radark clear {A}" in body
    rec = d.state.get(A)
    assert rec["flags"]["escalated"]
    assert rec["escalation"]["handover"] == "HO-FAKE-0001" and rec["escalation"]["session"] == session
    assert rec["escalation"]["team"] == "app" and not rec["escalation"]["answered"]
    assert env.ho_calls()[-1]["args"] == ["sync"]
    assert log_events(env, "escalation_sent")[0]["escalation"] == "HO-FAKE-0001"
    assert hub_data(env)[f"show:{A}"]["events"] == []  # the item's own handover is untouched


def test_triage_owner_verdict_sends_handover_for_asking_session(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START, ASK_STEP, stop_step("Waiting.")], "result": {"result": "Referred."}},
                    {"steps": [START], "result": {"structured_output": {"verdict": "owner", "answer": "",
                                                                        "reason": "changes pricing"}}}])
    d = disp(env)
    d.loop(once=True)
    asked = env.claude_calls()[0]["argv"][env.claude_calls()[0]["argv"].index("--session-id") + 1]
    [call] = new_calls(env)
    assert call["team"] == "app" and "changes pricing" in call["stdin"] and "Use a Map" in call["stdin"]
    assert d.state.get(A)["escalation"]["session"] == asked


def test_permission_denial_sends_handover(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Blocked.",
                                                  "permission_denials": [{"tool_name": "Bash", "tool_input": {}}]}}])
    disp(env).loop(once=True)
    [call] = new_calls(env)
    assert "permission denied: Bash" in call["stdin"]


def test_stalled_item_sends_handover(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Still thinking about it."}}])
    d = disp(env)
    d.loop(once=True)
    assert new_calls(env) == []
    d.loop(once=True)
    [call] = new_calls(env)
    assert "stalled" in call["args"][call["args"].index("--title") + 1]
    assert "Still thinking about it." in call["stdin"] and d.state.get(A)["flags"]["stalled"]


def test_send_failure_keeps_item_escalated(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A),
                 "new": {"exit": 1, "error": {"code": "unknown_team", "message": "no team owner"}}})
    env.set_claude([{"steps": [START, RISKY], "result": {}}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.blocked(A) and d.state.get(A)["escalation"] is None
    assert "no team owner" in log_events(env, "escalation_send_failed")[0]["error"]


def test_one_open_escalation_per_item(env):
    d = escalated_by_question(env)
    d.escalate(A, "app", "stalled: 2 sessions without progress", stalled=True)
    assert len(new_calls(env)) == 1


# ---- answer in (tasks 4.1–4.3)

def test_owner_respond_resumes_same_session(env):
    d = escalated_by_question(env, inbox=False)
    asked = d.state.get(A)["escalation"]["session"]
    owner(env, "respond", "HO-FAKE-0001", "yes, push to the feature branch")
    env.set_claude([{"steps": [START], "result": {"result": "Pushed and done."}}])
    d = disp(env)
    assert d.loop(once=True) == 0
    call = env.claude_calls()[-1]
    assert call["argv"][call["argv"].index("--resume") + 1] == asked and call["cwd"].endswith("app")
    assert "yes, push to the feature branch" in call["argv"][1] and "Push to the remote?" in call["argv"][1]
    assert not d.state.blocked(A) and d.state.get(A)["escalation"] is None
    answer = log_events(env, "owner_answer")[0]
    assert (answer["action"], answer["escalation"], answer["session"]) == ("respond", "HO-FAKE-0001", asked)
    assert hub_data(env)["show:HO-FAKE-0001"]["status"] == "closed"
    assert main(["--config", str(env.config_path), "escalations"]) == 0


def test_work_before_the_question_counts_as_progress(env):
    d = escalated_by_question(env, inbox=False)
    asked = d.state.get(A)["sessions"][0]
    assert asked["started"] < asked["ended"]
    data = hub_data(env)  # the asking session acknowledged A before it stopped
    data[f"show:{A}"]["events"].append({"at": asked["ended"], "team": "app", "action": "ack", "body": ""})
    env.set_hub(data)
    owner(env, "respond", "HO-FAKE-0001", "no, keep it local")
    env.set_claude([{"steps": [START], "result": {"result": "Change created."}}])  # no hub write
    d = disp(env)
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0 and log_events(env, "no_progress") == []


def test_owner_decline_resumes_with_refusal_and_closes_open_handover(env):
    d = escalated_by_question(env, inbox=False)
    data = hub_data(env)
    data["no_auto_close_on_decline"] = True
    env.set_hub(data)
    owner(env, "decline", "HO-FAKE-0001", "no pushing before the release")
    env.set_claude([{"steps": [START], "result": {"result": "Continued without the push."}}])
    d = disp(env)
    d.loop(once=True)
    msg = env.claude_calls()[-1]["argv"][1]
    assert "The owner declined" in msg and "no pushing before the release" in msg and "Do not do that part" in msg
    close = [c for c in env.ho_calls() if c["args"][0] == "close"][0]
    assert close["team"] == "app" and "--force" in close["args"]
    assert hub_data(env)["show:HO-FAKE-0001"]["status"] == "closed"


def test_answer_after_clear_by_hand_is_ignored(env):
    escalated_by_question(env, inbox=False)
    assert main(["--config", str(env.config_path), "clear", A]) == 0
    owner(env, "respond", "HO-FAKE-0001", "yes")
    calls = len(env.claude_calls())
    d = disp(env)
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls
    assert log_events(env, "owner_answer") == []


def test_failed_resume_falls_back_to_fresh_session(env):
    escalated_by_question(env, inbox=False)
    owner(env, "respond", "HO-FAKE-0001", "yes, push")
    env.set_claude([{"steps": [START], "result": None, "exit": 1},  # e.g. the transcript is gone
                    {"steps": [START], "result": {"result": "Done."}}])
    disp(env).loop(once=True)
    resumed, fresh = env.claude_calls()[-2:]
    assert "--resume" in resumed["argv"] and "--session-id" in fresh["argv"]
    assert "Phase: propose" in fresh["argv"][1] and "The owner answered" in fresh["argv"][1]
    assert "yes, push" in fresh["argv"][1]


def test_waiting_escalation_does_not_block_other_work(env):
    escalated_by_question(env, inbox=False)
    calls = len(env.claude_calls())
    d = disp(env)
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls  # no answer yet, nothing else to do
    assert len(new_calls(env)) == 1


def test_dry_run_shows_answers_and_writes_nothing(env, capsys):
    escalated_by_question(env, inbox=False)
    owner(env, "respond", "HO-FAKE-0001", "yes, push")
    before = len(env.ho_calls())
    capsys.readouterr()
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Owner answered HO-FAKE-0001" in out and f"would clear {A}" in out
    assert all(c["args"][0] in ("--version", "inbox", "show", "list", "teams") for c in env.ho_calls()[before:])


# ---- idle verdict (task 5.1)

def idle_env(env, verdict):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\nidle_ask = true"))
    env.set_hub({"list:product": {"items": [{"id": A, "last_activity": "2026-10-16T10:00:00.000Z"}]}})
    result = {"structured_output": verdict} if isinstance(verdict, dict) else {"result": verdict}
    env.set_claude([{"steps": [START], "result": result}])
    d = disp(env)
    d.loop(once=True)
    d.loop(once=True)
    return d


def test_idle_none_with_owner_items_sends_one_handover(env):
    idle_env(env, {"verdict": "none", "reason": "the rest needs decisions",
                   "waiting_for_owner": [{"item": "BL-003 Pricing page", "why": "pricing"},
                                         {"item": "BL-004 Paid ads", "why": "spending"}]})
    assert len(env.claude_calls()) == 1
    assert "--json-schema" in env.claude_calls()[0]["argv"]
    [call] = new_calls(env)
    assert call["team"] == "product" and "--ref" not in call["args"]
    assert "escalation" in call["args"] and "BL-003 Pricing page" in call["stdin"] and "BL-004" in call["stdin"]
    assert "the rest needs decisions" in call["stdin"]
    assert log_events(env, "idle_verdict")[0]["verdict"] == "none"


def test_idle_none_without_owner_items_only_logs(env):
    idle_env(env, {"verdict": "none", "reason": "backlog empty", "waiting_for_owner": []})
    assert new_calls(env) == []
    assert log_events(env, "idle_verdict")[0]["reason"] == "backlog empty"


@pytest.mark.parametrize("verdict", ["none", {"verdict": "maybe", "reason": "", "waiting_for_owner": []}])
def test_idle_invalid_verdict_logged(env, verdict):
    idle_env(env, verdict)
    assert new_calls(env) == [] and len(log_events(env, "idle_verdict_invalid")) == 1


# ---- harness-no-loop-while-blocked N3: `BLOCKED: owner` escalates at once

P3 = "HO-20261031-p3uj"
BENCH = "BLOCKED: owner — go-ahead for a paid benchmark (up to $0.30)"


def blocked_apply(env, steps=(), result=BENCH, lines=None, events=()):
    env.set_hub({f"show:{P3}": show(P3, events, title="Faster provider"),
                 "inbox:backend": {"action_required": [item(P3, title="Faster provider", my_state="acknowledged")]}})
    env.set_claude([{"steps": [START, *steps], "result": {"result": f"Ran the free checks.\n{result}"}}] * 2)
    d = Dispatcher(env.cfg(), out=(lines.append if lines is not None else lambda *a: None))
    d.state.ensure(P3, "backend").update(change="app-faster-provider", phase="apply")
    d.state.save()
    return d


def test_blocked_on_owner_escalates_after_one_session(env):
    lines = []
    d = blocked_apply(env, lines=lines)
    d.loop(once=True)
    d.loop(once=True)
    assert len(env.claude_calls()) == 1  # not started again before the owner answers
    rec = d.state.get(P3)
    reason = "blocked on the owner: go-ahead for a paid benchmark (up to $0.30)"
    assert rec["flags"]["escalated"] and rec["reason"] == reason and rec["no_progress"] == 0
    assert rec["sessions"][0]["outcome"] == "waiting_for_owner"
    [event] = log_events(env, "escalation")
    assert event["reason"] == reason
    [blocked] = log_events(env, "blocked_on_owner")
    assert blocked["reason"] == "go-ahead for a paid benchmark (up to $0.30)" and blocked["outcome"] == "finished"
    [call] = new_calls(env)
    assert call["team"] == "backend" and "--to" in call["args"] and "owner" in call["args"]
    assert any("paid benchmark" in a for a in call["args"])
    assert any(f"ESCALATED {P3} (backend): {reason}" in x for x in lines)


def test_blocked_line_after_the_phase_was_completed_is_ignored(env):
    d = blocked_apply(env, events=[(LATER, "backend", "done", "Done.")])
    d.loop(once=True)
    rec = d.state.get(P3)
    assert not rec["flags"]["escalated"] and new_calls(env) == []
    assert log_events(env, "blocked_on_owner") == [] and rec["sessions"][0]["outcome"] == "finished"


def test_no_blocked_line_keeps_the_old_rules(env):
    d = blocked_apply(env, result="Still working on it.")
    d.loop(once=True)
    rec = d.state.get(P3)
    assert not rec["flags"]["escalated"] and rec["no_progress"] == 1 and new_calls(env) == []
    assert log_events(env, "blocked_on_owner") == []


def test_blocked_line_after_an_answer_is_ignored(env):
    """An answered part (`ho respond`) completes the phase too (design N3: done, declined or answered)."""
    d = blocked_apply(env, steps=[{"ho": ["respond", P3, "-m", "Answered."]}])
    d.loop(once=True)
    assert not d.state.get(P3)["flags"]["escalated"] and log_events(env, "blocked_on_owner") == []


# ---- fewer-owner-waits D8: one clear question for a denial

RM = {"tool_name": "PowerShell", "tool_use_id": "t1", "tool_input": {"command": "Remove-Item C:/cache -Recurse"}}
SUGGEST = ("BLOCKED: owner — denied: Remove-Item C:/cache -Recurse; needed for: a clean benchmark; suggestion: "
           "allow it once or run the benchmark without a clean cache")


def test_denial_with_blocked_line_gives_one_clear_question(env):
    d = blocked_apply(env, result=SUGGEST)
    env.set_claude([{"steps": [START], "result": {"result": f"Ran the free checks.\n{SUGGEST}",
                                                  "permission_denials": [RM]}}])
    d.loop(once=True)
    [call] = new_calls(env)
    assert "--tag" in call["args"] and "escalation" in call["args"]
    body = call["stdin"]
    assert "## Denied" in body and "- PowerShell: `Remove-Item C:/cache -Recurse`" in body
    question = SUGGEST.split("— ", 1)[1]
    assert "## Question" in body and f"> {question}" in body
    rec = d.state.get(P3)
    assert "permission denied: PowerShell" in rec["reason"] and rec["escalation"]["question"] == question


def propose_item(env):
    env.set_hub({f"show:{A}": show(A), "inbox:app": {"action_required": [item(A)]}})
    return disp(env)


def test_denial_in_propose_without_blocked_line_composes_the_question(env):
    d = propose_item(env)
    curl = {"tool_name": "Bash", "tool_input": {"command": "curl https://example.com/spec.json"}}
    env.set_claude([{"steps": [START], "result": {"result": "Could not fetch the spec.", "permission_denials": [curl]}}])
    d.loop(once=True)
    [call] = new_calls(env)
    body = call["stdin"]
    assert "- Bash: `curl https://example.com/spec.json`" in body
    assert ("The permission mode denied Bash `curl https://example.com/spec.json` and the session ended without "
            "completing the propose phase. How should the team go on?") in body
    assert d.state.blocked(A) and "permission denied: Bash" in d.state.get(A)["reason"]


def test_several_denials_make_one_escalation_listing_all(env):
    denials = [{"tool_name": "Bash", "tool_input": {"command": f"step {n}"}} for n in (1, 2, 3)]
    d = blocked_apply(env)
    env.set_claude([{"steps": [START], "result": {"result": "Stuck.", "permission_denials": denials}}])
    d.loop(once=True)
    [call] = new_calls(env)
    for n in (1, 2, 3):
        assert f"- Bash: `step {n}`" in call["stdin"]
    assert len(log_events(env, "escalation")) == 1


# ---- fewer-owner-waits D10: the team-decision notice

NOTE = {"verdict": "product", "answer": "use the recommended cache option", "reason": "it is what app recommended",
        "note_for_owner": "Product picked the recommended cache option for app."}


def triage_with(env, verdict, fail_new=False):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A, [(LATER, "app", "ack", "")]),
                 **({"new": {"exit": 1, "error": {"code": "io", "message": "hub unwritable"}}} if fail_new else {})})
    env.set_claude([{"steps": [START, ASK_STEP, stop_step("Waiting for the answer.")], "result": {"result": "Referred."}},
                    {"steps": [START], "result": {"result": "", "structured_output": verdict}},
                    {"steps": [START], "result": {"result": "Continued."}}])
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.loop(once=True)
    return d, lines


def test_note_for_owner_sends_one_team_decision_notice(env):
    d, lines = triage_with(env, NOTE)
    calls = env.claude_calls()
    assert len(calls) == 3 and "--resume" in calls[2]["argv"]  # the asking session is resumed
    assert "use the recommended cache option" in calls[2]["argv"][1]
    [call] = new_calls(env)
    args = call["args"]
    assert call["team"] == "product" and args[args.index("--to") + 1] == "owner"
    assert args[args.index("--expects") + 1] == "ack" and "--auto-close" in args and "--ref" not in args
    assert args[args.index("--tag") + 1] == "team-decision"
    assert args[args.index("--title") + 1] == f"product: decided for app on {A}"
    body = call["stdin"]
    for text in ("use the recommended cache option", "Product picked the recommended cache option",
                 "Use a Map or a plain object", "it is what app recommended"):
        assert text in body
    assert not d.state.blocked(A)
    [sent] = log_events(env, "team_decision_sent")
    assert sent["team"] == "app" and sent["handover"] == A and sent["notice"].startswith("HO-FAKE-")


@pytest.mark.parametrize("note", [None, "", "   "])
def test_no_note_no_notice(env, note):
    verdict = {"verdict": "technical", "answer": "", "reason": "internal detail"}
    if note is not None:
        verdict["note_for_owner"] = note
    d, lines = triage_with(env, verdict)
    assert new_calls(env) == [] and len(env.claude_calls()) == 3 and log_events(env, "team_decision_sent") == []


def test_failed_notice_is_logged_and_the_session_still_resumed(env):
    d, lines = triage_with(env, NOTE, fail_new=True)
    assert len(env.claude_calls()) == 3 and "--resume" in env.claude_calls()[2]["argv"]
    [failed] = log_events(env, "team_decision_send_failed")
    assert failed["handover"] == A and "hub unwritable" in failed["error"]
    assert any("! could not send the team-decision handover" in x for x in lines)
    assert not d.state.blocked(A)
