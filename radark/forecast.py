"""Predict the next steps if every step succeeds (predict-next-steps D2–D5). Pure functions only.

The assumed outcomes edit copies of the hub snapshot the way `ho` would show them after the session
(ho.py, `inbox_view`: an item is in a recipient's `action_required` while its part is not
satisfied, in the sender's `to_review` once every part is satisfied and the handover is not closed), so `select` reads
them with its normal rule."""
from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass, field

from . import select as sel
from .state import new_record

PLACEHOLDER = "<proposed>"  # the change a predicted propose creates; printed as "change to be proposed"
# the event a finished part adds and the recipient state it leaves, per `expects` (ho's SATISFIED)
FINISH = {"done": ("done", "done"), "response": ("respond", "answered"), "ack": ("ack", "acknowledged")}


@dataclass
class Step:
    team: str
    phase: str  # propose | apply | act | review | archive | goal check
    handover: str | None
    title: str
    outcome: str  # the assumed outcome, for the console
    resume: bool = False  # continues a session cut by a time limit or an interruption


@dataclass
class Forecast:
    steps: list[Step] = field(default_factory=list)
    stop: str | None = None  # why it ended before the requested number of steps
    notes: list[str] = field(default_factory=list)  # e.g. "HO-... waits for owner"


def ts(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_ts(text: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def start_time(now: str, inboxes: dict, shows: dict) -> dt.datetime:
    """One second after the newest of `now` and the snapshot's activity (design D4)."""
    times = [now] + [sel.latest_activity(s) for s in shows.values()]
    times += [i.get("last_activity", "") for inbox in inboxes.values()
              for group in ("action_required", "to_review") for i in inbox.get(group, [])]
    return max(t for t in map(parse_ts, times) if t is not None) + dt.timedelta(seconds=1)


def simulate(teams: list[tuple[str, str]], inboxes: dict[str, dict], shows: dict[str, dict],
             records: dict[str, dict], held: dict[str, list] | None, steps: int, now: str, *,
             goal: bool = False, idle_ask: bool = False, product: str | None = None,
             skip: set[str] = frozenset()) -> Forecast:
    """The next `steps` steps of a run on this snapshot; `skip`: items the next loop would escalate (as in dry-run).
    The inputs are not changed."""
    inboxes, shows, records = copy.deepcopy(inboxes), copy.deepcopy(shows), copy.deepcopy(records)
    held = copy.deepcopy(held or {})
    t = start_time(now, inboxes, shows)
    out = Forecast()
    kinds = dict(teams)
    while len(out.steps) < steps:
        cands = [c for c in sel.ordered(sel.candidates(teams, inboxes, shows, records, held)) if c.handover not in skip]
        if not cands:
            if goal:
                out.steps.append(Step(product or "product team", "goal check", None, "", "a verdict"))
                out.stop = "the next steps depend on the goal check's verdict"
            else:
                out.stop = "nothing left to pick: the dispatcher would be idle" + (
                    " (the idle ask would ask the product team for the next backlog task)" if idle_ask else "")
            break
        cand = cands[0]
        title = cand.title or shows.get(cand.handover, {}).get("title", "")
        outcome = apply_outcome(cand, kinds, inboxes, shows, records, held, ts(t), out.notes)
        out.steps.append(Step(cand.team, cand.phase, cand.handover, title, outcome, resume=bool(cand.timeout_resume)))
        t += dt.timedelta(seconds=1)
    return out


def apply_outcome(cand: sel.Candidate, kinds: dict[str, str], inboxes: dict, shows: dict, records: dict,
                  held: dict, at: str, notes: list[str]) -> str:
    """Edit the copies as after a successful session of `cand` at time `at` (design D3); returns the outcome text."""
    hid, team = cand.handover, cand.team
    show = shows.setdefault(hid, {"id": hid, "title": cand.title, "status": "open", "events": []})
    rec = records.get(hid)
    if cand.timeout_resume and rec:  # the cut session finishes its phase (design D3)
        rec.pop("resume_after_timeout", None)
    if cand.phase == "review":
        event(show, at, team, "close")
        show["status"] = "closed"
        drop(inboxes, team, "to_review", hid)
        return "accepted and closed"
    if cand.phase == "archive":
        rec["phase"] = "archived"
        return "archived"
    if rec is None:
        rec = records[hid] = new_record(team)
    if held.get(hid) and not cand.timeout_resume:  # released by a return: one session, then held again (no-loop N1)
        rec.setdefault("sessions", []).append({"id": None, "team": team, "phase": cand.phase, "started": at})
        waits = ", ".join(dict.fromkeys(w["handover"] for w in held[hid]))
        return f"acts on the return; held again until {waits} is finished"
    if cand.phase == "propose":
        rec.update(change=PLACEHOLDER, phase="propose")
        event(show, at, team, "ack")
        if cand.expects != "ack":  # an ack that finished the part would end the work before its apply
            set_state(inboxes, show, team, hid, "acknowledged")
        return "change to be proposed"
    action, state = FINISH.get(cand.expects or "done", ("done", "done"))
    event(show, at, team, action)
    set_state(inboxes, show, team, hid, state)
    drop(inboxes, team, "action_required", hid)
    if kinds.get(team) == "technical":  # as Dispatcher.hub_phase: only the worker's `done` makes it done
        rec["phase"] = "done" if action == "done" else "apply"
    else:
        rec["phase"] = "act"
    release(held, hid, team)
    if not all(sel.part_finished(cand.expects, (show.get("recipients") or {}).get(r)) for r in recipients(show, team)):
        return "part finished; other recipients still work"
    show["status"] = "resolved"
    sender = show.get("from")
    if show.get("auto_close"):
        event(show, at, sender, "close")
        show["status"] = "closed"
        return "finished and auto-closed"
    if sender in kinds:
        inboxes.setdefault(sender, {}).setdefault("to_review", []).append(
            {"id": hid, "title": show.get("title") or cand.title, "from": sender, "expects": cand.expects,
             "last_activity": at})
        return f"finished; {sender} reviews"
    notes.append(f"{hid} waits for {sender or 'its author'} (not a configured team): no review step")
    return f"finished; waits for {sender or 'its author'}"


def event(show: dict, at: str, team: str | None, action: str) -> None:
    show.setdefault("events", []).append({"at": at, "team": team, "action": action, "body": ""})
    show["last_activity"] = at


def recipients(show: dict, team: str) -> list[str]:
    return list(show.get("to") or [team])


def set_state(inboxes: dict, show: dict, team: str, hid: str, state: str) -> None:
    show.setdefault("recipients", {})[team] = state
    for i in inboxes.get(team, {}).get("action_required", []):
        if i["id"] == hid:
            i["my_state"] = state


def drop(inboxes: dict, team: str, group: str, hid: str) -> None:
    inbox = inboxes.get(team, {})
    inbox[group] = [i for i in inbox.get(group, []) if i["id"] != hid]


def release(held: dict, hid: str, team: str) -> None:
    """`team` finished its part of `hid`: items waiting only for it are selectable again (design D3)."""
    for item in list(held):
        held[item] = [w for w in held[item] if not (w["handover"] == hid and w["team"] == team)]
        if not held[item]:
            del held[item]
