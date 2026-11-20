"""The current state of the pipelines for the cockpit's Now tab (change cockpit-now): a read-only scan of the
machine directory's instance records, the run directory's goal record, and pure functions that build one card per
pipeline from them, its run log and the hub's handover list.

Nothing here writes, creates or removes a file, takes a slot or calls `ho`: liveness comes from
`machine.probe_readonly` (design N2), never from `machine.probe`, which removes stale records (the dispatcher's job).
`cockpit.Cockpit.now` gathers the inputs and calls `now()`."""
from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cockpit_history as history_mod
from . import machine as machine_mod
from .cockpit_history import iso

RUNNING, NOT_RUNNING, UNKNOWN = "running", "not running", "unknown"


# ---- time

def parse_any(value) -> dt.datetime | None:
    """A record time as an aware datetime: UTC (`…Z`) or with an offset as given, a time without a zone (the
    machine layer's `local_now()`, a goal run's `ended`) as local time (design N3). None for anything else."""
    if not isinstance(value, str) or not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


# ---- instances (design N2, N3)

@dataclass
class Instance:
    """A live (or not probeable) dispatcher instance: its id (lock file stem) and record, read only."""
    id: str
    record: dict = field(default_factory=dict)
    unknown: bool = False  # the lock could not be probed: liveness unknown

    @property
    def pid(self):
        pid = self.record.get("pid")
        return pid if isinstance(pid, int) and not isinstance(pid, bool) else None

    @property
    def started(self) -> dt.datetime | None:
        return parse_any(self.record.get("started"))

    @property
    def sessions(self) -> int:
        n = self.record.get("sessions")
        return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else 0

    def key(self, name: str) -> str | None:
        value = self.record.get(name)
        return machine_mod.norm(value) if isinstance(value, str) and value else None

    def to_json(self) -> dict:
        return {"pid": self.pid, "started": iso(self.started), "sessions": self.sessions}


def live_instances(directory: Path) -> list[Instance]:
    """Every live instance of the machine directory, plus those whose lock cannot be probed (`unknown`); stale
    records (a free lock) and records without a lock file are ignored, nothing is removed or created."""
    folder = Path(directory) / "instances"
    try:
        locks = sorted(p for p in folder.iterdir() if p.suffix == ".lock")
    except OSError:  # no folder yet, or not readable: no instance known
        return []
    out = []
    for lock_path in locks:
        alive = machine_mod.probe_readonly(lock_path)
        if alive is None:
            out.append(Instance(lock_path.stem, unknown=True))
        elif alive:
            out.append(Instance(lock_path.stem, machine_mod.read_record(machine_mod.record_path(lock_path)) or {}))
    return out


def match(config: str | None, run_dir, instances: list[Instance]) -> list[Instance]:
    """The live instances of one pipeline: same normalized configuration path, else same run directory; oldest
    first (design N3)."""
    cfg = machine_mod.norm(config) if config else None
    rd = machine_mod.norm(run_dir) if run_dir else None
    found = []
    for inst in instances:
        if inst.unknown:
            continue
        if (cfg and inst.key("config") == cfg) or (rd and inst.key("run_dir") == rd):
            found.append(inst)
    epoch = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    return sorted(found, key=lambda i: (i.started or epoch, i.id))


# ---- the run directory (design N4, N5)

def run_dir_readable(run_dir) -> bool:
    """False when the run directory exists but cannot be listed; a missing one is fine (no run yet)."""
    try:
        with os.scandir(run_dir):
            return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def read_goal(run_dir) -> dict | None:
    """The run directory's `goal.json`, read only; None when missing or not valid."""
    if not run_dir:
        return None
    return machine_mod.read_record(Path(run_dir) / "goal.json")


def goal_name(path) -> str | None:
    """The goal file's name only, never its path (design N5); works for Windows and POSIX paths alike."""
    if not isinstance(path, str) or not path.strip():
        return None
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] or None


# ---- cards (design N4-N6)

@dataclass
class PipelineNow:
    """One shown pipeline's inputs. `state` is part 1's (`ok` / `missing` / `error`); `log` is None when the
    configuration cannot be read; `items` is None when the hub could not be read."""
    name: str
    config: str | None
    run_dir: Path | None = None
    state: str = "ok"
    message: str | None = None
    log: history_mod.Log | None = None
    dir_readable: bool = True
    goal: dict | None = None
    items: dict[str, dict] | None = None
    hub_error: str | None = None


def _title(items: dict | None, handover: str | None) -> str | None:
    if not handover:
        return None
    item = (items or {}).get(handover)
    title = item.get("title") if isinstance(item, dict) else None
    return title if isinstance(title, str) and title else "unknown"


