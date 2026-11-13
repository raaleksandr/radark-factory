"""CLI and loop: python -m radark [--config harness.toml] run|once|dry-run|plan|escalations|clear|keep|note."""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config as config_mod
from . import forecast
from . import prompts
from . import select as sel
from .awake import FORMS as KEEP_AWAKE_FORMS, KeepAwake, Keeper, cover_end_time, parse_keep_awake, wanted
from .clock import Sleep, SleepWatch, parse_until
from .hub import Hub, HoError
from .runner import Runner, SessionResult, kill_pid_tree
from .state import GoalRun, RunLog, State, now_ts, read_goal, write_json_atomic

CONSULT_TOOLS = ["Read", "Grep", "Glob"]
BUDGET_OPTIONS = {"five_hour": "--budget-5h", "seven_day": "--budget-7d"}  # run usage budget (run-usage-budget D1)
GOAL_EXIT = {"complete": 0, "stopped": 0, "blocked": 4, "stalled": 5, "limit": 6}  # goal-run design G7
GOAL_STALL_LIMIT = 2  # consecutive goal checks without new hub activity end the run (design G4)
USAGE_MARGIN_S = 60  # after a window's reported reset: covers clock skew against the server (design D3)
USAGE_REMINDER_S = 3600  # one console reminder per hour during a long usage wait (design D6)


class HooksNotLoaded(Exception):
    pass


# -- lock ---------------------------------------------------------------------------

def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_started(pid: int) -> float | None:
    """Unix time a running process was created; None when unknown (then it is never killed by PID)."""
    if os.name != "nt" or pid <= 0:
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    times = [ctypes.c_ulonglong() for _ in range(4)]  # FILETIMEs: creation, exit, kernel, user
    ok = kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))
    kernel32.CloseHandle(handle)
    return (times[0].value - 116444736000000000) / 1e7 if ok else None


class Lock:
    def __init__(self, path: Path):
        self.path = path

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    pid = int(self.path.read_text().strip() or 0)
                except (OSError, ValueError):
                    pid = 0
                if pid_alive(pid):
                    raise SystemExit(f"Another dispatcher (PID {pid}) holds {self.path}; not starting.")
                print(f"{stamp()}  ! replacing stale lock {self.path} (PID {pid} is not running)")
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w") as fh:
                fh.write(str(os.getpid()))
            return
        raise SystemExit(f"Could not create lock {self.path}")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


# -- dispatcher -----------------------------------------------------------------------

