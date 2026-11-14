"""A goal binds only its run; the idle ask is the full choice of next work (change goal-ends-with-run)."""
import datetime as dt
import json
import types

import pytest

from radark import prompts
from radark.__main__ import Dispatcher, iso_ts, main, parse_idle_verdict
from radark.state import GoalRun
from radark.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
NOTICE = prompts.NO_GOAL_NOTICE
CLEANUP = "remove that order now"


class Clock:
    """A sleep watch whose awake clock moves only when the test moves it (a sleep: it stands still)."""

    def __init__(self):
        self.t = 1000.0

    def clock(self):
        return self.t

    def check(self):
        return None


def disp(env, lines=None, watch=None):
    return Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)), watch=watch or Clock())


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def prompt_of(call) -> str:
    return call["argv"][call["argv"].index("-p") + 1] if "-p" in call["argv"] else call["argv"][1]


def new_calls(env):
    return [c for c in env.ho_calls() if c["args"][0] == "new"]


def verdict(kind="none", reason="backlog empty", waiting=()):
    return {"verdict": kind, "reason": reason, "waiting_for_owner": [{"item": i, "why": "owner decides"} for i in waiting]}


def idle_setup(env, verdicts, extra=""):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\nidle_ask = true" + extra))
    env.set_hub({"list:product": {"items": [{"id": A, "last_activity": "2026-10-16T10:00:00.000Z"}]}})
    env.set_claude([{"steps": [START], "result": {"structured_output": v}} for v in verdicts])


def goal_json(env, **fields):
    info = {"path": str(env.root / "goal-release.md"), "hash": "h1", "started": "2026-11-13T08:00:00.000Z",
            "status": "limit", "ended": "2026-11-13T17:00", **fields}
    (env.root / "run").mkdir(exist_ok=True)
    (env.root / "run" / "goal.json").write_text(json.dumps({k: v for k, v in info.items() if v is not None}))


# ---- prompts (tasks 2.1–2.7)

def test_idle_prompt_is_the_whole_choice():
    text = prompts.idle_prompt()
    for part in ("usual task-choice rule", "your backlog, your technical debt and your team's own regular tasks",
                 "the schedule your team's instructions name", "overdue or due within a day goes first",
                 "do it yourself in this session", "`did_regular`", "exactly one backlog item per handover",
                 "waiting_for_owner", prompts.STANDING_RULE):
        assert part in text
    assert "escalated to the owner or stalled" not in text and NOTICE not in text
    assert prompts.IDLE_SCHEMA["properties"]["verdict"]["enum"] == ["handed_over", "did_regular", "none"]


def test_idle_prompt_names_blocked_items_and_carries_the_notice():
    text = prompts.idle_prompt([{"handover": "HO-1", "team": "app", "kind": "escalated", "reason": "needs a key"},
                                {"handover": "HO-2", "team": "backend", "kind": "stalled", "reason": None}], NOTICE)
    assert "- HO-1 (team `app`, escalated): needs a key" in text
    assert "- HO-2 (team `backend`, stalled): no reason recorded" in text
    assert "A blocked item is no reason to leave other ready work waiting" in text
    assert "Answer `none` only when every ready item waits for the owner or depends on a blocked item." in text
    assert NOTICE in text and text.index(NOTICE) < text.index(prompts.STANDING_RULE)


def test_notices():
    assert "No owner goal is active in this run" in NOTICE and "usual task-choice rule" in NOTICE
    text = prompts.ended_goal_notice("goal-release.md", "limit", "2026-11-13T17:00")
    assert text.startswith("The goal run on `goal-release.md` ended (`limit`, 17:00, 2026-11-13).")
    assert CLEANUP in text and "keep its unfinished parts as ordinary backlog items" in text
    leftover = prompts.ended_goal_notice("goal-release.md", "running", None)
    assert "ended without a report" in leftover and "17:00" not in leftover and CLEANUP in leftover


def test_goal_check_says_only_this_run_counts():
    assert ("Only this run's goal sets the order of work; goals of earlier runs have ended."
            in prompts.goal_check_prompt("Finish B-1."))