def _facts(records: list[dict], built: history_mod.Built) -> dict:
    """Last event, last ended session, last `dispatcher_start`, last `stop` after it (design N6)."""
    last_event = None
    if records:
        rec = records[-1]
        last_event = {"time": iso(history_mod.parse_time(rec.get("time"))), "event": rec.get("event")}
    ended = [s for s in built.sessions if not s.running and s.end is not None]
    last = max(ended, key=lambda s: (s.end, s.order)) if ended else None
    last_session = None if last is None else {"end": iso(last.end), "outcome": last.outcome, "team": last.team,
                                              "handover": last.handover, "phase": last.phase}
    start_at = stop_at = None
    start_index = -1
    for n, rec in enumerate(records):
        if rec.get("event") == "dispatcher_start":
            start_index, start_at = n, history_mod.parse_time(rec.get("time"))
    wrap_at = None  # a wrap-up on demand seen by this run and not done yet (owner-wrap-up-on-demand D9)
    for rec in records[start_index + 1:]:
        if rec.get("event") == "stop":
            stop_at = history_mod.parse_time(rec.get("time")) or stop_at
        elif rec.get("event") == "owner_wrap_up_requested":
            wrap_at = history_mod.parse_time(rec.get("time")) or wrap_at
        elif rec.get("event") == "owner_wrap_up_done":
            wrap_at = None
    return {"last_event": last_event, "last_session": last_session, "last_start": iso(start_at),
            "last_stop": iso(stop_at), "wrap_up_pending": iso(wrap_at)}


def card(p: PipelineNow, instances: list[Instance], now: dt.datetime) -> dict:
    """The Now card of one pipeline (design N8); `instances` are its live instances (`match`)."""
    out = {"name": p.name, "state": NOT_RUNNING, "message": None, "log": p.log.state if p.log else None,
           "instances": [i.to_json() for i in instances], "goal": None, "last_goal": None, "running": [],
           "last_event": None, "last_session": None, "last_start": None, "last_stop": None,
           "wrap_up_pending": None, "hub_error": p.hub_error}
    if p.state == "missing":
        return {**out, "state": UNKNOWN, "message": "configuration file not found"}
    if p.state != "ok" or p.log is None:
        return {**out, "state": UNKNOWN, "message": p.message or "configuration not readable"}
    if p.log.state == "error" or not p.dir_readable:
        return {**out, "state": UNKNOWN, "message": "run log not readable"}
    built = history_mod.build_sessions(p.log.records)
    out.update(_facts(p.log.records, built))
    running = bool(instances)
    out["state"] = RUNNING if running else NOT_RUNNING
    if not running:  # a pending wrap-up belongs to a running dispatcher only
        out["wrap_up_pending"] = None
    g = p.goal if isinstance(p.goal, dict) else None
    if g:
        pids = {i.pid for i in instances}
        if running and g.get("status") == "running" and (g.get("pid") is None or g.get("pid") in pids):
            out["goal"] = {"name": goal_name(g.get("path")), "started": iso(parse_any(g.get("started")))}
        elif not running:
            out["last_goal"] = {"name": goal_name(g.get("path")), "status": g.get("status") if isinstance(
                g.get("status"), str) else None, "started": iso(parse_any(g.get("started"))),
                "ended": iso(parse_any(g.get("ended")))}
    for s in sorted((s for s in built.sessions if s.running), key=lambda s: s.order):
        elapsed = round((now - s.start).total_seconds()) if running and s.start else None
        out["running"].append({"team": s.team, "handover": s.handover, "title": _title(p.items, s.handover),
                               "phase": s.phase, "start": iso(s.start),
                               "elapsed_s": None if elapsed is None else max(elapsed, 0),
                               "state": "running" if running else "interrupted"})
    return out


# ---- the machine line and the answer (design N7, N8)

def machine_line(directory: Path, instances: list[Instance], matched: set[str]) -> dict:
    note = None
    try:
        limits = machine_mod.load_limits(directory)
    except machine_mod.MachineError:
        limits, note = machine_mod.Limits(), "machine.toml invalid, defaults shown"
    live = [i for i in instances if not i.unknown]
    return {"slots_used": sum(i.sessions for i in live), "slots_limit": limits.sessions,
            "running": 0, "other_instances": sum(1 for i in live if i.id not in matched),
            "unknown_instances": sum(1 for i in instances if i.unknown), "note": note}


def now(directory: Path, pipelines: list[PipelineNow], instances: list[Instance] | None = None,
        at: dt.datetime | None = None) -> dict:
    """The `/api/now` answer (design N8) for the shown pipelines, in their order."""
    at = at or dt.datetime.now(dt.timezone.utc)
    instances = live_instances(directory) if instances is None else instances
    cards, matched = [], set()
    for p in pipelines:
        mine = match(p.config, p.run_dir, instances)
        matched.update(i.id for i in mine)
        cards.append(card(p, mine, at))
    line = machine_line(directory, instances, matched)
    line["running"] = sum(1 for c in cards if c["state"] == RUNNING)
    return {"now": iso(at), "machine": line, "pipelines": cards}
