"""Per-handover state (design D6) and the JSONL run log."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


def now_ts() -> str:
    """UTC timestamp in the hub's own format, so the two compare as strings."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def new_record(team: str) -> dict:
    return {
        "team": team,
        "change": None,
        "phase": None,  # propose | apply | done | declined | archived | act
        "sessions": [],
        "no_progress": 0,
        "triage_count": 0,
        "flags": {"escalated": False, "stalled": False, "keep_session": False},
        "reason": None,
        "last_seen_event": None,
        # open escalation handover to the owner (design E3): handover, team, session, phase, reason, sent, answered
        "escalation": None,
    }


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        self.records: dict[str, dict] = data.get("handovers", {})
        self.meta: dict = data.get("meta", {})

    def get(self, handover_id: str) -> dict | None:
        return self.records.get(handover_id)

    def ensure(self, handover_id: str, team: str) -> dict:
        rec = self.records.get(handover_id)
        if rec is None:
            rec = self.records[handover_id] = new_record(team)
        for key, value in new_record(team).items():
            rec.setdefault(key, value)
        return rec

    def blocked(self, handover_id: str) -> bool:
        rec = self.records.get(handover_id)
        return bool(rec and (rec["flags"].get("escalated") or rec["flags"].get("stalled")))

    def escalate(self, handover_id: str, team: str, reason: str, stalled: bool = False) -> dict:
        rec = self.ensure(handover_id, team)
        rec["flags"]["stalled" if stalled else "escalated"] = True
        rec["reason"] = reason
        return rec

    def clear(self, handover_id: str) -> bool:
        rec = self.records.get(handover_id)
        if not rec:
            return False
        rec["flags"]["escalated"] = rec["flags"]["stalled"] = False
        rec["no_progress"] = 0
        rec["triage_count"] = 0
        rec["reason"] = None
        rec["escalation"] = None  # an answer to a handover cleared by hand is ignored
        return True

    def open_escalation(self, handover_id: str) -> dict | None:
        rec = self.records.get(handover_id)
        link = rec.get("escalation") if rec else None
        return link if link and not link.get("answered") else None

    def escalation_links(self) -> set[str]:
        return {r["escalation"]["handover"] for r in self.records.values() if r.get("escalation")}

    def save(self) -> None:
        write_json_atomic(self.path, {"handovers": self.records, "meta": self.meta})


def read_goal(path: Path) -> str | None:
    """The goal file's text; None when it is missing, unreadable or only whitespace."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return text if text.strip() else None


@dataclass
class GoalRun:
    """The current goal run (goal-run design G2); mirrored to goal.json for observability only."""
    path: Path
    text: str
    max_sessions: int
    max_hours: float
    started: float = field(default_factory=time.time)
    started_ts: str = field(default_factory=now_ts)
    sessions: int = 0  # every session the dispatcher starts: work, triage consultation, goal check
    slept_s: float = 0.0  # sleeps of the computer during the run: not counted in its duration (sleep-aware D7)
    empty_continues: int = 0  # consecutive goal checks without a verdict or new hub activity (design G4)
    last_verdict: dict | None = None
    verdict_at: str | None = None  # UTC time of last_verdict
    verdict_carried: bool = False  # last_verdict comes from an earlier run on the same goal file
    steps: list = field(default_factory=list)  # one line per session of this run, for the report
    unescalated_denials: list = field(default_factory=list)  # denials in completed phases (escalate-denial D5)
    given_text: str = ""  # the text last given to a product-team session (design G6)
    pending: bool = False  # guidance changed: the next session is a goal check
    unreadable: bool = False
    status: str = "running"
    result: dict | None = None

    def __post_init__(self):
        self.given_text = self.given_text or self.text

    def awake_s(self) -> float:
        return time.time() - self.started - self.slept_s

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_json(self) -> dict:
        return {"path": str(self.path), "hash": self.hash, "started": self.started_ts, "status": self.status,
                "sessions": self.sessions, "max_sessions": self.max_sessions, "max_hours": self.max_hours,
                "slept_s": round(self.slept_s),
                "empty_continues": self.empty_continues, "guidance_pending": self.pending, "given_text": self.given_text,
                "last_verdict": self.last_verdict, "last_verdict_at": self.verdict_at, "result": self.result, "pid": os.getpid()}


class RunLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields) -> dict:
        record = {"time": now_ts(), "event": event, **fields}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