def test_no_goal_block_in_phase_and_consult_prompts():
    from radark.select import Candidate
    c = Candidate(kind="review", team="product", handover=A, title="T", phase="review", recency="", team_index=0)
    assert NOTICE in prompts.phase_prompt(c, no_goal=NOTICE)
    assert NOTICE not in prompts.phase_prompt(c, "Goal text", no_goal=NOTICE)  # a goal wins
    assert prompts.consult_prompt({"question": "?"}, "app", A, None, no_goal=NOTICE).endswith(NOTICE)


def test_parse_idle_verdict_accepts_did_regular():
    r = types.SimpleNamespace(structured=verdict("did_regular", "weekly report written"), result_text="")
    assert parse_idle_verdict(r)["verdict"] == "did_regular"


# ---- did_regular (task 4.1)

def test_did_regular_asks_again_at_once_and_stops_after_three(env):
    idle_setup(env, [verdict("did_regular", "weekly report written")] * 4)
    lines = []
    d = disp(env, lines)
    for _ in range(5):
        d.loop(once=True)
    assert len(env.claude_calls()) == 3
    assert [e["cause"] for e in log_events(env, "idle_ask")] == ["hub", "regular", "regular"]
    assert [e["streak"] for e in log_events(env, "idle_regular_limit")] == [3]
    assert any("idle: did_regular - weekly report written; next ask now" in x for x in lines)
    assert any("3 regular tasks in a row; next ask on hub activity or ~" in x for x in lines)