class Dispatcher:
    def __init__(self, cfg: config_mod.Config, hub: Hub | None = None, runner: Runner | None = None, out=None,
                 watch: SleepWatch | None = None):
        self.cfg = cfg
        self.hub = hub or Hub(cfg.ho, cfg.hub)
        self.runner = runner
        self._print = out or console_print
        self.state = State(cfg.run_dir / "state.json")
        self.log = RunLog(cfg.run_dir / "runs.jsonl")
        self.stop_after_session = False
        self._interrupts = 0
        self._usage_announced = None  # (window, until) of the usage wait last printed by this process
        self._usage_note = 0.0  # time of the last usage wait line, for the hourly reminder
        self.goal: GoalRun | None = None
        self.budget: dict[str, int] = {}  # usage budget of this run per window, from the options; never stored
        self.until: float | None = None  # end time of this run (epoch seconds), from `--until`; never stored
        self.keep_awake: KeepAwake = cfg.keep_awake  # `--keep-awake` replaces it for the run; never stored
        self.keeper: Keeper | None = None  # the thread that holds the Windows request (keep-awake D4)
        self.watch = watch or SleepWatch()
        self._running: dict | None = None  # team, handover, phase of the session now running, for `suspend`
        self.check_runner: Runner | None = None  # the limit check next to a work session (check-session D2)

    def get_runner(self) -> Runner:
        if self.runner is None:
            self.runner = Runner(self.cfg)
        return self.runner

    def get_check_runner(self) -> Runner:
        if self.check_runner is None:
            self.check_runner = Runner(self.cfg)
        return self.check_runner

    def out(self, text: str = "") -> None:
        self._print(text)

    def problem(self, text: str) -> None:
        """One marked console line for a problem, printed where it is logged (design D5)."""
        self.out(f"{stamp()}  ! {text}")

    def slept(self) -> Sleep | None:
        """Report a sleep of the computer once: console line, `suspend` event, goal run's slept time (design D2, D7)."""
        self.keep_awake_changes()  # called on every loop and runner iteration (keep-awake D6)
        s = self.watch.check()
        if s is None:
            return None
        self.log.write("suspend", start=s.start, end=s.end, seconds=round(s.seconds), during=self._running)
        self.problem(f"computer slept {stamp(s.start)}{sym('–')}{stamp(s.end)} ({duration_text(s.seconds)}) "
                     "- not counted")
        if self.goal:
            self.goal.slept_s += s.seconds
            self.goal_save()
        return s

    # ---- selection

    def snapshot(self, held: dict[str, list] | None = None) -> tuple[list, dict, dict, dict]:
        """(teams, inboxes, shows, held) that selection reads; shared by the loop, dry-run and plan
        (predict-next-steps D6). held: by default the holds stored in the records (design H4)."""
        if held is None:
            held = {hid: rec["waiting_for"] for hid, rec in self.state.records.items() if rec.get("waiting_for")}
        inboxes = {t.id: self.hub.inbox(t.id) for t in self.cfg.teams}
        shows = {}
        for hid in sorted(sel.handovers_to_show(inboxes, self.state.records)):
            try:
                shows[hid] = self.hub.show(hid)
            except HoError as exc:
                self.problem(f"ho show {hid} failed: {exc}")
        return [(t.id, t.kind) for t in self.cfg.teams], inboxes, shows, held

    def plan(self, held: dict[str, list] | None = None) -> list[sel.Candidate]:
        teams, inboxes, shows, held = self.snapshot(held)
        return sel.ordered(sel.candidates(teams, inboxes, shows, self.state.records, held))

    # ---- one work item

    def run_candidate(self, cand: sel.Candidate) -> SessionResult:
        rec = self.state.ensure(cand.handover, cand.team if cand.kind != "review" else self._worker(cand))
        if cand.title and not rec.get("title"):  # for resumes and escalations later (design D4)
            rec["title"] = cand.title
        title = cand.title or rec.get("title")
        goal = self.goal_for(cand.team)
        if not cand.timeout_resume:
            result = self.session(cand.team, self.work_prompt(cand, rec, goal), cand.phase, cand.handover,
                                  resume=cand.resume_session, title=title)
            return self.finish(cand, rec, result)
        rec.pop("resume_after_timeout", None)  # one resume per time-limited session (design T4)
        info = cand.timeout_resume
        lock = self.cfg.team(cand.team).repo / ".git" / "index.lock"
        if lock.is_file():
            self.log.write("stale_index_lock", team=cand.team, handover=cand.handover, path=str(lock))
        self.log.write("resume_after_timeout", team=cand.team, handover=cand.handover, session=info["session"],
                       reason=info.get("reason"), duration_s=info.get("duration_s"), phase=cand.phase)
        step = "resume after time limit" if info.get("reason") in TIME_LIMIT else "resume after interruption"
        result = self.session(cand.team, prompts.timeout_resume_message(cand, info, lock.is_file(), goal), cand.phase,
                              cand.handover, resume=info["session"], title=title, step=step)
        if resume_failed(result):
            self.out(f"    session {info['session']} could not be resumed; starting a fresh {cand.phase} session")
            result = self.session(cand.team, self.work_prompt(cand, rec, goal), cand.phase, cand.handover, title=title)
        return self.finish(cand, rec, result)

    def finish(self, cand: sel.Candidate, rec: dict, result: SessionResult, since: str | None = None) -> SessionResult:
        """Triage any question, then update the record (shared by new work and owner-answer resumes)."""
        since = since or result.started  # progress counts from the first session, also across triage resumes
        while result.outcome == "question" and self.cfg.triage:
            resumed = self.triage(cand, result, since)
            if resumed is None:
                break
            result = resumed
        self.after_session(cand, rec, result, since)
        self.state.meta.pop("running", None)  # its end is processed (design D6)
        self.state.save()
        return result

    def _worker(self, cand: sel.Candidate) -> str:
        rec = self.state.get(cand.handover)
        return rec["team"] if rec else cand.team

    def session(self, team: str, prompt: str, phase: str, handover: str | None, *, resume: str | None = None,
                tools: list[str] | None = None, json_schema: dict | None = None,
                since: str | None = None, title: str | None = None, step: str | None = None) -> SessionResult:
        """`since`: start of the item's work when this session continues it (triage or owner resume); progress
        is then measured from that session's snapshot, otherwise from a snapshot taken now (design T3).
        `title` and `step` (a resume's kind) are for the console only (console-progress D1)."""
        runner = self.get_runner()
        repo = self.cfg.team(team).repo
        work = bool(handover) and phase != "consult"
        rec = self.state.ensure(handover, team) if work else None
        base = snapshot(repo, rec.get("change")) if work and since is None else None
        self.log.write("session_start", team=team, repo=str(repo), handover=handover, phase=phase,
                       prompt=prompt, resume=resume)
        if handover and not title:
            title = (self.state.get(handover) or {}).get("title")
        for line in start_lines(team, phase, handover, title, step):
            self.out(line)
        what = f"{team} {handover}" if handover else f"{team} {STEP_KIND.get(phase, phase)}"
        if self.goal:
            self.goal.sessions += 1
        self._running = {"team": team, "handover": handover, "phase": phase}

        def on_start(session_id: str, run_id: str, pid: int) -> None:  # recovered by the next start (design D6)
            self.state.meta["running"] = {"session": session_id, "run_id": run_id, "team": team, "handover": handover,
                                          "phase": phase, "step": step, "pid": pid, "started": now_ts()}
            self.state.save()

        on_deadline, on_abort = (self.limit_watch(team, handover, title, since, base) if work else (None, None))
        old = signal.signal(signal.SIGINT, self._on_interrupt)
        try:
            r = runner.run(team, prompt, phase=phase, handover=handover, resume=resume, tools=tools,
                           json_schema=json_schema, on_usage=self.usage_watch(team, handover), on_start=on_start,
                           sleep_check=self.slept, on_deadline=on_deadline, on_deadline_abort=on_abort)
        finally:
            signal.signal(signal.SIGINT, old)
            self._interrupts = 0
            self._running = None
        self.record_usage(r)
        for m in r.markers:
            if m.get("event") in ("auto_answer", "escalation", "question", "nudge"):
                self.log.write(m["event"], team=team, handover=handover, session=r.session_id,
                               **{k: v for k, v in m.items() if k not in ("time", "event", "team", "handover", "session")})
            if m.get("event") == "question":  # an escalation marker gets its line from escalate()
                head = f"{what}: question for product triage: "
                self.problem(head + question_text(m.get("question"), LINE_WIDTH - 11 - len(head)))
        for d in r.denials:
            self.log.write("denial", team=team, handover=handover, session=r.session_id, denial=d)
            self.problem(f"{what}: permission denied: {d.get('tool_name') if isinstance(d, dict) else d}")
        if work:
            ignored: list[str] = []
            r.progress_sources = self.made_progress(team, handover, since or r.started,
                                                    base if since is None else base_of(rec, since),
                                                    phase=phase, ignored=ignored)
            r.progress_ignored = ignored[0] if ignored else None
        self.log.write("session_end", team=team, handover=handover, phase=phase, session=r.session_id,
                       exit_code=r.exit_code, outcome=r.outcome, duration_s=r.duration_s,
                       auto_answers=len(r.markers_of("auto_answer")), denials=len(r.denials),
                       escalations=len(r.markers_of("escalation")), timed_out=r.timed_out,
                       timeout_reason=r.timeout_reason, interrupt_cause=r.interrupt_cause,
                       progress_sources=r.progress_sources,
                       stream=r.stream_path, result=r.result_text[-2000:])
        self.out(end_line(team, phase, step, r))
        if self.goal:
            self.goal.steps.append(end_line(team, phase, step, r, handover))
        if r.outcome == "error":
            self.problem(f"{what}: session ended with an error: {error_cause(r)}")
        if self.goal:
            self.goal_save()
        if work:
            rec["sessions"].append({"id": r.session_id, "team": team, "phase": phase, "outcome": r.outcome,
                                    "started": r.started, "ended": r.ended, **({"base": base} if base else {})})
        if not work:  # a step without a handover is handled by its caller right away
            self.state.meta.pop("running", None)
        # a session cut by a limit before its hooks ran is a hang, not a broken hook setup
        if (not r.hooks_loaded and r.exit_code is not None and not r.killed and not r.timed_out
                and not r.interrupt_cause):
            self.state.meta.pop("running", None)
            self.state.save()
            raise HooksNotLoaded(f"session {r.session_id}: the dispatcher's hooks did not fire")
        if r.outcome == "usage_limit":
            self.start_backoff(r)
        elif r.outcome != "error":
            self.state.meta.pop("backoff_minutes", None)
        if not work:
            self.state.save()
        return r

    def _on_interrupt(self, signum, frame) -> None:
        self._interrupts += 1
        self.stop_after_session = True
        if self._interrupts == 1:
            self.out("\nFinishing the current session, then exiting; press Ctrl+C again to end it now.")
        else:
            self.out("\nEnding the current session.")
            self.get_runner().kill()
            if self.check_runner is not None:  # a limit check running next to it (check-session D2)
                self.check_runner.kill()

    def recover(self) -> None:
        """A session left running by a dispatcher that is gone (window closed, reboot, crash): end its leftover
        process, and resume it next if it worked on a handover; a short step runs again when due (design D6)."""
        run = self.state.meta.pop("running", None)
        if not isinstance(run, dict):
            return
        pid, started = run.get("pid") or 0, iso_ts(run["started"]) if run.get("started") else 0
        created = process_started(pid) if pid_alive(pid) else None
        if created is not None and created <= started + 1:  # a later process only reuses the PID
            kill_pid_tree(pid)
        stream = self.cfg.run_dir / "sessions" / f"{run.get('run_id')}.jsonl"
        try:
            at = stream.stat().st_mtime
        except OSError:
            at = started or time.time()
        team, hid, phase = run.get("team"), run.get("handover"), run.get("phase")
        rec = self.state.get(hid) if hid else None
        resumable = rec is not None and phase not in STEP_KIND and run.get("step") != "owner answer"
        what = f"{team} {hid}" if hid else f"{team} {STEP_KIND.get(phase, phase)}"
        self.log.write("interrupted", team=team, handover=hid, phase=phase, session=run.get("session"),
                       cause="dispatcher_stopped", resumed=resumable)
        self.problem(f"{what}: session {run.get('session')} ({STEP_KIND.get(phase, phase)}) was interrupted at "
                     f"{stamp(at)} - dispatcher stopped; "
                     + ("it will be resumed" if resumable else "it will run again when due"))
        if resumable:
            rec["sessions"].append({"id": run.get("session"), "team": team, "phase": phase, "outcome": "interrupted",
                                    "started": run.get("started"), "ended": None})
            rec["resume_after_timeout"] = {"session": run.get("session"), "team": team, "phase": phase,
                                           "reason": "dispatcher_stopped", "duration_s": None}
        self.state.save()

    def start_backoff(self, r: SessionResult | None = None) -> None:
        """Wait for the exhausted window's reported reset; the doubling back-off only when none is known (design D4)."""
        now = time.time()
        found = exhausted_window(r.usage if r else {}, now) or exhausted_window(self.state.meta.get("usage"), now)
        if found:
            window, w = found
            self.log.write("usage_limit", window=window, resets_at=w["resets_at"])
            self.wait_for_reset(window, w, "limit_hit")
            self.state.save()
            return
        minutes = self.state.meta.get("backoff_minutes")
        minutes = self.cfg.usage_backoff_minutes if not minutes else min(minutes * 2, self.cfg.usage_backoff_max_minutes)
        self.state.meta["backoff_minutes"] = minutes
        self.state.meta["backoff_until"] = time.time() + minutes * 60
        self.log.write("usage_limit", backoff_minutes=minutes)
        self.problem(f"Usage limit reached; no new session for {minutes} min.")
        self.state.save()

    def escalate(self, handover: str, team: str, reason: str, stalled: bool = False, *, session: str | None = None,
                 phase: str | None = None, question=None, result_tail: str = "", title: str | None = None,
                 body: str | None = None) -> None:
        """Mark the item and send the owner an escalation handover from `team` (the escalated session's team);
        `title` / `body` replace the generic wording."""
        rec = self.state.escalate(handover, team, reason, stalled=stalled)
        self.log.write("stalled" if stalled else "escalation", team=team, handover=handover, reason=reason)
        self.problem(f"{'STALLED' if stalled else 'ESCALATED'} {handover} ({team}): {reason}")
        open_link = self.state.open_escalation(handover)
        if open_link:  # one open escalation handover per item (design E3)
            self.out(f"    escalation handover {open_link['handover']} is still open; not sending another")
        else:
            body = body or prompts.escalation_body(team=team, handover=handover, reason=reason, phase=phase,
                                                   change=rec.get("change"), question=question,
                                                   result_tail=result_tail, session=session,
                                                   repo=str(self.cfg.team(team).repo))
            sent = self.send_to_owner(team, title or prompts.escalation_title(team, reason), body, handover, reason)
            if sent:
                rec["escalation"] = {"handover": sent, "team": team, "session": session, "phase": phase,
                                     "reason": reason, "question": question, "sent": now_ts(), "answered": False}
        self.state.save()

    def send_to_owner(self, team: str, title: str, body: str, handover: str | None, reason: str) -> str | None:
        """`ho new` an escalation handover to the owner, then `ho sync`. Returns its ID, or None on failure."""
        try:
            hid = self.hub.new(team, self.cfg.owner_team, title, body, tags=["escalation"],
                               refs=[handover] if handover else [])["id"]
        except (HoError, KeyError) as exc:
            self.log.write("escalation_send_failed", team=team, handover=handover, reason=reason, error=str(exc))
            self.problem(f"could not send the escalation handover to {self.cfg.owner_team}: {exc} "
                         "(the item stays escalated; see `escalations`)")
            return None
        self.log.write("escalation_sent", team=team, handover=handover, escalation=hid, reason=reason)
        self.out(f"    escalation handover {hid} sent to {self.cfg.owner_team}")
        self.sync_hub()
        return hid

    def sync_hub(self) -> None:
        try:
            self.hub.sync()
        except HoError as exc:
            self.problem(f"ho sync failed: {exc}")

    # ---- owner answers (design E4)

    def owner_answers(self) -> list[tuple[str, dict, dict, dict]]:
        """(item, link, answer event, escalation handover) for every open escalation the owner answered, oldest first."""
        found = []
        for hid in list(self.state.records):
            link = self.state.open_escalation(hid)
            if not link or not self.state.blocked(hid):  # `clear` drops the link; an answer then is ignored
                continue
            try:
                shown = self.hub.show(link["handover"])
            except HoError as exc:
                self.problem(f"ho show {link['handover']} failed: {exc}")
                continue
            event = next((e for e in shown.get("events", []) if e.get("team") == self.cfg.owner_team
                          and e.get("action") in ("respond", "decline")), None)
            if event:
                found.append((hid, link, event, shown))
        return sorted(found, key=lambda f: f[2].get("at", ""))

    def resume_with_answer(self, hid: str, link: dict, event: dict, shown: dict) -> SessionResult:
        action, answer = event["action"], (event.get("body") or "").strip()
        team, phase = link["team"], link.get("phase") or "apply"
        if action == "decline" and not sel.is_closed(shown):  # in case `--auto-close` left it open
            try:
                self.hub.close(link["handover"], team, "declined by owner", force=True)
                self.sync_hub()
            except HoError as exc:
                self.problem(f"ho close {link['handover']} failed: {exc}")
        link["answered"] = True
        self.state.clear(hid)
        rec = self.state.ensure(hid, team)
        self.log.write("owner_answer", team=team, handover=hid, escalation=link["handover"], action=action,
                       answer=answer, session=link.get("session"))
        self.out(f"{stamp()}  owner {'declined' if action == 'decline' else 'answered'} {link['handover']} "
                 f"for {hid}; resuming {team}")
        self.state.save()
        cand = self.answer_candidate(hid, team, phase, rec)
        # progress counts from the escalated session's first start: its hub activity (e.g. `ho ack`) counts (design E8)
        since = min((s["started"] for s in rec["sessions"] if s["id"] == link.get("session") and s.get("started")),
                    default=None)
        result = None
        if link.get("session"):
            result = self.session(team, prompts.owner_resume_message(link, action, answer), phase, hid,
                                  resume=link["session"], since=since, title=cand.title, step="owner answer")
        if result is None or resume_failed(result):
            self.out(f"    session {link.get('session')} could not be resumed; starting a fresh {phase} session")
            result = self.session(team, self.work_prompt(cand, rec, self.goal_for(team))
                                  + prompts.owner_fresh_note(link, action, answer),
                                  phase, hid, since=since, title=cand.title, step="owner answer")
        return self.finish(cand, rec, result, since)

    def answer_candidate(self, hid: str, team: str, phase: str, rec: dict) -> sel.Candidate:
        try:
            shown = self.hub.show(hid)
        except HoError:
            shown = {}
        kind = phase if phase in ("review", "archive") else "work"
        if shown.get("title") and not rec.get("title"):
            rec["title"] = shown["title"]
        return sel.Candidate(kind=kind, team=team, handover=hid, title=shown.get("title") or rec.get("title") or "",
                             phase=phase, recency=now_ts(), team_index=self.cfg.team_ids().index(team),
                             change=rec.get("change"), expects=shown.get("expects"))

    # ---- after a session (spec: Session outcome, Archive gate)

    def after_session(self, cand: sel.Candidate, rec: dict, r: SessionResult, since: str | None = None) -> None:
        hid, team = cand.handover, cand.team
        blocked = None
        if cand.phase in ("apply", "act") and r.outcome not in ("interrupted", "usage_limit"):  # no-loop N3
            blocked = prompts.parse_blocked(r.result_text) or prompts.parse_blocked(r.assistant_text)
            if blocked and self.phase_complete(cand, rec, r, since or r.started):
                blocked = None  # a completed phase is handled as before, whatever its last line says
            if blocked:
                self.log.write("blocked_on_owner", team=team, handover=hid, session=r.session_id, phase=cand.phase,
                               outcome=r.outcome, reason=blocked)
                r.outcome = "waiting_for_owner"
                for s in rec["sessions"]:
                    if s.get("id") == r.session_id:
                        s["outcome"] = r.outcome
        if (r.outcome == "waiting_for_owner" and not blocked and denial_only(r) and normal_end(r)
                and self.phase_complete(cand, rec, r, since or r.started)):  # escalate-denial D1
            self.denial_not_escalated(cand, rec, r)
            r.outcome = "finished"
        if r.outcome == "waiting_for_owner":
            questions = [m.get("question") for m in r.markers_of("escalation")]
            reasons = [f"blocked on the owner: {blocked}"] if blocked else []
            reasons += [f"asked: {json.dumps(q, ensure_ascii=False)[:300]}" for q in questions]
            reasons += [f"permission denied: {d.get('tool_name')}" for d in r.denials]
            self.escalate(hid, team, "; ".join(reasons) or "waiting for the owner", session=r.session_id,
                          phase=cand.phase, question=questions[0] if len(questions) == 1 else (questions or None),
                          result_tail=tail(r))
            return
        if r.outcome == "usage_limit" or self.state.blocked(hid):
            return
        if cand.phase == "propose":
            change = self.session_change(team, hid, r)
            if change:
                rec["change"] = change
                rec["phase"] = "propose"
            else:  # no change to apply: the handover stays new and is proposed again (design P1)
                self.log.write("propose_without_change", team=team, handover=hid, outcome=r.outcome,
                               session=r.session_id)
                self.problem(f"{team} {hid}: propose created no OpenSpec change; the next session is propose again")
        elif cand.phase == "apply":
            rec["phase"] = "apply"
        elif cand.phase == "act":
            rec["phase"] = "act"
        self.hub_phase(hid, rec, since or r.started)
        progress = bool(r.progress_sources)
        if cand.phase == "archive":
            progress = r.outcome == "finished" and self.change_archived(team, rec)
            if progress or (r.outcome == "finished" and not rec.get("change")):
                rec["phase"] = "archived"
                progress = True
        if r.outcome == "interrupted":  # resumed whatever it did; the counter stays (sleep-aware D4)
            if rec.get("phase") == "archived":
                rec.pop("resume_after_timeout", None)
            else:
                rec["resume_after_timeout"] = {"session": r.session_id, "team": team, "phase": cand.phase,
                                               "reason": r.interrupt_cause, "duration_s": r.duration_s}
            return
        if r.timeout_reason and progress:  # continue it in its own context next time (design T4)
            rec["resume_after_timeout"] = {"session": r.session_id, "team": team, "phase": cand.phase,
                                           "reason": r.timeout_reason, "duration_s": r.duration_s,
                                           **({"limit_reason": r.limit_reason} if r.limit_reason else {})}
        else:
            rec.pop("resume_after_timeout", None)
        if progress:
            rec["no_progress"] = 0
        else:
            rec["no_progress"] = rec.get("no_progress", 0) + 1
            notes = r.progress_ignored == "change_notes"
            self.log.write("no_progress", team=team, handover=hid, count=rec["no_progress"],
                           timeout_reason=r.timeout_reason, **({"ignored": "change_notes"} if notes else {}))
            self.problem(f"{team} {hid}: no progress in this session "
                         f"({rec['no_progress']} of {self.cfg.no_progress_limit} before the item stalls)"
                         + (" (commits changed only the change's own files)" if notes else ""))
            if rec["no_progress"] >= self.cfg.no_progress_limit:
                self.escalate(hid, team, f"stalled: {rec['no_progress']} sessions without progress", stalled=True,
                              session=r.session_id, phase=cand.phase, result_tail=tail(r))

    def session_change(self, team: str, handover: str, r: SessionResult) -> str | None:
        """The change a propose session named or created."""
        return (prompts.parse_change(r.result_text) or prompts.parse_change(r.assistant_text)
                or find_change(self.cfg.team(team).repo, handover))

    def change_archived(self, team: str, rec: dict) -> bool:
        """The item's change is known and its directory is gone from `team`'s repository."""
        change = rec.get("change")
        return bool(change) and not (self.cfg.team(team).repo / "openspec" / "changes" / change).is_dir()

    def phase_complete(self, cand: sel.Candidate, rec: dict, r: SessionResult, since: str) -> bool:
        """The phase's own completion signal since `since` (escalate-denial D2): propose, a change; apply or act,
        the worker's `done` / `decline` / `respond` (no-loop N3: answered); review, a close or a return to the worker;
        archive, the change archived."""
        if cand.phase == "propose":
            return bool(self.session_change(cand.team, cand.handover, r))
        if cand.phase == "archive":
            return self.change_archived(cand.team, rec)
        try:
            show = self.hub.show(cand.handover)
        except HoError as exc:
            self.problem(f"ho show {cand.handover} failed: {exc}")
            return False
        worker = rec.get("team")
        for e in show.get("events", []):
            if e.get("at", "") <= since:
                continue
            if (cand.phase in ("apply", "act") and e.get("team") == worker
                    and e.get("action") in ("done", "decline", "respond")):
                return True
            if cand.phase == "review" and (e.get("action") == "close" or (
                    e.get("team") == cand.team and e.get("action") == "return" and e.get("target") == worker)):
                return True
        return False

    def denial_not_escalated(self, cand: sel.Candidate, rec: dict, r: SessionResult) -> None:
        """Log and print a denial in a completed phase; keep it for the item's next review and the goal report
        (escalate-denial D3–D5)."""
        denials = [denial_entry(d, cand.phase, r.session_id) for d in r.denials]
        self.log.write("denial_not_escalated", team=cand.team, handover=cand.handover, phase=cand.phase,
                       session=r.session_id, denials=denials)
        tools = ", ".join(dict.fromkeys(str(d["tool"]) for d in denials))
        noun = "denial" if len(denials) == 1 else "denials"
        self.problem(f"{cand.team} {cand.handover}: phase completed despite the permission {noun} ({tools}); "
                     "not escalated")
        if cand.phase in ("propose", "apply", "act"):  # a review or archive has no later reviewer
            rec.setdefault("unescalated_denials", []).extend(denials)
        if self.goal:
            self.goal.unescalated_denials += [{"handover": cand.handover, "team": cand.team, **d} for d in denials]
            self.goal_save()

    def work_prompt(self, cand: sel.Candidate, rec: dict, goal: str | None) -> str:
        """The phase prompt; a review prompt names the worker's denials that were not escalated, then drops them
        (escalate-denial D3)."""
        if cand.phase == "review":
            return prompts.phase_prompt(cand, goal, denials=rec.pop("unescalated_denials", None))
        return prompts.phase_prompt(cand, goal)

    def hub_phase(self, handover: str, rec: dict, since: str) -> None:
        """Move the record's phase on the worker's `done` / `decline` or a return to the worker since `since`."""
        try:
            show = self.hub.show(handover)
        except HoError as exc:
            self.problem(f"ho show {handover} failed: {exc}")
            return
        worker = rec.get("team")
        for e in show.get("events", []):
            if e.get("at", "") <= since or e.get("action") == "seen":
                continue
            if e.get("team") == worker and e.get("action") == "done":
                rec["phase"] = "done"
            elif e.get("team") == worker and e.get("action") == "decline":
                rec["phase"] = "declined"
            elif e.get("action") == "return" and e.get("target") == worker:
                rec["phase"] = "apply"

    def made_progress(self, team: str, handover: str, since: str, base: dict | None = None, phase: str | None = None,
                      ignored: list[str] | None = None) -> list[str]:
        """Progress sources since the item's work began (spec: Session outcome; design T3): `hub` (activity of
        `team` on the handover or a new handover from it), `commits` (new commits on any branch of its repository
        since the snapshot `base`), `tasks` (more checked tasks in the change's tasks.md than in `base`).
        In apply and act with a known change, commits count only if they change a file outside the change's own
        directory (no-loop N2); otherwise `"change_notes"` is added to `ignored`."""
        sources = []
        try:
            show = self.hub.show(handover)
        except HoError as exc:
            self.problem(f"ho show {handover} failed: {exc}")
            show = None
        if show is not None:
            new = [e for e in show.get("events", []) if e.get("at", "") > since and e.get("action") != "seen"]
            try:
                sent = [] if any(e.get("team") == team for e in new) else self.hub.sent_by(team)
            except HoError:
                sent = []
            if any(e.get("team") == team for e in new) or any(h.get("created", "") > since for h in sent):
                sources.append("hub")
        if base:  # missing for items started before the snapshot existed: hub-only progress
            repo = self.cfg.team(team).repo
            if base.get("heads") is not None and new_commits(repo, base["heads"]):
                change = base.get("change")
                if (phase in ("apply", "act") and change
                        and not commits_outside(repo, base["heads"], f"openspec/changes/{change}/")):
                    if ignored is not None:
                        ignored.append("change_notes")
                else:
                    sources.append("commits")
            if base.get("change") and base.get("tasks") is not None:
                if (checked_tasks(repo, base["change"]) or 0) > base["tasks"]:
                    sources.append("tasks")
        return sources

    # ---- product triage (design D10)

    def triage(self, cand: sel.Candidate, asked: SessionResult, since: str | None = None) -> SessionResult | None:
        tri = self.cfg.triage
        hid, team = cand.handover, cand.team
        rec = self.state.ensure(hid, team)
        question = asked.markers_of("question")[-1].get("question")
        owner = dict(session=asked.session_id, phase=cand.phase, question=question, result_tail=tail(asked))
        rec["triage_count"] = rec.get("triage_count", 0) + 1
        if rec["triage_count"] > tri.max_per_handover:
            self.escalate(hid, team, f"more than {tri.max_per_handover} product triages for this handover", **owner)
            return None
        consult = self.session(tri.team, prompts.consult_prompt(question, team, hid, rec.get("change"),
                                                                self.goal_for(tri.team)),
                               "consult", hid, tools=CONSULT_TOOLS, json_schema=prompts.VERDICT_SCHEMA,
                               title=rec.get("title") or cand.title)
        if consult.outcome == "interrupted":  # the asking session is resumed and asks again (sleep-aware D4)
            rec["triage_count"] -= 1
            asked.outcome, asked.interrupt_cause = "interrupted", consult.interrupt_cause
            self.log.write("triage", team=team, handover=hid, session=asked.session_id,
                           consult_session=consult.session_id, outcome=consult.outcome, verdict=None,
                           question=question, duration_s=consult.duration_s)
            return None
        verdict = parse_verdict(consult)
        self.log.write("triage", team=team, handover=hid, session=asked.session_id,
                       consult_session=consult.session_id, outcome=consult.outcome, verdict=verdict,
                       question=question, duration_s=consult.duration_s)
        self.problem(f"{team} {hid}: question went to product triage, "
                     + (f"verdict {verdict['verdict']}" if verdict else f"no valid verdict ({consult.outcome})"))
        if consult.outcome != "finished" or verdict is None:
            self.escalate(hid, team, f"product triage failed ({consult.outcome}, verdict {verdict!r}); "
                                     f"question: {json.dumps(question, ensure_ascii=False)[:300]}", **owner)
            return None
        if verdict["verdict"] == "owner":
            self.escalate(hid, team, f"product team asks for the owner: {verdict['reason']}; "
                                     f"question: {json.dumps(question, ensure_ascii=False)[:300]}", **owner)
            return None
        message = prompts.resume_message(verdict, question, self.cfg.default_answer)
        return self.session(team, message, cand.phase, hid, resume=asked.session_id, since=since or asked.started,
                            title=rec.get("title") or cand.title, step="triage answer")

    # ---- limit check at the maximum duration (check-session-at-time-limit)

    def limit_watch(self, team: str, handover: str, title: str | None, since: str | None, base: dict | None):
        """Runner callbacks for a work session's limit checks (design D1, D5); (None, None) when checks are off."""
        check_team = self.product_team()
        if check_team is None or self.cfg.limit_checks <= 0:
            return None, None
        used, aborted = [0], threading.Event()

        def on_deadline(r: SessionResult, elapsed: float) -> float | None:
            if used[0] >= self.cfg.limit_checks:  # extensions used up: ended at its deadline without a check
                return None
            rec = self.state.get(handover)
            progress = self.made_progress(team, handover, since or r.started,
                                          base if since is None else base_of(rec, since) if rec else None)
            verdict = self.limit_check(check_team, r, elapsed, progress, used[0], title, aborted)
            if verdict is None:
                return None
            if verdict["verdict"] == "progressing":
                used[0] += 1
                return self.cfg.limit_check_minutes * 60
            r.limit_reason = verdict["reason"]
            return None

        def on_abort() -> None:  # the session ended while its check runs
            aborted.set()
            if self.check_runner is not None:
                self.check_runner.kill()
        return on_deadline, on_abort

    def limit_check(self, check_team: str, r: SessionResult, elapsed: float, progress: list[str], used: int,
                    title: str | None, aborted: threading.Event) -> dict | None:
        """One read-only consultation of the product team on a session at its deadline, run in the runner's check
        thread (design D3–D6). Returns the verdict, or None when there is no valid one or the session ended first."""
        what = f"{r.team} {r.handover}"
        self.log.write("limit_check_start", team=r.team, check_team=check_team, handover=r.handover,
                       session=r.session_id, elapsed_s=round(elapsed), checks_used=used)
        self.problem(f"{what}: time limit after {duration_text(elapsed)}, asking {check_team} whether it is hung")
        digest = prompts.session_digest(r, self.get_runner().clock(), progress)
        runner = self.get_check_runner()
        if aborted.is_set():
            return None
        for line in start_lines(check_team, "limit_check", r.handover, title, None):
            self.out(line)
        if self.goal:  # every session counts in a goal run; saved by the main thread after the work session
            self.goal.sessions += 1
        c = runner.run(check_team, prompts.limit_check_prompt(digest, self.goal.text if self.goal else None),
                       phase="limit_check", handover=r.handover, tools=CONSULT_TOOLS, json_schema=prompts.LIMIT_SCHEMA,
                       timeout_s=self.cfg.limit_check_minutes * 60)
        ignored = aborted.is_set()
        verdict = None if ignored or c.outcome != "finished" else parse_limit_verdict(c)
        extension = (self.cfg.limit_check_minutes if verdict and verdict["verdict"] == "progressing" else None)
        self.log.write("limit_check", team=r.team, check_team=check_team, handover=r.handover, session=r.session_id,
                       check_session=c.session_id, outcome=c.outcome, verdict=verdict and verdict["verdict"],
                       reason=verdict and verdict["reason"], extension_min=extension, duration_s=c.duration_s,
                       ignored=ignored, stream=c.stream_path)
        head = f"{stamp()}  {check_team} {sym('·')} {STEP_KIND['limit_check']} {sym('→')} "
        if ignored:
            self.out(head + f"ignored, the session ended first ({duration_text(c.duration_s)})")
        elif verdict is None:
            self.out(head + f"{c.outcome} ({duration_text(c.duration_s)})")
            self.problem(f"{what}: the limit check gave no valid verdict ({c.outcome}"
                         + (f": {error_cause(c)}" if c.outcome == "error" else "") + "); ending the session")
        else:
            self.out(head + verdict["verdict"] + (f", +{extension:g} min" if extension else "")
                     + f" ({duration_text(c.duration_s)})")
            self.out(f"    {short_title(verdict['reason'], LINE_WIDTH - 4)}")
        return verdict

    # ---- idle ask (design D8)

    def product_team(self) -> str | None:
        """The team asked for work: the triage team, else the first product team."""
        return self.cfg.triage.team if self.cfg.triage else next(
            (t.id for t in self.cfg.teams if t.kind == "product"), None)

    def idle_ask(self) -> bool:
        team = self.product_team()
        if team is None:
            return False
        latest = self.hub_latest()
        previous = self.state.meta.get("last_idle_ask", "")
        if latest and latest <= previous:
            return False
        self.state.meta["last_idle_ask"] = latest or now_ts()
        self.state.save()
        self.log.write("idle_ask", team=team)
        r = self.session(team, prompts.IDLE_PROMPT, "idle", None, json_schema=prompts.IDLE_SCHEMA)
        if r.outcome == "interrupted":  # asked again when due (sleep-aware D6)
            self.state.meta["last_idle_ask"] = previous
            self.state.save()
            return True
        verdict = parse_idle_verdict(r)
        if verdict is None:
            self.log.write("idle_verdict_invalid", team=team, session=r.session_id, outcome=r.outcome,
                           structured=r.structured, result=r.result_text[-1000:])
            self.problem(f"the idle ask of {team} returned no valid verdict ({r.outcome})")
        else:
            self.log.write("idle_verdict", team=team, session=r.session_id, **verdict)
            if verdict["verdict"] == "none" and verdict["waiting_for_owner"]:
                n = len(verdict["waiting_for_owner"])
                self.send_to_owner(team, f"{team}: {n} backlog item{'s' if n > 1 else ''} wait for the owner",
                                   prompts.idle_escalation_body(team, verdict), None, "idle: none")
        # the escalation handover above is hub activity too: no new idle ask until something else happens
        self.state.meta["last_idle_ask"] = max(self.hub_latest(), self.state.meta["last_idle_ask"])
        self.state.save()
        return True

    def hub_latest(self) -> str:
        times = []
        for t in self.cfg.teams:
            times += [h.get("last_activity", "") for h in self.hub.sent_by(t.id)]
        return max(times, default="")

    # ---- handovers to a team the dispatcher does not run (unconfigured-team-escalation)

    def scan_sent(self) -> tuple[dict[str, list[dict]], set[str]]:
        """Every configured team's sent handovers, read once per loop iteration for the unconfigured-team check and
        the hold (wait-for-handover-result design H2); teams whose `ho list` failed are returned apart."""
        sent, failed = {}, set()
        for t in self.cfg.teams:
            try:
                sent[t.id] = self.hub.sent_by(t.id)
            except HoError as exc:
                self.problem(f"ho list --from {t.id} failed: {exc}")
                failed.add(t.id)
        return sent, failed

    def unconfigured_waits(self, scan=None) -> list[dict] | None:
        """Open handovers from a configured team to a hub team that is neither configured nor the owner, whose
        recipient has not finished; None when `ho list` fails, so the check is skipped this time (design U1)."""
        sent, failed = scan or self.scan_sent()
        if failed:
            return None
        configured = set(self.cfg.team_ids())
        waits = []
        for t in self.cfg.teams:
            for h in sent.get(t.id, []):
                if h.get("status") != "open":
                    continue
                for team in h.get("to") or []:
                    state = (h.get("recipients") or {}).get(team, "pending")
                    if team in configured or team == self.cfg.owner_team or sel.part_finished(h.get("expects"), state):
                        continue
                    waits.append({"handover": h["id"], "title": h.get("title") or "", "sender": t.id, "team": team,
                                  "state": state, "refs": h.get("refs") or []})
        return waits

    def waiting_item(self, w: dict) -> str | None:
        """The sender's item the waiting handover references, if it can still be escalated (design U3)."""
        return next((ref for ref in w["refs"] if (self.state.get(ref) or {}).get("team") == w["sender"]
                     and not self.state.blocked(ref)), None)

    def escalate_unconfigured(self, scan=None) -> None:
        """Escalate each new wait once; forget waits that ended (design U2–U5)."""
        waits = self.unconfigured_waits(scan)
        if waits is None:
            return
        known = self.state.meta.get("unconfigured") or {}
        current = {w["handover"] for w in waits}
        changed = [hid for hid in known if hid not in current]
        for hid in changed:
            del known[hid]
        for w in waits:
            if w["handover"] in known:  # one escalation per handover, also for a second missing recipient
                continue
            config = str(self.cfg.path)
            reason, title = prompts.unconfigured_reason(w, config), prompts.unconfigured_title(w)
            item = self.waiting_item(w)
            if item:
                last = (self.state.get(item)["sessions"] or [{}])[-1]
                body = prompts.unconfigured_body(w, config=config, item=item, session=last.get("id"),
                                                 repo=str(self.cfg.team(w["sender"]).repo))
                self.escalate(item, w["sender"], reason, session=last.get("id"), phase=last.get("phase"),
                              title=title, body=body)
                sent = (self.state.get(item).get("escalation") or {}).get("handover")
            else:
                self.problem(reason)
                body = prompts.unconfigured_body(w, config=config, item=None, session=None,
                                                 repo=str(self.cfg.team(w["sender"]).repo))
                sent = self.send_to_owner(w["sender"], title, body, w["handover"], reason)
            known[w["handover"]] = {"team": w["team"], "sender": w["sender"], "item": item, "escalation": sent,
                                    "at": now_ts()}
            self.log.write("unconfigured_team", handover=w["handover"], sender=w["sender"], team=w["team"],
                           state=w["state"], item=item, escalation=sent)
            changed.append(w["handover"])
            if sent:  # the escalation handover is no new work: no idle ask because of it (as in idle_ask)
                try:
                    self.state.meta["last_idle_ask"] = max(self.hub_latest(), self.state.meta.get("last_idle_ask", ""))
                except HoError as exc:
                    self.problem(f"ho list failed: {exc}")
        if known:
            self.state.meta["unconfigured"] = known
        else:
            self.state.meta.pop("unconfigured", None)
        if changed:
            self.state.save()

    # ---- waiting for a handover's result (wait-for-handover-result)

    def holds(self, scan) -> dict[str, list[dict]]:
        """Items held now: from the scan, and for a team whose `ho list` failed, the holds stored in its records,
        so a failing call neither releases nor creates a hold (design H2, H3)."""
        sent, failed = scan
        held = sel.held_items(sent, self.state.records, self.state.escalation_links())
        for hid, rec in self.state.records.items():
            if rec.get("team") in failed and rec.get("waiting_for"):
                held[hid] = rec["waiting_for"]
        return held

    def update_holds(self, scan) -> dict[str, list[dict]]:
        """Keep `waiting_for` in the records; one console line when a hold starts or ends (design H5)."""
        held, changed = self.holds(scan), False
        for hid, rec in self.state.records.items():
            old = rec.get("waiting_for") or []
            new = [{k: w[k] for k in ("handover", "team", "state")} for w in held.get(hid, [])]
            if new == old:
                continue
            changed, team = True, rec.get("team")
            if new:
                rec["waiting_for"] = new
                self.log.write("waiting_for_handover", handover=hid, team=team, waits=new)
                if not old:
                    self.out(f"{stamp()}  {hid} ({team}) waits for {waits_text(new)}; "
                             f"not selected until {'it is' if len(new) == 1 else 'they are'} finished")
            else:
                del rec["waiting_for"]
                ended = list(dict.fromkeys(w["handover"] for w in old))
                self.log.write("wait_ended", handover=hid, team=team, handovers=ended)
                self.out(f"{stamp()}  {hid} ({team}): {', '.join(ended)} finished; selectable again")
        if changed:
            self.state.save()
        return held

    # ---- goal run (goal-run)

    def start_goal(self, goal: GoalRun) -> None:
        info = self.previous_goal(goal)
        self.carry_verdict(goal, info)
        carried = self.carry_guidance(goal, info)
        self.goal = goal
        self.log.write("goal_start", path=str(goal.path), goal=goal.text, hash=goal.hash,
                       max_sessions=goal.max_sessions, max_hours=goal.max_hours, budget=self.budget,
                       until=local_iso(self.until), keep_awake=self.keep_awake.text)
        self.out(f"Goal run: {goal.path} (at most {goal.max_sessions} sessions, {goal.max_hours:g} h)")
        if carried:
            self.log.write("goal_guidance_carried", path=str(goal.path), recovered=carried,
                           added_chars=len(goal.text) - len(goal.given_text))
            self.out("    the goal changed since the product team last saw it; the first session is a goal check")
        self.goal_save()

    def previous_goal(self, goal: GoalRun) -> dict | None:
        """goal.json of the previous goal run when it used the same goal file, None otherwise."""
        try:
            info = json.loads((self.cfg.run_dir / "goal.json").read_text(encoding="utf-8"))
            same = Path(info["path"]).resolve() == goal.path.resolve()
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return info if same else None

    @staticmethod
    def carry_verdict(goal: GoalRun, info: dict | None) -> None:
        """Keep the last goal-check verdict of an earlier run on the same goal file, so a short run still reports
        what is done and left (marked as earlier in the report)."""
        if info and isinstance(info.get("last_verdict"), dict):
            goal.last_verdict, goal.verdict_carried = info["last_verdict"], True
            goal.verdict_at = info.get("last_verdict_at")

    @staticmethod
    def carry_guidance(goal: GoalRun, info: dict | None) -> str | None:
        """Guidance the product team has not received in an earlier run on the same goal file makes the first
        session a goal check (carry-goal-guidance C3). Returns how the seen text was found when it differs:
        `stored`, `hash` (an older goal.json: cut trailing notes until the stored hash matches) or `unknown`."""
        found = Dispatcher.unseen_guidance(goal, info)
        if found is None:
            return None
        goal.given_text, goal.pending = found[0], True
        return found[1]

    @staticmethod
    def unseen_guidance(goal: GoalRun, info: dict | None) -> tuple[str, str] | None:
        """(text the product team saw, how it was found) when the goal file has guidance it has not received;
        changes nothing (used by `plan`, predict-next-steps D5)."""
        if not info:
            return None
        given = info.get("given_text")
        if isinstance(given, str):
            how = "stored"
        else:
            pending, stored = bool(info.get("guidance_pending")), info.get("hash")
            if not pending and stored == goal.hash:
                return None
            given, how, cut = "", "unknown", goal.text
            while not pending and (i := cut.rfind("\n\n## Note ")) >= 0:
                cut = cut[:i]
                if hashlib.sha256(cut.encode("utf-8")).hexdigest() == stored:
                    given, how = cut, "hash"
                    break
        return None if given == goal.text else (given, how)

    def goal_save(self) -> None:
        write_json_atomic(self.cfg.run_dir / "goal.json", self.goal.to_json())

    def goal_for(self, team: str) -> str | None:
        """The goal text for a product-team prompt during a goal run, None otherwise (design G5)."""
        if self.goal is None or team != self.product_team():
            return None
        if self.goal.given_text != self.goal.text:  # saved now: a cut session still counts as received (C2)
            self.goal.given_text = self.goal.text
            self.goal_save()
        return self.goal.text

    def goal_refresh(self) -> None:
        """Re-read the goal file between sessions; a change makes the next session a goal check (design G6)."""
        g = self.goal
        text = read_goal(g.path)
        if text is None:
            if not g.unreadable:
                g.unreadable = True
                self.log.write("goal_unreadable", path=str(g.path))
                self.problem(f"the goal file {g.path} is unreadable or empty; keeping the last good text")
            return
        g.unreadable = False
        if text == g.text:
            return
        size = len(text) - len(g.text)
        g.text = text
        g.pending = text != g.given_text
        self.log.write("goal_updated", path=str(g.path), hash=g.hash, diff_chars=size)
        self.out(f"{stamp()}  the goal file changed ({size:+d} characters)"
                 + ("; the next session is a goal check" if g.pending else ""))
        self.goal_save()

    def goal_limit(self) -> str | None:
        """A reached safety limit, checked between sessions; usage waits count toward the duration, sleeps of the
        computer do not (design G7, sleep-aware D7)."""
        g = self.goal
        if g.sessions >= g.max_sessions:
            return f"the maximum of {g.max_sessions} sessions is reached"
        if g.awake_s() >= g.max_hours * 3600:
            return f"the maximum duration of {g.max_hours:g} h is reached"
        return None

    def goal_check(self) -> tuple[str, str] | None:
        """One product session instead of the idle ask (design G3, G4). Returns (end status, reason) or None."""
        g, team = self.goal, self.product_team()
        notice = prompts.guidance_notice(g.given_text, g.text) if g.pending else ""
        g.pending = False
        before = self.hub_latest()
        self.log.write("goal_check", team=team, guidance_changed=bool(notice))
        if notice:
            self.out("    the owner's guidance changed: goal check first")
        r = self.session(team, prompts.goal_check_prompt(self.goal_for(team), notice), "goal", None,
                         json_schema=prompts.GOAL_SCHEMA)
        if r.outcome in ("usage_limit", "interrupted"):  # no verdict to judge: the check runs again
            return None
        verdict = parse_goal_verdict(r)
        if verdict is None:
            self.log.write("goal_verdict_invalid", team=team, session=r.session_id, outcome=r.outcome,
                           structured=r.structured, result=r.result_text[-1000:])
            self.problem(f"the goal check of {team} returned no valid verdict ({r.outcome})")
        else:
            g.last_verdict, g.verdict_at, g.verdict_carried = verdict, now_ts(), False
            self.log.write("goal_verdict", team=team, session=r.session_id, **verdict)
            self.out(f"    goal: {verdict['status']} - {verdict['reason']}")
            if verdict["status"] in ("complete", "blocked"):
                return verdict["status"], verdict["reason"]
        moved = verdict is not None and self.hub_latest() > before
        g.empty_continues = 0 if moved else g.empty_continues + 1
        self.goal_save()
        if g.empty_continues >= GOAL_STALL_LIMIT:
            return "stalled", f"{g.empty_continues} goal checks in a row brought no new handover or hub activity"
        return None

    def end_goal(self, status: str, reason: str) -> int:
        """`goal_result` log record, Markdown report in the run directory, console report (design G7)."""
        g = self.goal
        v = g.last_verdict or {}
        g.status = status
        g.result = {"status": status, "reason": reason, "done": v.get("done", []), "left": v.get("left", []),
                    "escalated": self.goal_blocked_items(), "unescalated_denials": g.unescalated_denials,
                    "handovers": self.goal_handovers(),
                    "sessions": g.sessions, "duration_s": round(g.awake_s()), "slept_s": round(g.slept_s)}
        self.log.write("goal_result", **g.result)
        self.goal_save()
        report = goal_report(g, self.product_team())
        path = self.cfg.run_dir / f"goal-report-{dt.datetime.now():%Y%m%d-%H%M%S}.md"
        path.write_text(report, encoding="utf-8")
        self.out("\n" + report)
        self.out(f"Report saved: {path}")
        return GOAL_EXIT[status]

    def goal_blocked_items(self) -> list[dict]:
        out = []
        for hid, rec in self.state.records.items():
            if self.state.blocked(hid):
                out.append({"handover": hid, "team": rec["team"], "reason": rec.get("reason"),
                            "kind": "stalled" if rec["flags"].get("stalled") else "escalated",
                            "session": rec["sessions"][-1]["id"] if rec["sessions"] else None,
                            "repo": str(self.cfg.team(rec["team"]).repo) if rec["team"] in self.cfg.team_ids() else None})
        return out

    def goal_handovers(self) -> list[dict]:
        """Handovers the product team sent during the run."""
        try:
            sent = self.hub.sent_by(self.product_team())
        except HoError:
            return []
        return [{"id": h.get("id"), "title": h.get("title"), "status": h.get("status")}
                for h in sent if h.get("created", "") >= self.goal.started_ts]

    # ---- usage guard (usage-limit-guard)

    def usage_watch(self, team: str, handover: str | None):
        """Runner callback: announce once per session per window when a reading reaches the threshold (design D6)."""
        crossed = set()

        def on_usage(window: str, utilization: float, resets_at: float | None) -> None:
            budget = self.budget.get(window)
            if window in crossed or percent(utilization) < (budget or self.cfg.usage_pause_percent):
                return
            crossed.add(window)
            self.log.write("usage_threshold", team=team, handover=handover, window=window, utilization=utilization,
                           resets_at=resets_at, budget=budget)
            if budget:
                self.problem(f"usage: {window} {percent_text(utilization)} - run budget reached - "
                             f"the run ends after this session (budget {budget}%)")
                return
            self.problem(f"usage: {window} {percent_text(utilization)} - no new step after this session"
                     + (f" (resets {clock(resets_at)})" if resets_at else ""))
        return on_usage

    def record_usage(self, r: SessionResult) -> None:
        """Merge the session's reading into the stored one, per window (design D2)."""
        if not r.usage:
            return
        usage = self.state.meta.setdefault("usage", {})
        seen = now_ts()
        for window, reading in r.usage.items():
            usage[window] = {**reading, "seen": seen}
        self.state.save()

    def usage_hold(self) -> None:
        """Hold new steps while a window that has not reset is at or above the threshold (design D3, D5)."""
        held = held_windows(self.state.meta.get("usage"), self.cfg.usage_pause_percent, time.time(), set(self.budget))
        if held:
            window, w = max(held, key=lambda x: x[1]["resets_at"])
            self.wait_for_reset(window, w, "threshold")

    def start_budget(self) -> None:
        """Console lines and log records for the run's usage budget, with a warning above the threshold (design D5)."""
        if not self.budget:
            return
        threshold = self.cfg.usage_pause_percent
        live = dict(live_windows(self.state.meta.get("usage"), time.time()))
        self.log.write("usage_budget", budget=self.budget, threshold=threshold)
        for window, budget in self.budget.items():
            now = percent_text(live[window].get("utilization")) if window in live else "no current reading"
            self.out(f"Usage budget for this run: {window} up to {budget}% (now {now})")
            if budget > threshold:
                self.log.write("usage_budget_warning", window=window, budget=budget, threshold=threshold)
                self.problem(f"warning: {window} budget {budget}% is above the global usage_pause_percent {threshold}%; "
                             "this run may use the window past it")

    def budget_end(self) -> int | None:
        """End the run when a budgeted window reached its budget (design D4); None to go on."""
        found = budget_reached(self.state.meta.get("usage"), self.budget, time.time())
        if not found:
            return None
        window, w = found
        budget = self.budget[window]
        self.log.write("usage_budget_reached", window=window, utilization=w.get("utilization"), budget=budget,
                       status=w.get("status"))
        reason = f"usage budget reached: {window} {percent_text(w.get('utilization'))} (budget {budget}%)"
        self.out(f"{stamp()}  U{reason[1:]}; ending the run.")
        return self.end_goal("limit", reason) if self.goal else 0

    # ---- end time (run-until-time)

    def start_until(self) -> None:
        """Console line and log record for the run's end time (design D5)."""
        if self.until is None:
            return
        self.log.write("run_until", until=local_iso(self.until))
        self.out(f"Run ends at {until_text(self.until)}")

    def until_end(self) -> int | None:
        """End the run once its wall-clock end time is reached, sleep counted (design D2, D3); None to go on."""
        if self.until is None or time.time() < self.until:
            return None
        at = dt.datetime.fromtimestamp(self.until)
        self.log.write("run_until_reached", until=local_iso(self.until))
        self.out(f"{stamp()}  End time {at:%H:%M} reached; ending the run.")
        return self.end_goal("limit", f"end time {at:%Y-%m-%d %H:%M} reached") if self.goal else 0

    # ---- keeping the computer awake (keep-computer-awake)

    def start_keep_awake(self) -> None:
        """Console line and log record for the setting, then the keeper thread; nothing for `off` (design D7)."""
        s = self.keep_awake
        if s.mode == "off":
            return
        moment = s.until or s.given
        self.log.write("keep_awake_setting", mode=s.mode, text=s.text,
                       until=moment.isoformat(timespec="minutes") if moment else None,
                       start=f"{s.start:%H:%M}" if s.start else None, end=f"{s.end:%H:%M}" if s.end else None)
        if os.name != "nt":
            self.problem("keeping the computer awake is not available on this system")
            return
        self.out(f"Keep awake: {keep_awake_text(s, until=self.until)}")
        self.keeper = Keeper(s)
        self.keeper.start()

    def stop_keep_awake(self) -> None:
        if self.keeper is not None:
            self.keeper.stop()
            self.keeper = None

    def keep_awake_changes(self) -> None:
        """Print and log what the keeper thread changed, each with its own time (design D6)."""
        if self.keeper is None:
            return
        while not self.keeper.changes.empty():
            at, on = self.keeper.changes.get()
            self.log.write("keep_awake", on=on, at=local_iso(at))
            self.out(f"{stamp(at)}  " + ("Keep awake started." if on else "Keep awake ended; the computer may sleep."))

    def nap(self, seconds: float) -> None:
        """A wait without a session that never runs past the end time (design D4)."""
        if self.until is not None:
            seconds = max(0.0, min(seconds, self.until - time.time()))
        time.sleep(seconds)

    def wait_for_reset(self, window: str, w: dict, cause: str) -> None:
        """Start (or keep) a wait until `window` resets; logged once per wait, printed once per process."""
        meta = self.state.meta
        until = w["resets_at"] + USAGE_MARGIN_S
        old_until = meta.get("backoff_until", 0)
        meta["backoff_until"] = max(old_until, until)
        minutes = max(0, math.ceil((meta["backoff_until"] - time.time()) / 60))
        changed = meta["backoff_until"] != old_until
        old = meta.get("usage_wait") or {}
        if (old.get("until"), old.get("window")) != (until, window):
            meta["usage_wait"] = {"until": until, "window": window, "utilization": w.get("utilization"), "cause": cause}
            self.log.write("usage_wait", window=window, utilization=w.get("utilization"), resets_at=w["resets_at"],
                           until=meta["backoff_until"], minutes=minutes, cause=cause)
            changed = True
        if changed:
            self.state.save()
        if self._usage_announced != (window, until):
            self._usage_announced = (window, until)
            self._usage_note = time.time()
            if cause == "threshold":
                self.problem(f"Usage: {window} {percent_text(w.get('utilization'))} used, resets {clock(w['resets_at'])} "
                             f"(local), waiting {minutes} min.")
            else:
                self.problem(f"Usage limit hit: {window} resets {clock(w['resets_at'])} (local), waiting {minutes} min.")

    def usage_reminder(self, wait: float) -> None:
        w = self.state.meta.get("usage_wait")
        if w and time.time() - self._usage_note >= USAGE_REMINDER_S:
            self._usage_note = time.time()
            self.problem(f"still waiting for the {w['window']} usage window to reset "
                         f"(resumes {clock(time.time() + wait)}, {math.ceil(wait / 60)} min left).")

    def usage_resumed(self) -> None:
        w = self.state.meta.pop("usage_wait", None)
        if w:
            self._usage_announced = None
            self.log.write("usage_resume", window=w.get("window"), cause=w.get("cause"))
            self.out(f"{stamp()}  Usage window {w.get('window')} has reset; resuming.")
            self.state.save()

    # ---- loop (design D7)

    def loop(self, once: bool = False) -> int:
        paused = False
        while True:
            self.slept()  # between sessions and after every wait: poll, PAUSE, usage wait, back-off
            if (self.cfg.run_dir / "STOP").exists():
                self.log.write("stop")
                self.out("STOP file found; exiting.")
                return self.end_goal("stopped", "STOP file found") if self.goal else 0
            if self.goal and (limit := self.goal_limit()):
                return self.end_goal("limit", limit)
            if (code := self.until_end()) is not None:  # wall clock: also passed while the computer slept
                return code
            if (code := self.budget_end()) is not None:  # before the hold: a budgeted window ends the run, never waits
                return code
            if (self.cfg.run_dir / "PAUSE").exists():
                if not paused:
                    self.log.write("pause")
                    self.out("Paused (PAUSE file); waiting.")
                    paused = True
                self.nap(5)
                continue
            paused = False
            self.usage_hold()  # one check before every new step: owner-answer resume, work item, idle ask
            wait = self.state.meta.get("backoff_until", 0) - time.time()
            if wait > 0:
                if once:
                    for line in usage_report(self):
                        self.out(line)
                    self.out(f"In usage-limit back-off for {int(wait // 60)} more min; nothing run.")
                    return 0
                self.usage_reminder(wait)
                self.nap(min(wait, 60))
                continue
            self.usage_resumed()
            scan = self.scan_sent()  # once per iteration (wait-for-handover-result design H2)
            self.escalate_unconfigured(scan)  # before owner answers and selection: the waiting item is held (U1)
            held = self.update_holds(scan)
            if self.goal:
                self.goal_refresh()
            guidance = bool(self.goal and self.goal.pending)  # changed guidance: a goal check before anything else
            answers = [] if guidance else self.owner_answers()  # an owner's answer goes before new candidates
            cand = None if answers or guidance else sel.pick(self.plan(held))
            if not answers and cand is None:
                if self.goal:  # a goal run never polls an idle hub (goal-run design G3)
                    end = self.goal_check()
                    if end:
                        return self.end_goal(*end)
                    if self.stop_after_session:
                        return self.end_goal("stopped", "interrupted (Ctrl+C)")
                    continue
                if self.cfg.idle_ask and self.idle_ask():
                    if once or self.stop_after_session:
                        return 0
                    continue
                if once:
                    self.out("Nothing to do.")
                    return 0
                self.nap(self.cfg.poll_seconds)
                continue
            try:
                if answers:
                    self.resume_with_answer(*answers[0])
                else:
                    self.run_candidate(cand)
            except HooksNotLoaded as exc:
                self.log.write("hooks_not_loaded", detail=str(exc))
                self.problem(f"hooks not loaded: {exc}. Stopping: check the hook setup (radark/README.md).")
                return 3
            if self.goal and self.stop_after_session:
                return self.end_goal("stopped", "interrupted (Ctrl+C)")
            if once or self.stop_after_session:
                return 0


