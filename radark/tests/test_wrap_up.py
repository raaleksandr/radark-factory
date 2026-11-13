"""Wrap-up at the last time limit with fake `ho` and `claude` (wrap-up-at-time-limit, tasks 5.1-5.5)."""
import pytest

from radark import prompts
from radark import select as sel
from radark.__main__ import Dispatcher, sym
from radark.tests.conftest import START, write_config
from radark.tests.test_limit_check import ACTIVE, FAST, dispatcher, limits, run_item, verdict
from radark.tests.test_progress import A, committed, git_init, log_events

GRACE = 0.03  # 1.8 s wrap-up grace period
WRAPS_UP = {"steps": [START, {"text": "Committed; reporting."}], "result": {"result": "Wrapped up."}}


def resumed(env, index: int) -> list[str]:
    argv = env.claude_calls()[index]["argv"]
    return argv


def review_prompt(d, rec):
    cand = sel.Candidate(kind="review", team="product", handover=A, title="Add x", phase="review", recency="",
                         team_index=0)
    return d.work_prompt(cand, rec, None)


def test_progressing_session_wraps_up_after_its_last_extension(env):
    limits(env, extension=FAST, checks=1, wrap=GRACE)
    lines = []
    d = dispatcher(env, lines)
    env.set_claude([ACTIVE, verdict("progressing"), WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "finished" and r.timeout_reason is None
    work, check, wrap = env.claude_calls()
    argv = wrap["argv"]
    first = log_events(env, "session_start")[0]
    assert argv[argv.index("--resume") + 1] == r.session_id
    assert argv[1].startswith("The dispatcher stopped this session: it reached its time limit after ")
    assert "and 1 limit-check extension, in the apply phase" in argv[1]
    assert f"`ho done {A} -m" in argv[1] and prompts.APPLY_NO_ARCHIVE in argv[1]
    (start,) = log_events(env, "wrap_up_start")
    assert (start["team"], start["handover"], start["phase"], start["extensions_used"], start["grace_min"]) == (
        "app", A, "apply", 1, GRACE)
    assert start["session"] == r.session_id and start["elapsed_s"] >= 1
    (event,) = log_events(env, "wrap_up")
    assert (event["outcome"], event["timeout_reason"], event["extensions_used"], event["grace_min"]) == (
        "finished", None, 1, GRACE)
    assert event["wrap_up_session"] == r.session_id and event["duration_s"] is not None
    ends = [e["outcome"] for e in log_events(env, "session_end")]
    assert ends == ["interrupted", "finished"] and first["phase"] == "apply"
    text = "\n".join(lines)
    assert f"! app {A}: time limit after " in text and "1 extension used; asking the session to wrap up within" in text
    assert f"app {sym('·')} apply {sym('→')} interrupted, asked to wrap up (" in text
    assert f"app {sym('·')} apply {sym('·')} wrap-up {sym('·')} {A}" in text
    assert "session ended with an error" not in text
    rec = d.state.get(A)
    assert [s["outcome"] for s in rec["sessions"]] == ["interrupted", "finished"]
    assert "resume_after_timeout" not in rec
    (entry,) = rec["time_limits"]
    assert (entry["kind"], entry["extensions"], entry["outcome"], entry["reason"]) == ("wrap_up", 1, "finished", None)


def test_wrap_up_that_keeps_running_is_cut_and_resumed(env):
    git_init(env)
    limits(env, checks=0, wrap=GRACE)
    lines = []
    d = dispatcher(env, lines)
    env.set_claude([{"steps": [START, *committed(("src/a.py", "one"), msg="part one"), {"active": 30, "every": 0.2}],
                     "result": {}}, ACTIVE])
    r = run_item(d)
    assert r.outcome == "error" and r.timeout_reason == "max_time" and r.duration_s < 20
    (event,) = log_events(env, "wrap_up")
    assert (event["outcome"], event["timeout_reason"], event["extensions_used"]) == ("error", "max_time", 0)
    rec = d.state.get(A)
    assert rec["resume_after_timeout"]["reason"] == "max_time"
    assert rec["resume_after_timeout"]["session"] == r.session_id and rec.get("no_progress", 0) == 0
    assert [e["kind"] for e in rec["time_limits"]] == ["wrap_up"]  # the cut wrap-up is not counted twice
    assert any("session ended with an error: time limit after" in x for x in lines)


def test_checks_turned_off_wrap_up_at_the_maximum_duration(env):
    limits(env, checks=0, wrap=GRACE)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "finished" and not log_events(env, "limit_check_start")
    assert len(env.claude_calls()) == 2 and "--resume" in resumed(env, 1)
    assert log_events(env, "wrap_up_start")[0]["extensions_used"] == 0


def test_no_product_team_wraps_up(env):
    env.config_path = write_config(env.root, triage=False, teams=[("app", "technical"), ("backend", "technical")])
    limits(env, wrap=GRACE)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "finished" and len(env.claude_calls()) == 2
    assert not log_events(env, "limit_check_start") and log_events(env, "wrap_up")


@pytest.mark.parametrize("check", [
    verdict("hung", "It repeats the same failing command."),
    {"steps": [START], "result": None, "exit": 1},
])
def test_hung_or_failed_check_cuts_without_a_wrap_up(env, check):
    limits(env, wrap=GRACE)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, check, WRAPS_UP])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and r.outcome == "error"
    assert len(env.claude_calls()) == 2 and not log_events(env, "wrap_up_start")
    (entry,) = d.state.get(A)["time_limits"]
    assert (entry["kind"], entry["reason"], entry["extensions"]) == ("cut", "max_time", 0)


@pytest.mark.parametrize("phase,handover", [("consult", A), ("goal", None), ("idle", None)])
def test_non_work_sessions_are_not_wrapped_up(env, phase, handover):
    limits(env, checks=0, wrap=GRACE)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, WRAPS_UP])
    r = d.session("product", "question", phase, handover)
    assert r.timeout_reason == "max_time" and len(env.claude_calls()) == 1


def test_wrap_up_turned_off_cuts_as_before(env):
    limits(env, checks=0, wrap=0)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.timeout_reason == "max_time" and len(env.claude_calls()) == 1
    assert not log_events(env, "wrap_up_start")


def test_review_prompt_names_the_time_limits(env):
    limits(env, checks=0, wrap=GRACE)
    d = dispatcher(env, [])
    rec = d.state.get(A)
    assert "ran into the time limit" not in review_prompt(d, rec)  # no history, no paragraph
    env.set_claude([ACTIVE, WRAPS_UP])
    run_item(d)
    text = review_prompt(d, d.state.get(A))
    assert "The worker's sessions on this handover ran into the time limit: wrapped up after " in text
    assert "with 0 extensions (finished). The task may be too big for one session" in text


def test_review_prompt_counts_repeated_cuts(env):
    limits(env, checks=0, wrap=0)
    d = dispatcher(env, [])
    env.set_claude([ACTIVE])
    run_item(d)
    d = Dispatcher(env.cfg(), out=lambda line: None)
    env.set_claude([ACTIVE])
    d.session("app", "again", "apply", A)
    text = review_prompt(d, d.state.get(A))
    assert text.count("cut by max_time after ") == 2 and "; cut by max_time" in text
