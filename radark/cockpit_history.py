"""History of finished work for the cockpit (change cockpit-history): pure functions over a pipeline's run log
(`runs.jsonl`) and the hub's `ho list --status all` items, plus a small cache of parsed run logs.

Nothing here writes a file or calls `ho`; `cockpit.Cockpit.history` gathers the inputs and calls `history()`."""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import machine as machine_mod

PERIODS = ("last-run", "24h", "7d", "all")
DEFAULT_PERIOD = "last-run"
SPANS = {"24h": dt.timedelta(hours=24), "7d": dt.timedelta(days=7)}
RESULTS = ("accepted", "in review", "returned", "open", "declined", "unknown")
ANSWERED = ("done", "answered", "responded")  # recipient states of a finished part (`answered` is ho's word)
ESCALATION_EVENTS = ("escalation", "escalation_sent")


# ---- time

def parse_time(value) -> dt.datetime | None:
    """A UTC record time (`YYYY-MM-DDTHH:MM:SS.mmmZ`) as an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def iso(t: dt.datetime | None) -> str | None:
    if t is None:
        return None
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _count(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, list):
        return len(value)
    return 0


# ---- reading the run log (design H2)

def parse_log(data: bytes) -> tuple[list[dict], int]:
    """(records, skipped lines). A line that is not a JSON object with a string `time` and `event` is skipped,
    which covers a half-written last line."""
    records, skipped = [], 0
    for line in data.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("time"), str) or not isinstance(rec.get("event"), str):
            skipped += 1
            continue
        records.append(rec)
    return records, skipped


@dataclass
class Log:
    state: str  # ok | missing | error
    records: list[dict] = field(default_factory=list)
    skipped: int = 0
    error: str | None = None


class LogCache:
    """Parsed run logs, reused while a file's size and modification time are unchanged (design H2)."""

    def __init__(self):
        self._cache: dict[str, tuple[tuple[int, int], Log]] = {}
        self._lock = threading.Lock()

    def read(self, path: Path) -> Log:
        key = machine_mod.norm(path)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            with self._lock:
                self._cache.pop(key, None)
            return Log("missing")
        except OSError as exc:
            return Log("error", error=str(exc))
        stamp = (st.st_size, st.st_mtime_ns)
        with self._lock:
            found = self._cache.get(key)
        if found and found[0] == stamp:
            return found[1]
        try:
            data = Path(path).read_bytes()
        except FileNotFoundError:
            return Log("missing")
        except OSError as exc:
            return Log("error", error=str(exc))
        records, skipped = parse_log(data)
        log = Log("ok", records, skipped)
        with self._lock:
            self._cache[key] = (stamp, log)
        return log


# ---- sessions (design H3)

@dataclass
class Session:
    team: str | None
    handover: str | None
    phase: str | None
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    duration_s: float = 0.0
    outcome: str | None = None
    running: bool = False
    denials: int = 0
    escalations: int = 0
    session: str | None = None
    order: int = 0

    def key(self) -> tuple:
        return (self.team, self.handover, self.phase)

    def last_seen(self) -> dt.datetime | None:
        """The latest known moment of the session (the end; its start when no end is known)."""
        return self.end or self.start

    def overlaps(self, since: dt.datetime | None, now: dt.datetime) -> bool:
        """A running session overlaps every window that includes now (design H6)."""
        first = self.start or self.end
        last = now if self.running else self.last_seen()
        if first is not None and first > now:
            return False
        return since is None or (last is not None and last >= since)

    def to_json(self) -> dict:
        return {"phase": self.phase, "team": self.team, "start": iso(self.start), "end": iso(self.end),
                "duration_s": None if self.running else round(self.duration_s), "outcome": self.outcome,
                "running": self.running, "denials": self.denials, "escalations": self.escalations,
                "session": self.session}


@dataclass
class Built:
    sessions: list[Session]
    escalated: set[str]
    run_starts: list[dt.datetime]