def waits_text(waits: list[dict]) -> str:
    return ", ".join(f"{w['handover']} ({w['team']}, {w['state']})" for w in waits)


def percent(utilization: float | None) -> float:
    return round((utilization or 0) * 100, 6)  # 0.57 * 100 is 56.99999999999999


def percent_text(utilization: float | None) -> str:
    return f"{round(percent(utilization))}%"


def clock(ts: float) -> str:
    """Local time; the date is added when it is not today (the seven-day window)."""
    t = dt.datetime.fromtimestamp(ts)
    return t.strftime("%H:%M") if t.date() == dt.date.today() else t.strftime("%Y-%m-%d %H:%M")


# -- console lines (console-progress) ---------------------------------------------------

LINE_WIDTH = 110  # a start line stays within about this many characters (design D1)
MIN_TITLE = 30  # less room than this on the start line: the title goes to a second line
ASCII = {"·": "-", "→": "->", "…": "...", "–": "-"}  # fallbacks for a console that is not UTF-8 (design: Risks)
STEP_KIND = {"goal": "goal check", "idle": "idle ask", "consult": "triage consultation",
             "limit_check": "limit check"}
TIME_LIMIT = {"idle_timeout": "idle time limit", "max_time": "time limit"}
INTERRUPT_CAUSE = {"sleep": "computer slept", "owner": "owner", "dispatcher_stopped": "dispatcher stopped"}


