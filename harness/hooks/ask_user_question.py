"""PreToolUse hook for AskUserQuestion (design D3): escalate, refer to product triage, or answer.

Every branch denies the call with a reason; Claude Code shows the reason to the agent."""
import json

import hookcommon as hc


def decide(data: dict, e: dict, cfg: dict) -> tuple[str, str, dict]:
    """Return (marker event, reason shown to the agent, marker fields)."""
    tool_input = data.get("tool_input") or {}
    questions = tool_input.get("questions", tool_input)
    text = json.dumps(questions, ensure_ascii=False)
    keyword = hc.matched_keyword(text, cfg.get("escalation_keywords", []))
    if keyword:
        return "escalation", hc.ESCALATE_TEXT, {"keyword": keyword, "question": questions, "source": "ask_user_question"}
    if e["team"] and e["team"] in cfg.get("triage_teams", []) and e.get("phase") not in ("consult", "limit_check"):
        return "question", hc.REFER_TEXT, {"question": questions, "source": "ask_user_question"}
    answer = cfg.get("default_answer") or hc.DEFAULT_ANSWER
    return "auto_answer", answer, {"question": questions, "answer": answer}


def main() -> None:
    data = hc.read_input()
    e = hc.env()
    event, reason, fields = decide(data, e, hc.hook_config(e["run_dir"]))
    hc.write_marker(e, event, **fields)
    hc.emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


if __name__ == "__main__":
    main()