def _outcome(rec: dict) -> str | None:
    if rec.get("timed_out") is True:
        reason = rec.get("timeout_reason")
        return f"timed out ({reason})" if isinstance(reason, str) and reason else "timed out"
    out = rec.get("outcome")
    return out if isinstance(out, str) and out else None


def _str(value) -> str | None:
    return value if isinstance(value, str) and value else None


def build_sessions(records: list[dict]) -> Built:
    """Sessions from the records in file order: FIFO pairing of `session_start` and `session_end` by (team,
    handover, phase); `interrupted` and a later `dispatcher_start` close open sessions; the rest are running."""
    sessions: list[Session] = []
    open_: list[Session] = []
    escalated: set[str] = set()
    run_starts: list[dt.datetime] = []

    def take(key) -> Session | None:
        for i, s in enumerate(open_):
            if s.key() == key:
                return open_.pop(i)
        return None

    for n, rec in enumerate(records):
        event, at = rec.get("event"), parse_time(rec.get("time"))
        team, handover, phase = _str(rec.get("team")), _str(rec.get("handover")), _str(rec.get("phase"))
        if event == "dispatcher_start":
            for s in open_:  # the dispatcher that ran them is gone (design H3)
                s.running, s.outcome, s.end, s.duration_s = False, "interrupted", None, 0.0
            open_.clear()
            if at is not None:
                run_starts.append(at)
        elif event == "session_start":
            s = Session(team, handover, phase, start=at, running=True, order=n)
            sessions.append(s)
            open_.append(s)
        elif event == "session_end":
            s = take((team, handover, phase))
            duration = _number(rec.get("duration_s"))
            if s is None:
                start = at - dt.timedelta(seconds=duration) if at is not None and duration is not None else None
                s = Session(team, handover, phase, start=start, order=n)
                sessions.append(s)
            s.running, s.end = False, at
            if duration is None:
                duration = (at - s.start).total_seconds() if at is not None and s.start is not None else 0.0
            s.duration_s = max(duration, 0.0)
            s.outcome = _outcome(rec)
            s.denials, s.escalations = _count(rec.get("denials")), _count(rec.get("escalations"))
            s.session = _str(rec.get("session"))
            if s.escalations and handover:
                escalated.add(handover)
        elif event == "interrupted":
            s = take((team, handover, phase))
            if s is not None:
                s.running, s.end, s.outcome = False, at, "interrupted"
                s.duration_s = max((at - s.start).total_seconds(), 0.0) if at and s.start else 0.0
                s.session = _str(rec.get("session")) or s.session
        elif event in ESCALATION_EVENTS and handover:
            escalated.add(handover)
    return Built(sessions, escalated, run_starts)


# ---- results (design H5)

def result_of(item: dict | None, teams: list[str]) -> str:
    """The row's result from the hub's listed item and the row's teams; the first matching line of the design
    table wins (the state needing attention)."""
    if not isinstance(item, dict):
        return "unknown"
    recipients = item.get("recipients") if isinstance(item.get("recipients"), dict) else {}
    states = [recipients[t] for t in teams if t in recipients] or list(recipients.values())
    expects = item.get("expects")

    def finished(state):
        return state in ANSWERED or (state == "acknowledged" and expects == "ack")
    if "declined" in states and not any(finished(s) for s in states):
        return "declined"
    if item.get("status") == "closed":
        return "accepted"
    if "returned" in states:
        return "returned"
    if any(s == "pending" or (s == "acknowledged" and expects != "ack") for s in states):
        return "open"
    return "in review"


# ---- rows, filters, summary (design H4, H6)

@dataclass
class PipelineInput:
    """One pipeline's inputs: its name, its run log, the hub items by ID (None when the hub could not be read)."""
    name: str
    log: Log
    items: dict[str, dict] | None
    hub_error: str | None = None


def window_start(period: str, now: dt.datetime, run_starts: list[dt.datetime]) -> dt.datetime | None:
    if period == "last-run":
        return max(run_starts) if run_starts else None  # no dispatcher_start: the whole log
    if period in SPANS:
        return now - SPANS[period]
    return None


