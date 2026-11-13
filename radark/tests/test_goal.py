"""Goal run: start, goal check, owner guidance, end of run and wait for a key (change goal-run)."""
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

import radark.__main__ as hm
from radark import prompts
from radark.__main__ import Dispatcher, main
from radark.state import GoalRun
from radark.tests.conftest import START, goal_verdict, hand_over, item, show

A = "HO-20261016-aaaa"
ROOT = Path(__file__).resolve().parents[2]
GOAL = "Finish backlog items B-1 and B-2.\nDo not change the pricing page."


def log_events(env, kind=None):
    path = env.root / "run" / "runs.jsonl"
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [e for e in events if kind is None or e["event"] == kind]


def goal_file(env, text=GOAL) -> Path:
    path = env.root / "goal.md"
    path.write_text(text, encoding="utf-8")
    return path


def goal_disp(env, lines=None, max_sessions=40, max_hours=12, text=GOAL):
    d = Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))
    path = goal_file(env, text)
    d.start_goal(GoalRun(path, path.read_text(encoding="utf-8"), max_sessions, max_hours))
    return d


def prompt_of(call) -> str:
    return call["argv"][call["argv"].index("-p") + 1] if "-p" in call["argv"] else call["argv"][1]


def reports(env):
    return sorted((env.root / "run").glob("goal-report-*.md"))


# ---- start (design G1)

@pytest.mark.parametrize("content", [None, "  \n\t\n"])
def test_empty_goal_refused(env, capsys, content):
    path = env.root / "goal.md"
    if content is not None:
        path.write_text(content)
    assert main(["--config", str(env.config_path), "run", "--goal", str(path), "--no-wait"]) == 2
    assert "goal.md" in capsys.readouterr().err
    assert env.claude_calls() == [] and not (env.root / "run" / "goal.json").exists()


def test_goal_with_once_refused(env, capsys):
    assert main(["--config", str(env.config_path), "run", "--goal", str(goal_file(env)), "--once"]) == 2
    assert "--once" in capsys.readouterr().err and env.claude_calls() == []


def test_start_logs_goal_and_limits(env):
    goal_disp(env, max_sessions=7, max_hours=2)
    start = log_events(env, "goal_start")[0]
    assert start["goal"] == GOAL and (start["max_sessions"], start["max_hours"]) == (7, 2)
    mirror = json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))
    assert mirror["status"] == "running" and mirror["path"].endswith("goal.md")


def test_normal_run_unchanged(env):
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    assert d.loop(once=True) == 0
    assert env.claude_calls() == [] and log_events(env, "goal_check") == []


# ---- goal check (design G3, G4)

def test_next_piece_handed_over(env):
    env.set_claude([{"steps": [START, hand_over(title="B-1")], "result": goal_verdict("continue", "handed over B-1")},
                    {"steps": [START, {"ho": ["close", "HO-FAKE-0001"]}], "result": {"result": "CHANGE: b-1"}},
                    {"steps": [START], "result": goal_verdict("complete", "both done", done=["HO-FAKE-0001 closed"])}])
    d = goal_disp(env)
    assert d.loop() == 0
    calls = env.claude_calls()
    assert [c["cwd"].split("\\")[-1].split("/")[-1] for c in calls] == ["product", "app",
                                                                        "product"]
    assert "Goal check" in prompt_of(calls[0]) and "--json-schema" in calls[0]["argv"]
    assert "HO-FAKE-0001" in prompt_of(calls[1])
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "complete" and result["sessions"] == 3 and result["done"] == ["HO-FAKE-0001 closed"]
    assert [h["id"] for h in result["handovers"]] == ["HO-FAKE-0001"]


def test_goal_met_writes_report(env):
    lines = []
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "all closed", done=["HO-1 closed"])}])
    d = goal_disp(env, lines)
    assert d.loop() == 0
    [report] = reports(env)
    text = report.read_text(encoding="utf-8")
    assert "# Goal run: complete" in text and "- HO-1 closed" in text and "all closed" in text
    assert any("# Goal run: complete" in x for x in lines)
    assert json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))["status"] == "complete"