def test_work_session_resets_the_regular_streak(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Created.\nCHANGE: add-x"}}])
    d = disp(env)
    d.state.meta["idle_regular_streak"] = 2
    d.loop(once=True)
    assert "idle_regular_streak" not in d.state.meta


# ---- re-ask by awake time (task 4.3)

def test_reask_after_a_quiet_awake_hour_and_sleep_not_counted(env):
    idle_setup(env, [verdict()] * 3)
    lines, c = [], Clock()
    d = disp(env, lines, c)
    d.loop(once=True)
    assert len(env.claude_calls()) == 1
    assert any("idle: none - backlog empty; next ask on hub activity or ~" in x for x in lines)
    assert d.state.meta.get("idle_reask_at")
    c.t += 14 * 60  # awake until the computer sleeps; the sleep does not move the awake clock
    d.loop(once=True)
    c.t += 45 * 60  # 59 awake minutes
    d.loop(once=True)
    assert len(env.claude_calls()) == 1
    c.t += 60
    d.loop(once=True)
    assert len(env.claude_calls()) == 2 and log_events(env, "idle_ask")[1]["cause"] == "time"


def test_reask_by_time_switched_off(env):
    idle_setup(env, [verdict()] * 2, "\nidle_reask_minutes = 0")
    lines, c = [], Clock()
    d = disp(env, lines, c)
    d.loop(once=True)
    c.t += 600 * 60
    d.loop(once=True)
    assert len(env.claude_calls()) == 1
    assert any(x.endswith("next ask on hub activity") for x in lines)


# ---- blocked items and owner escalations (task 4.2)

def test_blocked_item_named_in_the_idle_prompt(env):
    idle_setup(env, [verdict()])
    d = disp(env)
    d.state.escalate("HO-20261016-bbbb", "app", "needs an API key")
    d.state.save()
    d.loop(once=True)
    text = prompt_of(env.claude_calls()[0])
    assert "- HO-20261016-bbbb (team `app`, escalated): needs an API key" in text
    assert "does not depend on these items" in text
    assert log_events(env, "idle_ask")[0]["blocked"] == ["HO-20261016-bbbb"]


def test_same_owner_items_are_not_escalated_again(env):
    two = ("BL-3 Pricing page", "BL-4 Paid ads")
    idle_setup(env, [verdict("none", "needs the owner", two), verdict("none", "needs the owner", two[::-1]),
                     verdict("none", "needs the owner", two + ("BL-5 Terms",))])
    c = Clock()
    d = disp(env, watch=c)
    d.loop(once=True)
    assert len(new_calls(env)) == 1
    c.t += 3600
    d.loop(once=True)
    assert len(env.claude_calls()) == 2 and len(new_calls(env)) == 1
    assert log_events(env, "idle_escalation_skipped")[0]["items"] == sorted(two)
    assert len(log_events(env, "idle_verdict")) == 2
    c.t += 3600
    d.loop(once=True)
    calls = new_calls(env)
    assert len(calls) == 2 and all(i in calls[1]["stdin"] for i in two + ("BL-5 Terms",))


# ---- no-goal notice (task 4.4)

def test_no_goal_notice_in_product_prompts_only(env):
    idle_setup(env, [verdict()])
    d = disp(env)
    d.loop(once=True)
    assert NOTICE in prompt_of(env.claude_calls()[0])
    assert d.no_goal_for("product") == NOTICE and d.no_goal_for("app") is None


def test_review_prompt_carries_the_notice_and_apply_does_not(env):
    env.set_hub({"inbox:product": {"to_review": [item(A, sender="app")]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Closed."}}])
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="done")
    d.state.save()
    d.loop(once=True)
    assert NOTICE in prompt_of(env.claude_calls()[0])
    B = "HO-20261016-bbbb"
    env.set_hub({"inbox:app": {"action_required": [item(B, my_state="acknowledged")]}, f"show:{B}": show(B)})
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    d = disp(env)
    d.state.ensure(B, "app").update(change="add-y", phase="propose")
    d.state.save()
    d.loop(once=True)
    text = prompt_of(env.claude_calls()[-1])
    assert "Phase: apply" in text and NOTICE not in text


def test_goal_run_keeps_its_goal(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    assert d.no_goal_for("product") is None and d.goal_for("product") == "Finish B-1."


# ---- ended-goal notice (task 4.5)

def test_first_prompt_after_a_goal_run_names_it_once(env):
    goal_json(env)
    idle_setup(env, [verdict()])
    d = disp(env)
    d.loop(once=True)
    text = prompt_of(env.claude_calls()[0])
    assert "goal-release.md` ended (`limit`, 17:00, 2026-11-13)" in text and CLEANUP in text
    assert d.state.meta["goal_cleanup_done"].endswith("|2026-11-13T08:00:00.000Z")
    assert log_events(env, "ended_goal_notice")[0]["counted"] is True
    assert d.no_goal_for("product") == NOTICE
    assert disp(env).no_goal_for("product") == NOTICE  # the next run without a goal


def test_note_appended_after_the_goal_run_does_not_repeat_it(env):
    goal_json(env)
    d = disp(env)
    assert CLEANUP in d.no_goal_for("product")
    d.ended_goal_given("product", types.SimpleNamespace(outcome="finished", session_id="s1"))
    goal_json(env, hash="h2")  # `note` changed the goal file's hash, not the goal run
    assert disp(env).no_goal_for("product") == NOTICE


@pytest.mark.parametrize("outcome", ["interrupted", "usage_limit"])
def test_cut_session_does_not_count(env, outcome):
    goal_json(env)
    d = disp(env)
    assert CLEANUP in d.no_goal_for("product")
    d.ended_goal_given("product", types.SimpleNamespace(outcome=outcome, session_id="s1"))
    assert "goal_cleanup_done" not in d.state.meta
    assert CLEANUP in d.no_goal_for("product")


def test_goal_run_ended_without_a_report(env):
    goal_json(env, status="running", ended=None)
    text = disp(env).no_goal_for("product")
    assert "ended without a report" in text and "17:00" not in text and CLEANUP in text


def test_older_goal_json_without_end_time(env):
    goal_json(env, ended=None, result={"status": "limit", "duration_s": 3600, "slept_s": 1800})
    at = dt.datetime.fromtimestamp(iso_ts("2026-11-13T08:00:00.000Z") + 5400)
    assert f"(`limit`, {at:%H:%M, %Y-%m-%d})" in disp(env).no_goal_for("product")


def test_end_goal_writes_the_end_time(env):
    path = env.root / "goal.md"
    path.write_text("Finish B-1.", encoding="utf-8")
    d = disp(env)
    d.start_goal(GoalRun(path, "Finish B-1.", 40, 12))
    d.end_goal("limit", "end time reached")
    info = json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))
    assert info["status"] == "limit" and dt.datetime.fromisoformat(info["ended"]).date() == dt.date.today()


# ---- dry-run (task 3.9)

def test_dry_run_names_the_next_reask_and_the_notice(env, capsys):
    idle_setup(env, [])
    goal_json(env)
    d = disp(env)
    d.state.meta.update(last_idle_ask="2099-01-01T00:00:00.000Z", idle_reask_at="2026-11-14T10:26")
    d.state.save()
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "next idle re-ask ~10:26 if the computer stays awake, or on hub activity" in out
    assert NOTICE in out and CLEANUP in out
    assert env.claude_calls() == []
