"""Pick the next work item from a hub snapshot and the state (design D5). Pure functions only."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    kind: str  # work | review | archive
    team: str
    handover: str
    title: str
    phase: str  # propose | apply | review | archive | act
    recency: str
    team_index: int
    change: str | None = None
    return_comment: str | None = None
    expects: str | None = None
    resume_session: str | None = None
    timeout_resume: dict | None = None  # the record's resume_after_timeout this candidate uses (design T4)


def latest_activity(show: dict) -> str:
    """Time of the newest event that is not a plain 'seen' (same rule as ho's last_activity)."""
    times = [e["at"] for e in show.get("events", []) if e.get("action") != "seen"]
    return max(times + [show.get("created", "")])


def return_comment(show: dict, team: str) -> str | None:
    returns = [e for e in show.get("events", []) if e.get("action") == "return" and e.get("target") == team]
    return returns[-1].get("body", "").strip() if returns else None


def latest_return(show: dict, team: str) -> str | None:
    """Time of the newest `return` event that targets `team`, or None."""
    times = [e.get("at", "") for e in show.get("events", []) if e.get("action") == "return" and e.get("target") == team]
    return max(times) if times else None


def return_used(show: dict, rec: dict | None, team: str) -> bool:
    """A session of `team` for this item started after the latest return to it: the return's one session is used
    (no-loop N1)."""
    at = latest_return(show, team)
    if not at or not rec:
        return False
    return any(s.get("team") == team and (s.get("started") or "") > at for s in rec.get("sessions") or [])


def is_closed(show: dict) -> bool:
    return show.get("status") == "closed" or any(e.get("action") == "close" for e in show.get("events", []))


def escalation_links(records: dict[str, dict]) -> set[str]:
    return {rec["escalation"]["handover"] for rec in records.values() if rec.get("escalation")}


def is_escalation(item: dict, links: set[str]) -> bool:
    """An escalation handover the dispatcher sent to the owner: never work or review for a team (design E5)."""
    return "escalation" in (item.get("tags") or []) or item["id"] in links


# ho's SATISFIED: the states in which a recipient's part counts as finished, per `expects` (design H1)
SATISFIED = {"ack": {"acknowledged", "declined"}, "done": {"done", "declined"}, "response": {"answered", "declined"}}


def part_finished(expects: str | None, state: str | None) -> bool:
    """`pending` and `returned` are never finished; an unknown `expects` is finished only when declined."""
    return (state or "pending") in SATISFIED.get(expects, {"declined"})


def held_items(sent: dict[str, list[dict]], records: dict[str, dict], links: set[str]) -> dict[str, list[dict]]:
    """Items held while their team waits for a handover's result (design H3).
    sent: team -> `ho list --from <team>` items; returns item -> [{handover, team, state, title}]."""
    held: dict[str, list[dict]] = {}
    for tid, handovers in sent.items():
        for h in handovers:
            if h.get("status") != "open" or is_escalation(h, links):
                continue
            states = h.get("recipients") or {}
            waits = [{"handover": h["id"], "team": r, "state": states.get(r, "pending"), "title": h.get("title") or ""}
                     for r in h.get("to") or [] if not part_finished(h.get("expects"), states.get(r, "pending"))]
            for ref in h.get("refs") or []:
                if waits and (records.get(ref) or {}).get("team") == tid:
                    held.setdefault(ref, []).extend(waits)
    return held


def handovers_to_show(inboxes: dict[str, dict], records: dict[str, dict]) -> set[str]:
    """IDs the caller must fetch with `ho show` before calling `candidates`."""
    ids, links = set(), escalation_links(records)
    for inbox in inboxes.values():
        for group in ("action_required", "to_review"):
            ids.update(item["id"] for item in inbox.get(group, []) if not is_escalation(item, links))
    ids.update(hid for hid, rec in records.items() if rec.get("phase") == "done")
    return ids


def _blocked(rec: dict | None) -> bool:
    return bool(rec and (rec["flags"].get("escalated") or rec["flags"].get("stalled")))


def _resume(rec: dict | None, team: str) -> str | None:
    if rec and rec["flags"].get("keep_session") and rec["sessions"]:
        last = rec["sessions"][-1]
        if last.get("team") == team:
            return last["id"]
    return None


def _timeout_resume(rec: dict | None, team: str) -> dict | None:
    """A session of `team` ended by a time limit with progress, or interrupted: the next session resumes it once
    (design T4, sleep-aware D5)."""
    found = rec.get("resume_after_timeout") if rec else None
    return found if found and found.get("team") == team and found.get("session") else None


FULL_PHASES = ("propose", "apply", "archive")  # the `openspec` profile's work phases, the default


def work_phase(kind: str, item: dict, rec: dict | None, phases: tuple[str, ...] = FULL_PHASES) -> str:
    """`phases`: the work phases of the team's workflow profile; without propose a new handover goes straight to
    apply (workflow-profiles D6)."""
    if kind == "product":
        return "act"
    if "propose" not in phases:
        return "apply"
    started = rec is not None and (rec.get("change") or rec.get("phase") in ("apply", "done"))
    return "apply" if started or item.get("my_state") == "returned" else "propose"


def candidates(teams: list[tuple[str, str]], inboxes: dict[str, dict], shows: dict[str, dict],
               records: dict[str, dict], held: dict[str, list] | None = None,
               phases: dict[str, tuple[str, ...]] | None = None) -> list[Candidate]:
    """teams: (id, kind) in configuration order; inboxes: team -> `ho inbox --json`;
    phases: team -> the work phases of its workflow profile (default: propose, apply, archive); a team without an
    archive phase gets no archive candidate (workflow-profiles D6);
    shows: handover ID -> `ho show --json`; records: state records by handover ID;
    held: items waiting for a handover's result (`held_items`), not offered as work (design H4); exceptions: a return
    by the sender releases a held item for one session per return (no-loop N1), and a cut session resumes once."""
    kinds = dict(teams)
    order = {tid: i for i, (tid, _) in enumerate(teams)}
    links = escalation_links(records)
    out: list[Candidate] = []
    for tid, _ in teams:
        inbox = inboxes.get(tid, {})
        for item in inbox.get("action_required", []):
            hid, rec = item["id"], records.get(item["id"])
            if _blocked(rec) or is_escalation(item, links):
                continue
            show = shows.get(hid, {})
            phase = work_phase(kinds[tid], item, rec, (phases or {}).get(tid, FULL_PHASES))
            timed = _timeout_resume(rec, tid)
            released = item.get("my_state") == "returned" and not return_used(show, rec, tid)  # one session (N1)
            if held and held.get(hid) and not released and not timed:
                continue
            out.append(Candidate(
                kind="work", team=tid, handover=hid, title=item.get("title", ""), phase=phase,
                recency=latest_activity(show) if show else item.get("last_activity", ""),
                team_index=order[tid], change=rec.get("change") if rec else None,
                return_comment=return_comment(show, tid) if item.get("my_state") == "returned" else None,
                expects=item.get("expects"), resume_session=timed["session"] if timed else _resume(rec, tid),
                timeout_resume=timed,
            ))
        for item in inbox.get("to_review", []):
            hid, rec = item["id"], records.get(item["id"])
            if _blocked(rec) or is_escalation(item, links):
                continue
            show = shows.get(hid, {})
            timed = _timeout_resume(rec, tid)  # the record's team is the worker; a review resume names the reviewer
            out.append(Candidate(
                kind="review", team=tid, handover=hid, title=item.get("title", ""), phase="review",
                recency=latest_activity(show) if show else item.get("last_activity", ""),
                team_index=order[tid], resume_session=timed["session"] if timed else None, timeout_resume=timed,
            ))
    for hid, rec in records.items():
        tid = rec.get("team")
        if rec.get("phase") != "done" or kinds.get(tid) != "technical" or _blocked(rec):
            continue
        if "archive" not in (phases or {}).get(tid, FULL_PHASES):  # finished by the dispatcher without a session
            continue
        show = shows.get(hid)
        if not show or not is_closed(show):
            continue
        timed = _timeout_resume(rec, tid)
        out.append(Candidate(
            kind="archive", team=tid, handover=hid, title=show.get("title", ""), phase="archive",
            recency=latest_activity(show), team_index=order[tid], change=rec.get("change"),
            resume_session=timed["session"] if timed else _resume(rec, tid), timeout_resume=timed,
        ))
    return out


def pick(cands: list[Candidate]) -> Candidate | None:
    """Newest hub activity first; ties go to the team listed first in the configuration."""
    found = ordered(cands)
    return found[0] if found else None


def pick_free(cands: list[Candidate], busy_repos: set[str], busy_handovers: set[str],
              repo_of: dict[str, str] | None = None) -> Candidate | None:
    """The first candidate in `ordered` order whose repository and handover have no running session
    (parallel-sessions D2). repo_of: team -> resolved repository path, so two teams sharing a repository count as
    one; a team missing from it is its own repository."""
    repo_of = repo_of or {}
    for c in ordered(cands):
        if repo_of.get(c.team, c.team) not in busy_repos and c.handover not in busy_handovers:
            return c
    return None


def ordered(cands: list[Candidate]) -> list[Candidate]:
    by_team = sorted(cands, key=lambda c: (c.team_index, c.handover))
    return sorted(by_team, key=lambda c: c.recency, reverse=True)  # stable: ties keep team order