def utf8_console() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "").replace("_", "")
    return enc in ("utf8", "utf8sig")


def sym(char: str) -> str:
    return char if utf8_console() else ASCII[char]


def iso_ts(text: str) -> float:
    """Unix time of a `now_ts()` timestamp (UTC, `...Z`)."""
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def stamp(ts: float | None = None) -> str:
    """Local `HH:MM` for console lines; `DD.MM HH:MM` when it is not today (design D2)."""
    t = dt.datetime.fromtimestamp(time.time() if ts is None else ts)
    return t.strftime("%H:%M") if t.date() == dt.date.today() else t.strftime("%d.%m %H:%M")


def keep_awake_text(s: KeepAwake, now: float | None = None, until: float | None = None) -> str:
    """`whole run`, `until 23:00 today, in 9 h 00 min`, `daily 08:00-23:00 (now: off, from 08:00)` (design D7);
    `whole run (until 12:00 given, the run ends at 12:00)` for a moment covered by the end time `until`
    (keep-awake-covers-until D2)."""
    now = time.time() if now is None else now
    if s.mode == "on" and s.given is not None and until is not None:
        return f"whole run (until {s.text} given, the run ends at {day_clock(until, now)})"
    if s.mode == "until":
        return f"until {until_text(s.until.timestamp(), now)}"
    if s.mode == "range":
        on = wanted(s, dt.datetime.fromtimestamp(now))
        return f"daily {s.text} " + ("(now: on)" if on else f"(now: off, from {s.start:%H:%M})")
    return "whole run"