def test_only_owner_dependent_work_left(env):
    env.set_claude([{"steps": [START], "result": goal_verdict("blocked", "pricing needs the owner",
                                                               left=["B-2: the price must be decided"])}])
    d = goal_disp(env)
    d.state.escalate(A, "app", "asked: push?")
    d.state.get(A)["sessions"].append({"id": "sess-esc", "team": "app", "phase": "apply"})
    assert d.loop() == 4
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "blocked" and result["left"] == ["B-2: the price must be decided"]
    assert result["escalated"][0]["handover"] == A and result["escalated"][0]["session"] == "sess-esc"
    assert "claude --resume sess-esc" in reports(env)[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("first", [goal_verdict("continue", "in progress"), {"result": "not json"},
                                   {"structured_output": {"status": "maybe", "reason": "r", "done": [], "left": []}}])
def test_continue_without_new_work(env, first):
    env.set_claude([{"steps": [START], "result": first},
                    {"steps": [START], "result": goal_verdict("continue", "still in progress")}])
    d = goal_disp(env)
    assert d.loop() == 5
    assert len(env.claude_calls()) == 2
    assert log_events(env, "goal_result")[0]["status"] == "stalled"


def test_malformed_verdict_with_hub_activity_still_counts(env):
    """An invalid verdict is `continue` without new work, even if the session touched the hub."""
    env.set_claude([{"steps": [START, hand_over()], "result": {"result": "oops"}},
                    {"steps": [START], "result": goal_verdict("continue")}])
    d = goal_disp(env)
    d.plan = lambda held=None: []  # keep the new handover out of selection
    assert d.loop() == 5 and len(env.claude_calls()) == 2


def test_parse_goal_verdict():
    r = hm.SessionResult(run_id="r", session_id="s", team="t", handover=None, phase="goal", started="")
    r.structured = {"status": "complete", "reason": "ok", "done": ["a"], "left": []}
    assert hm.parse_goal_verdict(r) == {"status": "complete", "reason": "ok", "done": ["a"], "left": []}
    r.structured = {"status": "complete", "reason": "ok", "done": [1], "left": []}
    assert hm.parse_goal_verdict(r) is None
    r.structured, r.result_text = None, json.dumps({"status": "blocked", "reason": "x"})
    assert hm.parse_goal_verdict(r) == {"status": "blocked", "reason": "x", "done": [], "left": []}


# ---- owner guidance (design G5, G6)

def test_guidelines_reach_the_product_team(env):
    env.set_hub({"inbox:product": {"to_review": [item(A, sender="product")]},
                 f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Reviewed."}}])
    d = goal_disp(env, max_sessions=1)
    assert d.loop() == 6
    review = prompt_of(env.claude_calls()[0])
    assert "Phase: review" in review and "Do not change the pricing page." in review
    assert "Owner's goal and guidelines for this run" in review
    assert review.index("Owner's goal") < review.index(prompts.STANDING_RULE)
    consult = prompts.consult_prompt({"question": "?"}, "app", A, None, GOAL)
    assert "Do not change the pricing page." in consult


def test_technical_prompts_untouched(env):
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Working."}}])
    d = goal_disp(env, max_sessions=1)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    assert d.loop() == 6
    apply = prompt_of(env.claude_calls()[0])
    assert "Phase: apply" in apply and "pricing page" not in apply and "Owner's goal" not in apply


def test_guidance_changed_mid_run(env):
    """`note` from a second process while a technical session runs; the next session is a goal check."""
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    note = [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); from radark.__main__ import main; "
            f"sys.exit(main(['--config', {str(env.config_path)!r}, 'note', 'Skip B-2 for now.']))"]
    env.set_claude([{"steps": [START, {"cmd": note}], "result": {"result": "Working."}},
                    {"steps": [START], "result": goal_verdict("complete", "B-1 done, B-2 dropped by the owner")}])
    d = goal_disp(env)
    assert d.loop() == 0
    calls = env.claude_calls()
    assert len(calls) == 2 and calls[1]["cwd"].endswith("product")
    check = prompt_of(calls[1])
    assert "guidance changed" in check and "Skip B-2 for now." in check and "## Note" in check
    assert "Goal check" in check
    assert "Skip B-2 for now." in (env.root / "goal.md").read_text(encoding="utf-8")
    assert log_events(env, "goal_updated")[0]["diff_chars"] > 0
    assert log_events(env, "goal_check")[0]["guidance_changed"] is True


def test_guidance_notice_appended_or_edited():
    assert "> extra" in prompts.guidance_notice("goal", "goal\n\nextra")
    assert "edited the goal text" in prompts.guidance_notice("goal A", "goal B")
    assert "edited the goal text" in prompts.guidance_notice("", "goal")  # the seen text is unknown


def test_unreadable_goal_keeps_last_text(env):
    lines = []
    d = goal_disp(env, lines)
    (env.root / "goal.md").write_text("   ")
    d.goal_refresh()
    d.goal_refresh()
    assert d.goal.text == GOAL and not d.goal.pending
    assert len(log_events(env, "goal_unreadable")) == 1 and sum("! the goal file" in x for x in lines) == 1


def test_note_without_goal_run(env, capsys):
    assert main(["--config", str(env.config_path), "note", "hello"]) == 1
    assert "No goal run" in capsys.readouterr().err
    (env.root / "run").mkdir(exist_ok=True)
    (env.root / "run" / "goal.json").write_text(json.dumps({"path": str(goal_file(env)), "status": "limit"}))
    assert main(["--config", str(env.config_path), "note", "hello"]) == 0
    assert "the next run on this file starts with a goal check" in capsys.readouterr().out


# ---- guidance carried to the next run (carry-goal-guidance)

NOTE = "\n\n## Note 2026-10-26 14:23\nThe backend team may deploy production.\n"


def tech_waiting(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


def limit_run(env):
    """A first run on goal.md that ends at its session limit with one technical session."""
    tech_waiting(env)
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    assert goal_disp(env, max_sessions=1).loop() == 6


def next_run(env, lines=None, max_sessions=2):
    d = Dispatcher(env.cfg(), out=(lines.append if lines is not None else (lambda *a: None)))
    path = env.root / "goal.md"
    d.start_goal(GoalRun(path, path.read_text(encoding="utf-8"), max_sessions, 12))
    return d


def append_note(env):
    assert main(["--config", str(env.config_path), "note", "The backend team may deploy production."]) == 0


def cwd_team(call) -> str:
    return call["cwd"].replace("\\", "/").split("/")[-1]


def test_note_between_runs_starts_the_next_run_with_a_goal_check(env):
    limit_run(env)
    append_note(env)
    copy = env.root / "goal-during-check.json"
    snap = [sys.executable, "-c", f"import shutil; shutil.copy({str(env.root / 'run' / 'goal.json')!r}, {str(copy)!r})"]
    env.set_claude([{"steps": [START, {"cmd": snap}], "result": goal_verdict("continue", "deploy allowed")},
                    {"steps": [START], "result": {"result": "Working."}}])
    lines = []
    d = next_run(env, lines)
    assert any("the first session is a goal check" in x for x in lines)
    assert d.loop() == 6
    calls = env.claude_calls()[1:]
    assert [cwd_team(c) for c in calls] == ["product", "app"]
    check = prompt_of(calls[0])
    assert "The owner added this to the goal" in check and "The backend team may deploy production." in check
    carried = log_events(env, "goal_guidance_carried")[0]
    assert carried["recovered"] == "stored" and carried["added_chars"] > 0
    during = json.loads(copy.read_text(encoding="utf-8"))  # saved when the session got the text (design C2)
    assert during["given_text"] == (env.root / "goal.md").read_text(encoding="utf-8")


def test_note_late_in_a_run_carries_to_the_next_run(env):
    tech_waiting(env)
    note = [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); from radark.__main__ import main; "
            f"sys.exit(main(['--config', {str(env.config_path)!r}, 'note', 'Skip B-2 for now.']))"]
    env.set_claude([{"steps": [START, {"cmd": note}], "result": {"result": "Working."}}])
    assert goal_disp(env, max_sessions=1).loop() == 6
    info = json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))
    assert info["given_text"] == GOAL  # the limit ends the run before the change is even read
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    assert next_run(env).loop() == 0
    check = prompt_of(env.claude_calls()[1])
    assert "Goal check" in check and "> Skip B-2 for now." in check


