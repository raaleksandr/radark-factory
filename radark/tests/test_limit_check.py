"""Limit check at the maximum duration with fake `ho` and `claude` (check-session-at-time-limit, tasks 3.2, 3.3)."""
import json
import threading

import pytest

from radark.__main__ import CONSULT_TOOLS, Dispatcher, sym
from radark import prompts
from radark.state import GoalRun
from radark.tests.conftest import START, write_config
from radark.tests.test_progress import A, apply_item, committed, git_init, log_events

FAST = 0.02  # 1.2 s maximum duration


def limits(env, maximum=FAST, extension=1, checks=3, wrap=0):
    """`wrap`: the wrap-up grace period; 0 (off) by default, as these tests are about the cut (wrap-up task 5.6)."""
    text = env.config_path.read_text()
    env.config_path.write_text(text.replace("[loop]", f"[loop]\nsession_max_minutes = {maximum}\n"
                                                      f"limit_check_minutes = {extension}\nlimit_checks = {checks}\n"
                                                      f"wrap_up_minutes = {wrap}"))


def verdict(v, reason="It runs its final e2e suite with steady output."):
    return {"steps": [START], "result": {"structured_output": {"verdict": v, "reason": reason}}}


ACTIVE = {"steps": [START, {"active": 30, "every": 0.2}], "result": {}}
FINISHES = {"steps": [START, {"active": 4, "every": 0.2}], "result": {"result": "Done."}}


def dispatcher(env, lines, tasks=None):
    d = apply_item(env, tasks)
    d._print = lines.append
    return d


def run_item(d):
    (cand,) = d.plan()
    return d.run_candidate(cand)


def test_progressing_session_is_extended_and_finishes(env):
    limits(env)
    lines = []
    d = dispatcher(env, lines)
    goal = env.root / "goal.md"
    goal.write_text("Ship the export.", encoding="utf-8")
    d.goal = GoalRun(goal, "Ship the export.", 40, 12)
    env.set_claude([FINISHES, verdict("progressing")])
    r = run_item(d)
    assert r.outcome == "finished" and r.timeout_reason is None and r.duration_s >= 4
    assert d.goal.sessions == 2  # the check counts in a goal run
    work, check = env.claude_calls()
    argv = check["argv"]
    assert check["cwd"].endswith("product") and check["env"]["HARNESS_TEAM"] == "product"
    assert argv[argv.index("--tools") + 1] == ",".join(CONSULT_TOOLS)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == prompts.LIMIT_SCHEMA
    prompt = argv[1]
    assert "Consultation, not a work session." in prompt and f"handover {A}, phase apply" in prompt
    assert "Ship the export." in prompt and r.stream_path in prompt
    # read-only: no hub write command, nothing written in the product repository
    assert not [c for c in env.ho_calls() if c["args"][0] not in ("inbox", "show", "list", "teams", "sync")]
    assert not [p for p in (env.root / "repos" / "product").rglob("*") if p.is_file()]
    (start,) = log_events(env, "limit_check_start")
    assert (start["team"], start["check_team"], start["handover"], start["checks_used"]) == (
        "app", "product", A, 0)
    assert start["session"] == r.session_id and start["elapsed_s"] >= 1
    (event,) = log_events(env, "limit_check")
    assert (event["outcome"], event["verdict"], event["extension_min"], event["ignored"]) == (
        "finished", "progressing", 1, False)
    assert event["reason"].startswith("It runs its final") and event["session"] == r.session_id
    assert event["check_session"] and event["duration_s"] is not None
    assert log_events(env, "session_end")[0]["outcome"] == "finished"
    text = "\n".join(lines)
    assert f"! app {A}: time limit after 1 s, asking product whether it is hung" in text
    assert f"product {sym('·')} limit check {sym('·')} {A}" in text
    assert f"product {sym('·')} limit check {sym('→')} progressing, +1 min (" in text
    assert "    It runs its final e2e suite with steady output." in text
    assert f"app {sym('·')} apply {sym('→')} finished (" in text