def local_iso(ts: float | None) -> str | None:
    return None if ts is None else dt.datetime.fromtimestamp(ts).isoformat(timespec="minutes")


def day_clock(ts: float, now: float) -> str:
    """`12:00`, `12:00 tomorrow` or `12:00 on 2026-11-20` (keep-awake-covers-until D2)."""
    at, today = dt.datetime.fromtimestamp(ts), dt.datetime.fromtimestamp(now).date()
    day = {today: "", today + dt.timedelta(days=1): " tomorrow"}.get(at.date(), f" on {at:%Y-%m-%d}")
    return f"{at:%H:%M}{day}"


def until_text(ts: float, now: float | None = None) -> str:
    """`07:00 tomorrow (2026-10-30), in 8 h 50 min` (run-until-time D5)."""
    now = time.time() if now is None else now
    at, today = dt.datetime.fromtimestamp(ts), dt.datetime.fromtimestamp(now).date()
    day = {today: "today", today + dt.timedelta(days=1): f"tomorrow ({at:%Y-%m-%d})"}.get(at.date(),
                                                                                         f"on {at:%Y-%m-%d}")
    return f"{at:%H:%M} {day}, in {duration_text(max(0.0, ts - now))}"


def duration_text(seconds: float) -> str:
    """`45 s` under 2 min, `36 min`, `2 h 05 min` from 2 h (design D3)."""
    if seconds < 120:
        return f"{round(seconds)} s"
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 120 else f"{minutes} min"


