"""Stop hook (design D3): let a referred or escalated session end, refer plain-text questions of
triaged teams, otherwise nudge once with "continue"."""
import json
import re
from pathlib import Path

import hookcommon as hc

_PHRASES = re.compile(
    r"\b(which (one|option|approach|variant)|should i|shall i|do you want|would you like|"
    r"do you prefer|would you prefer|let me know)\b",
    re.I,
)
_LIST_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)]|[A-Za-z][.)])\s+\S", re.M)


def last_message(data: dict) -> str:
    text = data.get("last_assistant_message")
    if isinstance(text, str) and text.strip():
        return text
    path = data.get("transcript_path")
    if not path or not Path(path).is_file():
        return ""
    last = ""
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            parts = [content]
        else:
            parts = [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
        joined = "\n".join(p for p in parts if p).strip()
        if joined:
            last = joined
    return last


def question_part(text: str) -> str | None:
    """The trailing paragraph(s) if they read as a question to the user, else None."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not paras:
        return None
    tail = paras[-1]
    if _LIST_LINE.search(tail) and len(paras) > 1 and not tail.rstrip().endswith("?"):
        tail = paras[-2] + "\n\n" + tail  # an options list after its question
    lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
    if any(ln.endswith("?") for ln in lines) or _PHRASES.search(tail):
        return tail
    return None


def decide(data: dict, e: dict, cfg: dict) -> tuple[str | None, dict | None, dict]:
    """Return (marker event or None, decision JSON or None to allow the stop, marker fields)."""
    if data.get("stop_hook_active") or e.get("phase") in ("consult", "limit_check"):  # consultations are one-shot
        return None, None, {}
    if any(m.get("event") in ("question", "escalation") for m in hc.read_markers(e)):
        return None, None, {}
    question = question_part(last_message(data))
    if question:
        keyword = hc.matched_keyword(question, cfg.get("escalation_keywords", []))
        if keyword:
            return "escalation", None, {"keyword": keyword, "question": question, "source": "stop"}
        if e["team"] and e["team"] in cfg.get("triage_teams", []):
            return "question", None, {"question": question, "source": "stop"}
    return "nudge", {"decision": "block", "reason": hc.NUDGE_TEXT}, {}


def main() -> None:
    data = hc.read_input()
    e = hc.env()
    event, decision, fields = decide(data, e, hc.hook_config(e["run_dir"]))
    if event:
        hc.write_marker(e, event, **fields)
    if decision:
        hc.emit(decision)


if __name__ == "__main__":
    main()