def test_unchanged_goal_file_keeps_the_normal_selection(env):
    limit_run(env)
    env.set_claude([{"steps": [START], "result": {"result": "Working."}}])
    d = next_run(env, max_sessions=1)
    assert not d.goal.pending and d.loop() == 6
    assert cwd_team(env.claude_calls()[1]) == "app"
    assert log_events(env, "goal_guidance_carried") == []


def test_other_goal_file_keeps_the_normal_selection(env):
    limit_run(env)
    append_note(env)
    other = env.root / "other.md"
    other.write_text("Another goal.", encoding="utf-8")
    env.set_claude([{"steps": [START], "result": {"result": "Working."}}])
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.start_goal(GoalRun(other, "Another goal.", 1, 12))
    assert not d.goal.pending and d.loop() == 6
    assert cwd_team(env.claude_calls()[1]) == "app"


def old_goal_json(env, text, pending):
    """goal.json as written before carry-goal-guidance: a hash, no given_text."""
    (env.root / "run").mkdir(exist_ok=True)
    (env.root / "run" / "goal.json").write_text(json.dumps({
        "path": str(env.root / "goal.md"), "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "status": "limit", "guidance_pending": pending, "last_verdict": None}))


def test_older_goal_json_recovers_the_seen_text_through_the_hash(env):
    goal_file(env, GOAL + NOTE)
    old_goal_json(env, GOAL, pending=False)
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    d = next_run(env)
    assert d.goal.given_text == GOAL and d.goal.pending
    assert d.loop() == 0
    check = prompt_of(env.claude_calls()[0])
    assert "The owner added this to the goal" in check and "> The backend team may deploy production." in check
    assert log_events(env, "goal_guidance_carried")[0]["recovered"] == "hash"
    assert json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))["given_text"] == GOAL + NOTE


def test_older_goal_json_with_pending_guidance_gives_the_generic_notice(env):
    goal_file(env, GOAL + NOTE)
    old_goal_json(env, GOAL + NOTE, pending=True)  # goal_refresh saved the unseen text's hash
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    d = next_run(env)
    assert d.goal.given_text == "" and d.goal.pending
    assert d.loop() == 0
    check = prompt_of(env.claude_calls()[0])
    assert "edited the goal text" in check and "The owner added" not in check
    assert log_events(env, "goal_guidance_carried")[0]["recovered"] == "unknown"


def test_unseen_guidance_leaves_the_goal_run_unchanged(env):
    limit_run(env)
    append_note(env)
    path = env.root / "goal.md"
    goal = GoalRun(path, path.read_text(encoding="utf-8"), 2, 12)
    before = dict(vars(goal))
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    assert Dispatcher.unseen_guidance(goal, d.previous_goal(goal)) == (GOAL, "stored")
    assert vars(goal) == before and not goal.pending
    assert Dispatcher.unseen_guidance(goal, None) is None


def test_older_goal_json_unchanged_file(env):
    goal_file(env, GOAL + NOTE)
    old_goal_json(env, GOAL + NOTE, pending=False)
    assert not next_run(env).goal.pending


# ---- end of run (design G7, G8)

def test_session_limit(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    d = goal_disp(env, max_sessions=1)
    assert d.loop() == 6
    assert len(env.claude_calls()) == 1
    result = log_events(env, "goal_result")[0]
    assert result["status"] == "limit" and "1 sessions" in result["reason"]


def test_short_run_reports_its_sessions_and_the_earlier_verdict(env):
    env.set_claude([{"steps": [START], "result": goal_verdict("blocked", "waiting", done=["B-0 closed"],
                                                               left=["B-1 in progress"])}])
    assert goal_disp(env).loop() == 4
    env.set_hub({"inbox:app": {"action_required": [item(A, title="B-1")]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    d = goal_disp(env, max_sessions=1)
    assert d.loop() == 6
    result = log_events(env, "goal_result")[-1]
    assert result["done"] == ["B-0 closed"] and result["left"] == ["B-1 in progress"]
    text = max(reports(env)).read_text(encoding="utf-8")
    assert "## Sessions in this run" in text and f"app {hm.sym('·')} propose {hm.sym('·')} {A} {hm.sym('→')} " in text
    assert "No goal check in this run; Done and Left are from the last goal check of " in text
    info = json.loads((env.root / "run" / "goal.json").read_text(encoding="utf-8"))
    assert info["last_verdict"]["done"] == ["B-0 closed"] and info["last_verdict_at"]


def test_other_goal_file_does_not_carry_the_verdict(env):
    env.set_claude([{"steps": [START], "result": goal_verdict("blocked", "waiting", done=["B-0 closed"])}])
    assert goal_disp(env).loop() == 4
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    other = env.root / "other.md"
    other.write_text("Another goal.", encoding="utf-8")
    d.start_goal(GoalRun(other, "Another goal.", 1, 12))
    assert d.goal.last_verdict is None and not d.goal.verdict_carried


def test_duration_limit_and_stop(env):
    d = goal_disp(env)
    d.goal.started -= 13 * 3600
    assert d.loop() == 6 and "12 h" in log_events(env, "goal_result")[0]["reason"]
    d = goal_disp(env)
    (env.root / "run" / "STOP").write_text("")
    assert d.loop() == 0 and log_events(env, "goal_result")[-1]["status"] == "stopped"


def test_dry_run_prints_goal_check(env, capsys):
    assert main(["--config", str(env.config_path), "run", "--dry-run", "--goal", str(goal_file(env))]) == 0
    out = capsys.readouterr().out
    assert "would run a goal check in product" in out and "Do not change the pricing page." in out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []


class Console:
    def isatty(self):
        return True


def complete_run(env, monkeypatch, *args):
    env.set_claude([{"steps": [START], "result": goal_verdict("complete", "done")}])
    keys = []
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getch=lambda: keys.append(1)))
    code = main(["--config", str(env.config_path), "run", "--goal", str(goal_file(env)), *args])
    return code, keys


def test_complete_run_waits_for_key_in_a_console(env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", Console())
    code, keys = complete_run(env, monkeypatch)
    out = capsys.readouterr().out
    assert code == 0 and keys == [1]
    assert "# Goal run: complete" in out and out.rstrip().endswith("Press any key to exit")
    assert log_events(env, "goal_result")[0]["status"] == "complete" and len(reports(env)) == 1


def test_not_interactive(env, monkeypatch, capsys):
    code, keys = complete_run(env, monkeypatch)  # pytest's stdin is not a console
    assert code == 0 and keys == [] and "Press any key" not in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", Console())
    code, keys = complete_run(env, monkeypatch, "--no-wait")
    assert code == 0 and keys == [] and "Press any key" not in capsys.readouterr().out


def test_console_is_copied_to_console_log(env, monkeypatch, capsys):
    code, _ = complete_run(env, monkeypatch, "--no-wait")
    out = capsys.readouterr().out
    log = (env.root / "run" / "console.log").read_text(encoding="utf-8")
    assert code == 0 and "# Goal run: complete" in out
    assert log.startswith("\n==== ") and "--no-wait" in log.splitlines()[1]
    assert out in log  # everything the window showed, in order