def short_title(title: str, width: int) -> str:
    title = " ".join((title or "").split())
    if len(title) <= width:
        return title
    dots = sym("…")
    return title[:max(width - len(dots), 1)].rstrip() + dots


def console_print(text: str = "", stream=None) -> None:
    """print() that never raises on the console's encoding: unencodable characters are replaced."""
    stream = stream or sys.stdout
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        stream.write((text + "\n").encode(enc, "replace").decode(enc))
    stream.flush()


class Tee:
    """A console stream that also appends every write to a UTF-8 file, so a watcher sees what the window shows."""

    def __init__(self, stream, file):
        self.stream, self.file = stream, file

    def write(self, text: str) -> int:
        try:
            self.stream.write(text)
        except UnicodeEncodeError:
            enc = getattr(self.stream, "encoding", None) or "ascii"
            self.stream.write(text.encode(enc, "replace").decode(enc))
        try:
            self.file.write(text)
            self.file.flush()
        except (OSError, ValueError):
            pass  # the console stays the primary output
        return len(text)

    def flush(self) -> None:
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)  # encoding, isatty, reconfigure, ...


def tee_console(run_dir: Path, argv: list[str]) -> None:
    """Copy stdout and stderr of this process to `<run_dir>/console.log` (appended, one header per start)."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        file = open(run_dir / "console.log", "a", encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"{stamp()}  ! console.log not written: {exc}", file=sys.stderr)
        return
    file.write(f"\n==== {dt.datetime.now():%Y-%m-%d %H:%M:%S}  PID {os.getpid()}  {' '.join(argv)}\n")
    file.flush()
    sys.stdout, sys.stderr = Tee(sys.stdout, file), Tee(sys.stderr, file)


def quick_edit_off(kernel32=None) -> bool:
    """Turn off QuickEdit of this process's console window: a click in it starts a selection, which blocks every
    console write - and with it the whole run - until the selection ends. False when stdin is not a console."""
    if os.name != "nt" and kernel32 is None:
        return False
    kernel32 = kernel32 or ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, (mode.value & ~0x40) | 0x80))  # -QUICK_EDIT, +EXTENDED_FLAGS


def step_parts(team: str, phase: str, step: str | None) -> list[str]:
    return [team, STEP_KIND.get(phase, phase)] + ([step] if step else [])


def start_lines(team: str, phase: str, handover: str | None, title: str | None, step: str | None) -> list[str]:
    """`HH:MM  team · phase · HO-ID  "title"`; the title moves to a second line when the head is long (design D1)."""
    parts = step_parts(team, phase, step) + ([handover] if handover else [])
    head = f"{stamp()}  " + f" {sym('·')} ".join(parts)
    if not title:
        return [head]
    room = LINE_WIDTH - len(head) - 4
    if room >= MIN_TITLE:
        return [f'{head}  "{short_title(title, room)}"']
    return [head, f'       "{short_title(title, LINE_WIDTH - 9)}"']


def end_line(team: str, phase: str, step: str | None, r: SessionResult, handover: str | None = None) -> str:
    cause = (TIME_LIMIT.get(r.timeout_reason, r.timeout_reason) if r.timeout_reason
             else INTERRUPT_CAUSE.get(r.interrupt_cause, r.interrupt_cause) if r.interrupt_cause else None)
    outcome = r.outcome + (f", {cause}" if cause else "")
    return (f"{stamp()}  " + f" {sym('·')} ".join(step_parts(team, phase, step) + ([handover] if handover else []))
            + f" {sym('→')} {outcome} ({duration_text(r.duration_s)})")


def error_cause(r: SessionResult) -> str:
    """Why a session ended with outcome `error`, for its `!` line."""
    if r.timeout_reason:
        return f"{TIME_LIMIT.get(r.timeout_reason, r.timeout_reason)} after {duration_text(r.duration_s)}"
    if r.killed:
        return "ended with Ctrl+C"
    if not r.hooks_loaded and r.exit_code is not None:
        return "hooks not loaded"
    if not r.has_result:
        return f"no result (exit code {r.exit_code})"
    return f"exit code {r.exit_code}"


def question_text(question, size: int = 80) -> str:
    """The question(s) of an AskUserQuestion marker, as one short quoted line."""
    if isinstance(question, list) and all(isinstance(q, dict) and "question" in q for q in question):
        text = " / ".join(str(q["question"]) for q in question)
    elif isinstance(question, str):
        text = question
    else:
        text = json.dumps(question, ensure_ascii=False)
    return f'"{short_title(text, max(size, 20))}"'


def live_windows(usage: dict | None, now: float) -> list[tuple[str, dict]]:
    """Stored windows whose reset is still ahead; a window past its reset counts as unused (spec: Usage reading)."""
    return [(name, w) for name, w in (usage or {}).items()
            if isinstance(w, dict) and isinstance(w.get("resets_at"), (int, float)) and w["resets_at"] > now]


def held_windows(usage: dict | None, threshold: int, now: float, exempt: set[str] = frozenset()
                 ) -> list[tuple[str, dict]]:
    """Windows that hold new steps: at or above the threshold, or reported `rejected` (design D3, D5); windows with a
    run budget are `exempt` (run-usage-budget D3)."""
    return [(name, w) for name, w in live_windows(usage, now)
            if name not in exempt and (percent(w.get("utilization")) >= threshold or w.get("status") == "rejected")]


def budget_reached(usage: dict | None, budget: dict[str, int], now: float) -> tuple[str, dict] | None:
    """The first budgeted window, in `budget` order, used at or above its budget or reported `rejected` (D2)."""
    live = dict(live_windows(usage, now))
    for name, limit in budget.items():
        w = live.get(name)
        if w and (percent(w.get("utilization")) >= limit or w.get("status") == "rejected"):
            return name, w
    return None


def exhausted_window(usage: dict | None, now: float) -> tuple[str, dict] | None:
    """After a usage-limit hit: the window not `allowed`, else the most used one (design D4)."""
    live = live_windows(usage, now)
    if not live:
        return None
    blocked = [x for x in live if x[1].get("status") not in (None, "allowed")]
    return blocked[0] if blocked else max(live, key=lambda x: x[1].get("utilization") or 0)


def usage_report(d: Dispatcher) -> list[str]:
    """The stored reading per window and the guard's verdict, for dry-run and a held --once (design D6)."""
    usage, now = d.state.meta.get("usage") or {}, time.time()
    lines = []
    for name, w in usage.items():
        reset = w.get("resets_at")
        if isinstance(reset, (int, float)) and reset <= now:
            lines.append(f"Usage: {name} has reset at {clock(reset)} (counts as unused)")
            continue
        status = w.get("status")
        lines.append(f"Usage: {name} {percent_text(w.get('utilization'))} "
                     + (f"resets {clock(reset)}" if isinstance(reset, (int, float)) else "reset time unknown")
                     + (f", status {status}" if status not in (None, "allowed") else ""))
    if not usage:
        lines.append("Usage: no reading yet")
    held = held_windows(usage, d.cfg.usage_pause_percent, now, set(d.budget))
    backoff = d.state.meta.get("backoff_until", 0)
    if held:
        window, w = max(held, key=lambda x: x[1]["resets_at"])
        lines.append(f"guard: holding until {clock(w['resets_at'] + USAGE_MARGIN_S)} "
                     f"({window} {percent_text(w.get('utilization'))}, threshold {d.cfg.usage_pause_percent}%)")
    elif backoff > now:
        lines.append(f"guard: below the threshold, but in usage-limit back-off until {clock(backoff)}")
    else:
        lines.append(f"guard: next step would start (threshold {d.cfg.usage_pause_percent}%)")
    if d.budget:
        reached = budget_reached(usage, d.budget, now)
        if reached:
            window, w = reached
            lines.append(f"budget: {window} {percent_text(w.get('utilization'))} >= {d.budget[window]}% "
                         "- the run would end without starting a step")
        else:
            live = dict(live_windows(usage, now))
            below = ", ".join(f"{name} {percent_text(live[name].get('utilization') if name in live else 0)} < {b}%"
                              for name, b in d.budget.items())
            lines.append(f"budget: below ({below})")
    return lines


