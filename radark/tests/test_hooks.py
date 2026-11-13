"""Feed sample hook inputs to the real hook scripts and check decisions and markers (task 3.3)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
CFG = {"default_answer": "DEFAULT ANSWER", "escalation_keywords": ["push", "deploy", "delete"],
       "triage_teams": ["app", "backend"]}
ASK = {"tool_name": "AskUserQuestion",
       "tool_input": {"questions": [{"question": "Which approach: A or B?", "header": "Approach",
                                     "options": [{"label": "A", "description": "Map"}, {"label": "B", "description": "Object"}],
                                     "multiSelect": False}]}}
RISKY = {"tool_name": "AskUserQuestion",
         "tool_input": {"questions": [{"question": "Should I push to the remote now?", "header": "Push",
                                       "options": [{"label": "Yes"}, {"label": "No"}]}]}}


@pytest.fixture
def run_dir(tmp_path):
    (tmp_path / "hook-config.json").write_text(json.dumps(CFG))
    return tmp_path


def hook(script, payload, run_dir, team="app", run_id="run-1", phase="apply"):
    env = {"SYSTEMROOT": "C:\\Windows", "HARNESS_RUN_DIR": str(run_dir), "HARNESS_RUN_ID": run_id,
           "HARNESS_SESSION": "sess-1", "HARNESS_TEAM": team, "HARNESS_HANDOVER": "HO-20261016-ab12",
           "HARNESS_PHASE": phase}
    p = subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload).encode(),
                       capture_output=True, env=env)
    assert p.returncode == 0, p.stderr.decode()
    out = p.stdout.decode().strip()
    return json.loads(out) if out else None


def markers(run_dir, run_id="run-1"):
    path = run_dir / "markers" / f"{run_id}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def decision(out):
    return out["hookSpecificOutput"]["permissionDecision"], out["hookSpecificOutput"]["permissionDecisionReason"]


def test_session_start_marker(run_dir):
    assert hook("session_start.py", {"source": "startup"}, run_dir) is None
    assert markers(run_dir)[0]["event"] == "hooks_loaded"


def test_routine_question_from_triaged_team_is_referred(run_dir):
    verdict, reason = decision(hook("ask_user_question.py", ASK, run_dir, team="app"))
    assert verdict == "deny" and "referred to the product team" in reason
    m = markers(run_dir)[0]
    assert m["event"] == "question" and m["question"][0]["question"] == "Which approach: A or B?"
    assert m["team"] == "app" and m["handover"] == "HO-20261016-ab12"


def test_routine_question_from_non_triaged_team_gets_default(run_dir):
    verdict, reason = decision(hook("ask_user_question.py", ASK, run_dir, team="product"))
    assert (verdict, reason) == ("deny", "DEFAULT ANSWER")
    assert markers(run_dir)[0]["event"] == "auto_answer"


@pytest.mark.parametrize("phase", ["consult", "limit_check"])
def test_question_inside_consultation_gets_default(run_dir, phase):
    verdict, reason = decision(hook("ask_user_question.py", ASK, run_dir, team="app", phase=phase))
    assert reason == "DEFAULT ANSWER" and markers(run_dir)[0]["event"] == "auto_answer"


def test_risky_question_escalated(run_dir):
    verdict, reason = decision(hook("ask_user_question.py", RISKY, run_dir, team="product"))
    assert verdict == "deny" and "owner must decide" in reason
    m = markers(run_dir)[0]
    assert (m["event"], m["keyword"]) == ("escalation", "push")


@pytest.mark.parametrize("question,keyword", [
    ("Удалить старый файл тестов test_greet.py и заменить его новым?", "удал"),
    ("Платёж около 2000 EUR: оплатить подрядчика?", "оплат"),
    ("Задеплоить на боевой сервер сейчас?", "задепло"),
])
def test_russian_question_at_stop_escalated_with_default_keywords(tmp_path, question, keyword):
    from radark.config import DEFAULT_KEYWORDS
    (tmp_path / "hook-config.json").write_text(json.dumps(dict(CFG, escalation_keywords=DEFAULT_KEYWORDS)),
                                               encoding="utf-8")
    msg = "Я подготовил изменение.\n\n" + question
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": msg}, tmp_path) is None
    m = markers(tmp_path)[0]
    assert (m["event"], m["keyword"]) == ("escalation", keyword)


def test_russian_routine_question_not_escalated(tmp_path):
    from radark.config import DEFAULT_KEYWORDS
    (tmp_path / "hook-config.json").write_text(json.dumps(dict(CFG, escalation_keywords=DEFAULT_KEYWORDS)),
                                               encoding="utf-8")
    msg = "Какой вариант продукта выбрать, чтобы продолжить?"
    hook("stop.py", {"stop_hook_active": False, "last_assistant_message": msg}, tmp_path, team="backend")
    assert markers(tmp_path)[0]["event"] == "question"


def test_plain_text_question_at_stop_referred(run_dir):
    msg = "I checked both options.\n\nShould the endpoint return 404 or an empty list?"
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": msg}, run_dir, team="backend") is None
    m = markers(run_dir)[0]
    assert m["event"] == "question" and m["question"] == "Should the endpoint return 404 or an empty list?"


def test_plain_text_options_list_detected(run_dir):
    msg = "Which approach do you prefer:\n\n1. Map\n2. Object"
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": msg}, run_dir) is None
    assert markers(run_dir)[0]["event"] == "question"


def test_plain_text_risky_question_escalated_for_any_team(run_dir):
    msg = "All tests pass. Should I push to dev?"
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": msg}, run_dir,
                team="product") is None
    assert markers(run_dir)[0]["event"] == "escalation"


def test_stop_without_question_nudged_once(run_dir):
    out = hook("stop.py", {"stop_hook_active": False, "last_assistant_message": "Implemented tasks 1-3."}, run_dir)
    assert out["decision"] == "block" and "Continue" in out["reason"]
    assert markers(run_dir)[0]["event"] == "nudge"
    # the second stop in a row arrives with stop_hook_active: allowed, no new marker
    assert hook("stop.py", {"stop_hook_active": True, "last_assistant_message": "Done."}, run_dir) is None
    assert len(markers(run_dir)) == 1


def test_question_from_non_triaged_team_at_stop_is_nudged(run_dir):
    out = hook("stop.py", {"stop_hook_active": False, "last_assistant_message": "Map or object?"}, run_dir,
               team="product")
    assert out["decision"] == "block"


def test_stop_after_referral_is_allowed(run_dir):
    hook("ask_user_question.py", ASK, run_dir, team="app")
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": "Waiting."}, run_dir) is None
    assert [m["event"] for m in markers(run_dir)] == ["question"]


@pytest.mark.parametrize("phase", ["consult", "limit_check"])
def test_consultation_stop_not_nudged(run_dir, phase):
    assert hook("stop.py", {"stop_hook_active": False, "last_assistant_message": "{}"}, run_dir,
                team="product", phase=phase) is None


def test_stop_reads_transcript_when_message_missing(run_dir, tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(json.dumps(x) for x in [
        {"type": "user", "message": {"content": "go"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Use A or B?"}]}},
    ]))
    assert hook("stop.py", {"stop_hook_active": False, "transcript_path": str(t)}, run_dir) is None
    assert markers(run_dir)[0]["event"] == "question"


def test_rate_limit_failure(run_dir):
    hook("stop_failure.py", {"hook_event_name": "StopFailure", "error": "rate_limit"}, run_dir)
    hook("stop_failure.py", {"hook_event_name": "StopFailure", "error": "server_error"}, run_dir)
    assert [m["event"] for m in markers(run_dir)] == ["usage_limit", "error"]
