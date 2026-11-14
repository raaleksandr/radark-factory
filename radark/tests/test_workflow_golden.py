"""Golden guard (workflow-profiles D3, task 1.1): every prompt of the `openspec` profile renders exactly as before
workflow profiles existed. `golden/openspec_prompts.json` was generated from the code before the change with
`python -m radark.tests.test_workflow_golden`; a difference is a bug, not a justified change."""
from __future__ import annotations

import json
from pathlib import Path

from radark import prompts
from radark.select import Candidate

GOLDEN = Path(__file__).parent / "golden" / "openspec_prompts.json"
H = "HO-20261016-ab12"
GOAL = "Ship the export.\nKeep it small."


def cand(phase, **kw):
    base = dict(kind="work", team="app", handover=H, title="Export", phase=phase, recency="", team_index=0)
    base.update(kw)
    return Candidate(**base)


DENIALS = [{"tool": "Bash", "input": "git push"}, {"tool": "PowerShell", "input": "Stop-Process -Name node"}]
LIMITS = [{"kind": "wrap_up", "extensions": 1, "elapsed_s": 4 * 3600, "outcome": "finished"},
          {"kind": "cut", "reason": "idle_timeout", "extensions": 0, "elapsed_s": 1800}]


def render() -> dict[str, str]:
    out: dict[str, str] = {}
    cases = {
        "propose": cand("propose"),
        "apply_new": cand("apply", change="add-export"),
        "apply_new_no_change": cand("apply"),
        "apply_returned": cand("apply", change="add-export", return_comment="Add a CSV header.\nThen push."),
        "apply_returned_empty": cand("apply", change="add-export", return_comment=""),
        "apply_returned_no_change": cand("apply", return_comment="Fix it."),
        "review": cand("review", kind="review"),
        "archive": cand("archive", kind="archive", change="add-export"),
        "archive_no_change": cand("archive", kind="archive"),
        "act": cand("act", team="product", expects="response"),
        "act_no_expects": cand("act", team="product"),
    }
    for name, c in cases.items():
        out[f"phase/{name}"] = prompts.phase_prompt(c)
        out[f"phase/{name}/goal"] = prompts.phase_prompt(c, GOAL)
        out[f"phase/{name}/no_goal"] = prompts.phase_prompt(c, no_goal=prompts.NO_GOAL_NOTICE)
    r = cand("review", kind="review")
    out["phase/review/denials"] = prompts.phase_prompt(r, denials=DENIALS)
    out["phase/review/time_limits"] = prompts.phase_prompt(r, time_limits=LIMITS)
    out["phase/review/both/goal"] = prompts.phase_prompt(r, GOAL, denials=DENIALS, time_limits=LIMITS)
    for phase in ("propose", "apply", "review", "archive", "act"):
        c = cand(phase, change="add-export", expects="done")
        out[f"wrap_up/{phase}"] = prompts.wrap_up_message(c, 180, 2, 15)
        out[f"wrap_up/{phase}/lock/goal"] = prompts.wrap_up_message(c, 240, 1, 7.5, True, GOAL)
        out[f"wrap_up/{phase}/no_ext"] = prompts.wrap_up_message(c, 180, 0, 15)
    for phase in ("propose", "apply", "review", "archive", "act"):
        c = cand(phase, change="add-export", expects="done")
        out[f"resume/{phase}/same"] = prompts.timeout_resume_message(
            c, {"reason": "max_time", "duration_s": 3 * 3600, "phase": phase})
        out[f"resume/{phase}/idle/lock"] = prompts.timeout_resume_message(
            c, {"reason": "idle_timeout", "duration_s": 1500, "phase": phase}, True)
        out[f"resume/{phase}/sleep/goal"] = prompts.timeout_resume_message(
            c, {"reason": "sleep", "duration_s": 600, "phase": phase}, False, GOAL)
    nxt = cand("apply", change="add-export")
    out["resume/next_phase"] = prompts.timeout_resume_message(
        nxt, {"reason": "max_time", "duration_s": 7200, "phase": "propose", "limit_reason": "loops"})
    out["resume/next_phase/goal"] = prompts.timeout_resume_message(
        nxt, {"reason": "owner", "duration_s": 60, "phase": "propose"}, False, GOAL)
    q = {"question": "A or B?", "options": ["A", "B"]}
    out["consult/change"] = prompts.consult_prompt(q, "app", H, "add-export")
    out["consult/no_change"] = prompts.consult_prompt(q, "app", H, None)
    out["consult/goal"] = prompts.consult_prompt(q, "app", H, "add-export", GOAL)
    out["consult/no_goal"] = prompts.consult_prompt(q, "app", H, None, None, prompts.NO_GOAL_NOTICE)
    for name, change in (("change", "add-export"), ("no_change", None)):
        out[f"escalation/{name}"] = prompts.escalation_body(
            team="app", handover=H, reason="asked: push?", phase="apply", change=change, question=q,
            result_tail="Last words.", session="s-1", repo="/repos/app", denied=[{"tool": "Bash", "input": "x"}])
    out["escalation/minimal"] = prompts.escalation_body(
        team="app", handover=H, reason="stalled", phase=None, change=None, question=None, result_tail="",
        session=None, repo="/repos/app")
    out["goal_check"] = prompts.goal_check_prompt(GOAL)
    out["goal_check/notice/running"] = prompts.goal_check_prompt(
        GOAL, "Notice.\n\n", [{"team": "app", "handover": H, "title": "Export", "phase": "apply"}])
    return out


def test_openspec_prompts_unchanged():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = render()
    assert sorted(now) == sorted(golden)
    for key in golden:
        assert now[key] == golden[key], key


if __name__ == "__main__":  # regenerate only from the code before workflow profiles (task 1.1)
    GOLDEN.write_text(json.dumps(render(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