def tail(r: SessionResult, size: int = 1500) -> str:
    return (r.result_text or r.assistant_text or "")[-size:]


def parse_verdict(r: SessionResult) -> dict | None:
    data = r.structured
    if data is None:
        try:
            data = json.loads(r.result_text)
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict) or data.get("verdict") not in ("technical", "product", "owner"):
        return None
    if not isinstance(data.get("answer", ""), str) or not isinstance(data.get("reason"), str):
        return None
    if data["verdict"] == "product" and not data.get("answer", "").strip():
        return None
    return {"verdict": data["verdict"], "answer": data.get("answer", ""), "reason": data["reason"]}


def parse_idle_verdict(r: SessionResult) -> dict | None:
    data = r.structured
    if data is None:
        try:
            data = json.loads(r.result_text)
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict) or data.get("verdict") not in ("handed_over", "none"):
        return None
    waiting = data.get("waiting_for_owner", [])
    if not isinstance(data.get("reason"), str) or not isinstance(waiting, list):
        return None
    if not all(isinstance(w, dict) and isinstance(w.get("item"), str) and isinstance(w.get("why"), str)
               for w in waiting):
        return None
    return {"verdict": data["verdict"], "reason": data["reason"],
            "waiting_for_owner": [{"item": w["item"], "why": w["why"]} for w in waiting]}


def parse_limit_verdict(r: SessionResult) -> dict | None:
    data = r.structured
    if data is None:
        try:
            data = json.loads(r.result_text)
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict) or data.get("verdict") not in ("progressing", "hung"):
        return None
    if not isinstance(data.get("reason"), str) or not data["reason"].strip():
        return None
    return {"verdict": data["verdict"], "reason": data["reason"].strip()}


def parse_goal_verdict(r: SessionResult) -> dict | None:
    data = r.structured
    if data is None:
        try:
            data = json.loads(r.result_text)
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict) or data.get("status") not in ("complete", "continue", "blocked"):
        return None
    if not isinstance(data.get("reason"), str):
        return None
    lists = {k: data.get(k, []) for k in ("done", "left")}
    if not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in lists.values()):
        return None
    return {"status": data["status"], "reason": data["reason"], **lists}


def goal_report(g: GoalRun, team: str | None) -> str:
    """The end-of-run report (design G7): printed and saved as goal-report-<time>.md."""
    res = g.result
    lines = [f"# Goal run: {res['status']}", "",
             f"- Goal file: {g.path}",
             f"- Reason: {res['reason']}",
             f"- Sessions: {res['sessions']} (limit {g.max_sessions}); duration {duration_text(res['duration_s'])} "
             f"(limit {g.max_hours:g} h)" + (f", slept {duration_text(res['slept_s'])}" if res.get("slept_s") else ""),
             f"- Started: {g.started_ts}"]
    if g.steps:
        lines += ["", "## Sessions in this run", ""] + [f"- {x}" for x in g.steps]
    if g.verdict_carried:
        when = f" of {stamp(iso_ts(g.verdict_at))}" if g.verdict_at else ""
        lines += ["", f"No goal check in this run; Done and Left are from the last goal check{when} (an earlier run) "
                      "and do not include the sessions above."]
    for title, key in (("Done", "done"), ("Left or blocked", "left")):
        lines += ["", f"## {title}", ""] + ([f"- {x}" for x in res[key]] or ["- (none reported)"])
    if res["escalated"]:
        lines += ["", "## Escalated or stalled items", ""]
        for e in res["escalated"]:
            resume = f"; `claude --resume {e['session']}` in `{e['repo']}`" if e.get("session") and e.get("repo") else ""
            lines.append(f"- {e['handover']} ({e['team']}, {e['kind']}): {e.get('reason')}{resume}")
    if res.get("unescalated_denials"):
        lines += ["", "## Permission denials not escalated", ""]
        lines += [f"- {x['handover']} ({x['team']}, {x['phase']}): {x['tool']} `{x['input']}`"
                  for x in res["unescalated_denials"]]
    if res["handovers"]:
        lines += ["", f"## Handovers sent by {team} during the run", ""]
        lines += [f"- {h['id']} ({h.get('status')}): {h.get('title')}" for h in res["handovers"]]
    return "\n".join(lines) + "\n"


def wait_for_key() -> None:
    """Keep a console window open after a goal run (design G8); nothing happens without a console."""
    if sys.stdin is None or not sys.stdin.isatty():
        return
    print("Press any key to exit", flush=True)
    try:
        import msvcrt
        msvcrt.getch()
    except ImportError:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    except KeyboardInterrupt:
        pass


def add_note(cfg: config_mod.Config, text: str) -> int:
    """Append a timestamped note to the goal file of the current goal run; takes no lock (design G6)."""
    try:
        info = json.loads((cfg.run_dir / "goal.json").read_text(encoding="utf-8"))
        path = Path(info["path"])
    except (OSError, ValueError, KeyError, TypeError):
        print(f"No goal run found in {cfg.run_dir} (goal.json); start one with `run --goal <file>`.", file=sys.stderr)
        return 1
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n\n## Note {dt.datetime.now():%Y-%m-%d %H:%M}\n{text}\n")
    except OSError as exc:
        print(f"Could not append to {path}: {exc}", file=sys.stderr)
        return 1
    print(f"Note appended to {path}." + ("" if info.get("status") == "running" else
                                          f" The goal run has ended ({info.get('status')}); the next run on "
                                          "this file starts with a goal check that passes the note to the "
                                          "product team."))
    return 0


def denial_only(r: SessionResult) -> bool:
    """Permission denials are the session's only reason to wait for the owner (escalate-denial D1)."""
    return bool(r.denials) and not r.markers_of("escalation") and not r.markers_of("question")


def normal_end(r: SessionResult) -> bool:
    return (r.exit_code == 0 and r.has_result and not r.is_error and r.hooks_loaded and not r.timed_out
            and not r.killed and not r.interrupt_cause)


def denial_entry(d, phase: str, session: str) -> dict:
    """A denial as kept for the reviewer and the goal report: tool and command (or input), shortened (design D3)."""
    d = d if isinstance(d, dict) else {"tool_name": str(d)}
    tool_input = d.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    text = command if isinstance(command, str) else json.dumps(tool_input, ensure_ascii=False)
    return {"tool": d.get("tool_name"), "input": short_title(text, 200), "phase": phase, "session": session,
            "at": now_ts()}


def resume_failed(r: SessionResult) -> bool:
    """A resumed session that produced nothing: the next session starts fresh with the phase prompt."""
    return r.outcome == "error" and not r.has_result and not r.killed and not r.timed_out


def git_out(repo: Path, *args: str) -> str | None:
    """Read-only git query in a team repository; None when it is not a git repository or git fails."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def branch_heads(repo: Path) -> list[str] | None:
    out = git_out(repo, "for-each-ref", "--format=%(objectname)", "refs/heads")
    return None if out is None else sorted(set(out.split()))


def new_commits(repo: Path, old_heads: list[str]) -> bool:
    """A branch head points to a commit not reachable from the old heads (a reset or deletion is not progress)."""
    heads = branch_heads(repo)
    changed = [h for h in heads or [] if h not in old_heads]
    if not changed:
        return False
    out = git_out(repo, "rev-list", "--max-count=1", *changed, "--not", *old_heads, "--")
    return bool(out and out.strip())


def commits_outside(repo: Path, old_heads: list[str], prefix: str) -> bool:
    """The commits not reachable from the old heads change at least one path outside `prefix` (no-loop N2).
    If git cannot tell, they count (as before)."""
    changed = [h for h in branch_heads(repo) or [] if h not in old_heads]
    if not changed:
        return False
    out = git_out(repo, "-c", "core.quotepath=off", "log", "--name-only", "--format=", *changed,
                  "--not", *old_heads, "--")
    if out is None:
        return True
    return any(p.strip() and not p.strip().startswith(prefix) for p in out.splitlines())


CHECKED_RE = re.compile(r"^\s*[-*] \[[xX]\]", re.M)


def checked_tasks(repo: Path, change: str) -> int | None:
    path = Path(repo) / "openspec" / "changes" / change / "tasks.md"
    try:
        return len(CHECKED_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return None


def snapshot(repo: Path, change: str | None) -> dict:
    """Taken when an item's work begins; made_progress compares against it (design T3)."""
    return {"heads": branch_heads(repo), "change": change,
            "tasks": checked_tasks(repo, change) if change else None}


def base_of(rec: dict, since: str) -> dict | None:
    """The snapshot of the session that began the item's work at `since`."""
    return next((s.get("base") for s in rec["sessions"] if s.get("started") == since and s.get("base")), None)


def find_change(repo: Path, handover: str) -> str | None:
    """Fallback: newest change directory whose files mention the handover ID."""
    changes = Path(repo) / "openspec" / "changes"
    if not changes.is_dir():
        return None
    found = []
    for d in changes.iterdir():
        if not d.is_dir() or d.name == "archive":
            continue
        for f in d.rglob("*.md"):
            try:
                if handover in f.read_text(encoding="utf-8", errors="replace"):
                    found.append((d.stat().st_mtime, d.name))
                    break
            except OSError:
                continue
    return max(found)[1] if found else None


# -- CLI --------------------------------------------------------------------------------

def dry_run(d: Dispatcher) -> int:
    for line in usage_report(d):
        print(line)
    if d.until is not None:
        print(f"Would end: {until_text(d.until)}")
    if d.keep_awake.mode != "off":
        print(f"Would keep awake: {keep_awake_text(d.keep_awake, until=d.until)}")
    owner = d.cfg.owner_team
    answers = d.owner_answers()
    answered = {hid for hid, *_ in answers}
    for hid, link, event, _ in answers:
        print(f"Owner {'declined' if event['action'] == 'decline' else 'answered'} {link['handover']} for {hid}: "
              f"would clear {hid} and resume session {link.get('session') or '-'} of {link['team']} "
              f"(phase {link.get('phase')}) with: {(event.get('body') or '').strip()[:200]}")
    for hid, rec in d.state.records.items():
        link = d.state.open_escalation(hid)
        if link and hid not in answered:
            print(f"Waiting for {owner}: escalation handover {link['handover']} for {hid} ({link['team']})")
        elif not link and d.state.blocked(hid):
            print(f"Escalated without an escalation handover (manual path, `escalations` / `clear`): {hid}")
    print(f"An item that escalates or stalls would send an escalation handover to `{owner}` "
          "(ho new --expects response --auto-close --tag escalation --ref <item>), then ho sync.")
    escalating = set()  # items the next loop would escalate before selection
    known = d.state.meta.get("unconfigured") or {}
    scan = d.scan_sent()
    for w in d.unconfigured_waits(scan) or []:
        item = d.waiting_item(w)
        if w["handover"] in known:
            action = "already escalated" + (f" ({known[w['handover']]['escalation']})"
                                            if known[w["handover"]].get("escalation") else "")
        elif item:
            action = f"would escalate {item}"
            escalating.add(item)
        else:
            action = f"would send a standalone escalation handover to `{owner}`"
        print(f"Waits for a team not set up: {w['handover']} from {w['sender']} to {w['team']} ({w['state']}); "
              f"{action}")
    held = d.holds(scan)
    for hid, waits in held.items():
        print(f"Held (waits for a handover's result): {hid} ({d.state.get(hid).get('team')}) waits for "
              f"{waits_text(waits)}")
    if answers:
        print("\nOwner answers are handled before any new candidate.")
    cands = [c for c in d.plan(held) if c.handover not in escalating]
    if d.goal:
        print(f"Goal run: {d.goal.path} (at most {d.goal.max_sessions} sessions, {d.goal.max_hours:g} h); "
              f"the goal text is added to every prompt of {d.product_team()}.")
    if not cands:
        print("Nothing to do: no selectable candidate.")
        if d.goal:
            print(f"Goal run: would run a goal check in {d.product_team()} instead of polling.\nPrompt:\n"
                  + prompts.goal_check_prompt(d.goal.text))
            return 0
        if d.cfg.idle_ask:
            print("Idle ask is enabled: the product team would be asked for the next backlog task "
                  f"if the hub has new activity; a verdict `none` with items waiting for the owner would send "
                  f"one escalation handover to `{owner}`.")
        return 0
    print("Candidates (newest first):")
    for c in cands:
        print(f"  {c.recency}  {c.team:<20} {c.kind:<7} {c.phase:<8} {c.handover}  {c.title}")
    c = cands[0]
    print(f"\nWould start: {c.team} in {d.cfg.team(c.team).repo}, phase {c.phase}, handover {c.handover}"
          + (f", resuming session {c.resume_session}" if c.resume_session else "")
          + (f" after its {c.timeout_resume.get('reason')}" if c.timeout_resume else ""))
    lock = (d.cfg.team(c.team).repo / ".git" / "index.lock").is_file()
    goal = d.goal_for(c.team)
    print("Prompt:\n" + (prompts.timeout_resume_message(c, c.timeout_resume, lock, goal) if c.timeout_resume
                         else prompts.phase_prompt(c, goal)))
    return 0