def test_extensions_used_up_end_the_session_without_a_check(env):
    limits(env, extension=FAST)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, verdict("progressing")])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and r.outcome == "error"
    assert [e["checks_used"] for e in log_events(env, "limit_check_start")] == [0, 1, 2]
    assert [e["verdict"] for e in log_events(env, "limit_check")] == ["progressing"] * 3
    assert len(env.claude_calls()) == 4 and r.duration_s < 30


def test_hung_session_is_cut_and_resumed_with_the_reason(env):
    git_init(env)
    limits(env)
    lines = []
    d = dispatcher(env, lines)
    reason = "It reruns the same failing lint command without changing anything."
    env.set_claude([{"steps": [START, *committed(("src/a.py", "one"), msg="part one"), {"active": 30, "every": 0.2}],
                     "result": {}},
                    verdict("hung", reason), {"steps": [START], "result": {"result": "Finished."}}])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and r.limit_reason == reason and r.duration_s < 20
    rec = d.state.get(A)
    assert rec["resume_after_timeout"]["limit_reason"] == reason
    (event,) = log_events(env, "limit_check")
    assert (event["verdict"], event["reason"], event["extension_min"]) == ("hung", reason, None)
    assert f"product {sym('·')} limit check {sym('→')} hung (" in "\n".join(lines)
    d = Dispatcher(env.cfg(), out=lines.append)
    run_item(d)
    resume = env.claude_calls()[2]["argv"]
    assert resume[resume.index("--resume") + 1] == r.session_id
    assert f"The product team judged the session hung: {reason}" in resume[1] and "`max_time`" in resume[1]


@pytest.mark.parametrize("check", [
    {"steps": [START], "result": {"structured_output": {"verdict": "maybe", "reason": "x"}}},
    {"steps": [START], "result": None, "exit": 1},
])
def test_malformed_verdict_or_failed_check_cuts(env, check):
    limits(env)
    lines = []
    d = dispatcher(env, lines)
    env.set_claude([ACTIVE, check])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and r.limit_reason is None and r.duration_s < 20
    (event,) = log_events(env, "limit_check")
    assert event["verdict"] is None and event["extension_min"] is None
    assert any(f"! app {A}: the limit check gave no valid verdict (" in x for x in lines)


@pytest.mark.parametrize("phase,handover", [("consult", A), ("goal", None), ("idle", None)])
def test_consultations_goal_checks_and_idle_asks_are_not_checked(env, phase, handover):
    limits(env)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, verdict("progressing")])
    r = d.session("product", "question", phase, handover)
    assert r.timeout_reason == "max_time" and r.duration_s < 20
    assert not log_events(env, "limit_check_start") and len(env.claude_calls()) == 1


def test_checks_turned_off(env):
    limits(env, checks=0)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, verdict("progressing")])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and r.duration_s < 20
    assert not log_events(env, "limit_check_start") and len(env.claude_calls()) == 1


def test_no_product_team_no_check(env):
    env.config_path = write_config(env.root, triage=False, teams=[("app", "technical"), ("backend", "technical")])
    limits(env)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, verdict("progressing")])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and len(env.claude_calls()) == 1


def test_session_ending_during_the_check_ignores_it(env):
    limits(env)
    lines = []
    d = dispatcher(env, lines)
    env.set_claude([{"steps": [START, {"active": 2.5, "every": 0.2}], "result": {"result": "Done."}},
                    {"steps": [START, {"sleep": 30}], "result": {}}])
    r = run_item(d)
    assert r.outcome == "finished" and r.timeout_reason is None and r.duration_s < 20
    (event,) = log_events(env, "limit_check")
    assert event["ignored"] and event["verdict"] is None
    assert any("limit check" in x and "ignored, the session ended first" in x for x in lines)


def test_second_ctrl_c_during_a_check_ends_both(env):
    limits(env)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, {"steps": [START, {"sleep": 30}], "result": {}}])

    def press_twice():
        d._on_interrupt(None, None)
        d._on_interrupt(None, None)
    timer = threading.Timer(3.5, press_twice)
    timer.start()
    try:
        r = run_item(d)
    finally:
        timer.cancel()
    assert r.outcome == "interrupted" and r.interrupt_cause == "owner" and r.duration_s < 20
    (event,) = log_events(env, "limit_check")
    assert event["outcome"] == "interrupted" and event["verdict"] is None and event["duration_s"] < 20
    assert d.check_runner.proc is None
