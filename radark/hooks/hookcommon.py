"""Shared helpers for the hook scripts. Hooks run as plain scripts (exec form), so this module is
imported from the scripts' own directory, not through the radark package."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ANSWER = (
    "No user is available. Choose the best variant yourself, record the assumption "
    "in the change's design/tasks notes, and continue."
)
ESCALATE_TEXT = (
    "Do not proceed with this. The owner must decide it. End your turn now and state exactly "
    "what the owner must decide."
)
REFER_TEXT = (
    "This question is referred to the product team. End your turn now; you will be resumed with the answer."
)
NUDGE_TEXT = (
    "Continue: no user is available; follow the standing rule. If this phase is already complete, "
    "repeat your final summary (including any `CHANGE:` line) and stop."
)


def read_input() -> dict:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {"_unparsed": raw[:2000]}
    return data if isinstance(data, dict) else {"_unparsed": raw[:2000]}


def env() -> dict:
    return {
        "run_dir": os.environ.get("HARNESS_RUN_DIR"),
        "run_id": os.environ.get("HARNESS_RUN_ID") or os.environ.get("HARNESS_SESSION") or "unknown",
        "session": os.environ.get("HARNESS_SESSION"),
        "team": os.environ.get("HARNESS_TEAM"),
        "handover": os.environ.get("HARNESS_HANDOVER"),
        "phase": os.environ.get("HARNESS_PHASE"),
    }


def hook_config(run_dir: str | None) -> dict:
    cfg = {"default_answer": DEFAULT_ANSWER, "escalation_keywords": [], "triage_teams": []}
    if run_dir:
        path = Path(run_dir) / "hook-config.json"
        if path.is_file():
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def markers_path(e: dict) -> Path | None:
    if not e["run_dir"]:
        return None
    return Path(e["run_dir"]) / "markers" / f"{e['run_id']}.jsonl"


def write_marker(e: dict, event: str, **fields) -> None:
    path = markers_path(e)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "event": event, "session": e["session"], "team": e["team"], "handover": e["handover"], **fields,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_markers(e: dict) -> list[dict]:
    path = markers_path(e)
    if path is None or not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fold(s: str) -> str:
    return s.lower().replace("ё", "е")


def matched_keyword(text: str, keywords: list[str]) -> str | None:
    for kw in keywords:
        if re.search(r"\b" + re.escape(_fold(kw)), _fold(text)):
            return kw
    return None


def emit(data: dict) -> None:
    sys.stdout.write(json.dumps(data))  # ASCII: the pipe encoding may not be UTF-8
    sys.stdout.flush()