PLAN_ASSUMES = ("Assumes: reviews accept the work; no question escalates or goes to triage; no permission is denied; "
                "checks pass; sessions send no new handovers; a goal check hands over work not known yet.")


def plan_line(n: int, team: str, phase: str, handover: str | None, title: str) -> str:
    head = f"  {n}. {team:<20} {phase:<8} {handover or ''}".rstrip()
    return head + (f"  {short_title(title, max(LINE_WIDTH - len(head) - 2, MIN_TITLE))}" if title else "")


def plan_run(d: Dispatcher, steps: int, goal: GoalRun | None, max_sessions: int | None) -> int:
    """The next steps if every step succeeds (predict-next-steps); reads the hub, writes nothing (design D5, D7)."""
    for line in usage_report(d):
        print(line)
    print("Plan (if every step succeeds):")
    first = None
    if goal and Dispatcher.unseen_guidance(goal, d.previous_goal(goal)):
        first = (d.product_team(), "goal check", None, "",
                 "the product team has not received the goal's latest guidance; the next steps depend on its verdict")
    elif answers := d.owner_answers():
        hid, link, event, _ = answers[0]
        first = (link["team"], link.get("phase") or "apply", hid, (d.state.get(hid) or {}).get("title") or "",
                 f"it resumes with the owner's {'decline' if event['action'] == 'decline' else 'answer'} on "
                 f"{link['handover']}; the next steps depend on that session")
    if first:
        print(plan_line(1, *first[:4]))
        print(f"Stops: {first[4]}.")
        print(PLAN_ASSUMES)
        return 0
    scan = d.scan_sent()
    known = d.state.meta.get("unconfigured") or {}
    escalating = {item for w in d.unconfigured_waits(scan) or [] if w["handover"] not in known
                  if (item := d.waiting_item(w))}  # escalated by the next loop before selection, as in dry_run
    teams, inboxes, shows, held = d.snapshot(d.holds(scan))
    f = forecast.simulate(teams, inboxes, shows, d.state.records, held, steps, now_ts(), goal=goal is not None,
                          idle_ask=d.cfg.idle_ask, product=d.product_team(), skip=escalating)
    limit = (max_sessions or d.cfg.goal_max_sessions) if goal else None
    for n, s in enumerate(f.steps, 1):
        phase = s.phase + (" (resume)" if s.resume else "")
        print(plan_line(n, s.team, phase, s.handover, s.title))
        if n == limit and n < len(f.steps):
            print(f"  --max-sessions {limit} ends the run here")
    for item in escalating:
        print(f"Not predicted: {item} would be escalated first (it waits for a team that is not set up).")
    for note in f.notes:
        print(f"Note: {note}.")
    if f.stop:
        print(f"Stops: {f.stop}.")
    print(PLAN_ASSUMES)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m radark", description=__doc__)
    p.add_argument("--config", default="harness.toml")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the loop")
    r.add_argument("--once", action="store_true", help="run one session, then exit")
    r.add_argument("--dry-run", action="store_true", help="print the plan; start nothing")
    r.add_argument("--goal", metavar="FILE", help="goal run: work the scope in FILE to an end, then report")
    r.add_argument("--max-sessions", type=int, help="goal run: session limit (default [goal] max_sessions)")
    r.add_argument("--max-hours", type=float, help="goal run: duration limit (default [goal] max_hours)")
    r.add_argument("--no-wait", action="store_true", help="goal run: exit without 'Press any key to exit'")
    sub.add_parser("once", help="same as run --once")
    dr = sub.add_parser("dry-run", help="same as run --dry-run")
    for parser in (r, dr):
        for window, flag in BUDGET_OPTIONS.items():
            parser.add_argument(flag, type=int, metavar="PCT",
                                help=f"this run only: end the run once the {window} window is used PCT %% or more "
                                     "(1-100; replaces [loop] usage_pause_percent for that window)")
        parser.add_argument("--until", metavar="WHEN",
                            help="this run only: start no new step from WHEN on, HH:MM (next such time) or "
                                 "YYYY-MM-DD HH:MM, local wall-clock time (sleep of the computer counts)")
        parser.add_argument("--keep-awake", nargs="?", const="on", metavar="WHEN",
                            help="this run only: keep the computer from sleeping on its own: off, on (the bare flag), "
                                 "until HH:MM / YYYY-MM-DD HH:MM, or daily HH:MM-HH:MM (replaces [loop] keep_awake)")
    pl = sub.add_parser("plan", help="print the next steps if every step succeeds; start nothing")
    pl.add_argument("--steps", type=int, default=5, metavar="N", help="number of steps to predict (default 5)")
    pl.add_argument("--goal", metavar="FILE", help="predict a goal run on FILE (goal check instead of idle)")
    pl.add_argument("--max-sessions", type=int, metavar="N", help="goal run: mark where this session limit ends the run "
                                                      "(default [goal] max_sessions)")
    sub.add_parser("escalations", help="list escalated and stalled items")
    c = sub.add_parser("clear", help="make an escalated or stalled item selectable again")
    c.add_argument("id")
    k = sub.add_parser("keep", help="continue a handover's next phases in its previous session")
    k.add_argument("id")
    k.add_argument("--team", help="working team, if the handover has no record yet")
    k.add_argument("--off", action="store_true", help="go back to a fresh session per phase")
    n = sub.add_parser("note", help="append a timestamped note to the goal file of the running goal run")
    n.add_argument("text")
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # titles and agent text may not fit the console code page
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    budget = {}
    for window, flag in BUDGET_OPTIONS.items():
        value = getattr(args, flag[2:].replace("-", "_"), None)
        if value is None:
            continue
        if not 1 <= value <= 100:
            print(f"{flag} must be an integer from 1 to 100, not {value}.", file=sys.stderr)
            return 2
        budget[window] = value
    until = None
    if getattr(args, "until", None) is not None:
        at = parse_until(args.until, dt.datetime.now())
        if at is None:
            print(f"--until must be HH:MM or YYYY-MM-DD HH:MM (local time) in the future, not '{args.until}'.",
                  file=sys.stderr)
            return 2
        until = at.timestamp()
    keep_awake = None
    if getattr(args, "keep_awake", None) is not None:
        keep_awake = parse_keep_awake(args.keep_awake, dt.datetime.now())
        if keep_awake is None:
            print(f"--keep-awake must be {KEEP_AWAKE_FORMS}, not '{args.keep_awake}'.", file=sys.stderr)
            return 2

    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.command == "note":
        return add_note(cfg, args.text)
    if args.command == "once" or (args.command == "run" and not args.dry_run):
        tee_console(cfg.run_dir, sys.argv[1:] if argv is None else argv)
        quick_edit_off()
    d = Dispatcher(cfg)
    d.budget = budget
    d.until = until
    if keep_awake is not None:
        d.keep_awake = keep_awake
    d.keep_awake = cover_end_time(d.keep_awake, until)  # a moment at or after the end time: the whole run
    goal = None
    if args.command in ("run", "plan") and args.goal:
        goal, error = new_goal(d, args)
        if error:
            print(error, file=sys.stderr)
            return 2

    if args.command == "escalations":
        items = [(hid, r) for hid, r in d.state.records.items()
                 if r["flags"].get("escalated") or r["flags"].get("stalled")]
        for hid, r in items:
            kind = "stalled" if r["flags"].get("stalled") else "escalated"
            last = r["sessions"][-1]["id"] if r["sessions"] else "-"
            print(f"{hid}  {r['team']:<20} {kind:<9} last session {last}\n    {r.get('reason')}")
            link = r.get("escalation")
            if link and not link.get("answered"):
                print(f"    escalation handover {link['handover']} to the owner, sent {link.get('sent')}; "
                      f"resumes session {link.get('session') or '-'}")
        if not items:
            print("No escalated or stalled items.")
        return 0
    if args.command == "clear":
        if not d.state.clear(args.id):
            print(f"No record for {args.id}.", file=sys.stderr)
            return 1
        d.state.save()
        d.log.write("clear", handover=args.id)
        print(f"{args.id} is selectable again.")
        return 0
    if args.command == "keep":
        rec = d.state.get(args.id)
        if rec is None and not args.team:
            print(f"No record for {args.id}; pass --team <id>.", file=sys.stderr)
            return 1
        rec = d.state.ensure(args.id, rec["team"] if rec else args.team)
        rec["flags"]["keep_session"] = not args.off
        d.state.save()
        print(f"{args.id}: {'fresh session per phase' if args.off else 'next phases resume the previous session'}.")
        return 0

    if args.command == "plan":
        if args.steps <= 0:
            print("--steps must be positive.", file=sys.stderr)
            return 2
        if args.max_sessions is not None and not goal:
            print("--max-sessions needs --goal: only a goal run has a session limit.", file=sys.stderr)
            return 2
        try:
            config_mod.check_owner(cfg, d.hub.teams())
            return plan_run(d, args.steps, goal, args.max_sessions)
        except config_mod.ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        except HoError as exc:
            print(f"ho error: {exc}", file=sys.stderr)
            return 1
    dry = args.command == "dry-run" or (args.command == "run" and args.dry_run)
    once = args.command == "once" or (args.command == "run" and args.once)
    print(config_mod.summary(cfg, config_mod.claude_version(cfg)))
    try:
        config_mod.check_owner(cfg, d.hub.teams())
    except config_mod.ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except HoError as exc:
        print(f"ho error: {exc}", file=sys.stderr)
        return 1
    try:
        if dry:
            d.goal = goal
            return dry_run(d)
        lock = Lock(cfg.run_dir / "lock")
        lock.acquire()
        try:
            d.log.write("dispatcher_start", once=once, pid=os.getpid(), goal=str(goal.path) if goal else None)
            d.recover()  # after the lock: the dispatcher that wrote the record is gone
            if goal:
                d.start_goal(goal)
            d.start_budget()
            d.start_until()
            d.start_keep_awake()
            code = d.loop(once=once)
        finally:
            d.stop_keep_awake()
            lock.release()
    except HoError as exc:
        print(f"ho error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted; exiting.")
        return 130
    if goal and not args.no_wait:
        wait_for_key()
    return code


def new_goal(d: Dispatcher, args) -> tuple[GoalRun | None, str | None]:
    """A goal run from `run --goal`, or the reason it is refused before any session (design G1)."""
    path = Path(args.goal).resolve()
    if getattr(args, "once", False):
        return None, "--goal cannot be combined with --once: a goal run ends on its own (see radark/README.md)."
    text = read_goal(path)
    if text is None:
        return None, f"Goal file {path} is missing, unreadable or empty; not starting."
    if d.product_team() is None:
        return None, "A goal run needs a product team ([triage] team or a [[teams]] entry with kind = \"product\")."
    sessions = d.cfg.goal_max_sessions if args.max_sessions is None else args.max_sessions
    hours = d.cfg.goal_max_hours if getattr(args, "max_hours", None) is None else args.max_hours
    if sessions <= 0 or hours <= 0:
        return None, "--max-sessions and --max-hours must be positive."
    return GoalRun(path, text, sessions, hours), None


if __name__ == "__main__":
    sys.exit(main())