def _sort_time(s: Session) -> tuple:
    t = s.start or s.end
    return (t is None, t or dt.datetime.min.replace(tzinfo=dt.timezone.utc), s.order)


def rows_of(name: str, built: Built, items: dict[str, dict] | None) -> list[dict]:
    """One row per handover of the pipeline (sessions with a handover), with every session and the totals."""
    by_id: dict[str, list[Session]] = {}
    for s in built.sessions:
        if s.handover:
            by_id.setdefault(s.handover, []).append(s)
    rows = []
    for hid, sessions in by_id.items():
        sessions = sorted(sessions, key=_sort_time)
        teams = []
        for s in sorted(sessions, key=lambda x: x.order):
            if s.team and s.team not in teams:
                teams.append(s.team)
        starts = [s.start for s in sessions if s.start]
        ends = [s.end for s in sessions if s.end and not s.running]
        first, last = (min(starts) if starts else None), (max(ends) if ends else None)
        running = any(s.running for s in sessions)
        activity = [t for t in [last] + [s.last_seen() for s in sessions] if t]
        item = (items or {}).get(hid)
        title = item.get("title") if isinstance(item, dict) and isinstance(item.get("title"), str) else None
        rows.append({"pipeline": name, "id": hid, "title": title or hid, "teams": teams,
                     "first_start": first, "last_end": last,
                     "working_s": sum(s.duration_s for s in sessions if not s.running),
                     "wall_s": (last - first).total_seconds() if first and last else None,
                     "result": result_of(item, teams) if items is not None else "unknown",
                     "escalated": hid in built.escalated, "running": running,
                     "activity": max(activity) if activity else None, "sessions": sessions})
    return rows


def history(inputs: list[PipelineInput], period: str = DEFAULT_PERIOD, pipeline: str | None = None,
            now: dt.datetime | None = None) -> dict:
    """The `/api/history` answer (design H7) for the pipelines in `inputs`."""
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}")
    now = now or dt.datetime.now(dt.timezone.utc)
    pipes, rows = [], []
    summary = {"handovers": 0, "sessions": 0, "working_s": 0, "accepted": 0, "other_sessions": 0, "other_s": 0}
    working = other = 0.0
    for p in inputs:
        if pipeline is not None and p.name != pipeline:
            continue
        built = build_sessions(p.log.records)
        since = window_start(period, now, built.run_starts)
        pipes.append({"name": p.name, "state": "ok", "log": p.log.state, "skipped": p.log.skipped,
                      "since": iso(since), "hub_error": p.hub_error})
        for row in rows_of(p.name, built, p.items):
            hits = [s for s in row["sessions"] if s.overlaps(since, now)]
            if not hits:
                continue
            rows.append(row)
            summary["sessions"] += len(hits)
            working += sum(s.duration_s for s in hits if not s.running)
        for s in built.sessions:
            if not s.handover and s.overlaps(since, now):
                summary["other_sessions"] += 1
                other += 0.0 if s.running else s.duration_s
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    rows.sort(key=lambda r: (r["pipeline"], r["id"]))
    rows.sort(key=lambda r: r["activity"] or epoch, reverse=True)
    summary.update(handovers=len(rows), accepted=sum(1 for r in rows if r["result"] == "accepted"),
                   working_s=round(working), other_s=round(other))
    return {"period": period, "pipeline": pipeline, "now": iso(now), "pipelines": pipes, "summary": summary,
            "rows": [_row_json(r) for r in rows]}


def _row_json(r: dict) -> dict:
    return {"pipeline": r["pipeline"], "id": r["id"], "title": r["title"], "teams": r["teams"],
            "first_start": iso(r["first_start"]), "last_end": iso(r["last_end"]), "working_s": round(r["working_s"]),
            "wall_s": None if r["wall_s"] is None else round(r["wall_s"]), "result": r["result"],
            "escalated": r["escalated"], "running": r["running"], "sessions": [s.to_json() for s in r["sessions"]]}
