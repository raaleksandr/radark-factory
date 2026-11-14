"""Phase prompts (spec: Phase prompts) and the messages used around product triage."""
from __future__ import annotations

import datetime as dt
import json
import math
import re

from .select import Candidate

STANDING_RULE = (
    "You are run unattended by a dispatcher; no user is available. Never ask the user: when you "
    "would ask, choose the best variant yourself, record the assumption in the change (design or "
    "tasks notes), and continue. Stop only when this phase is complete or blocked by something "
    "outside this repository."
)


def long_wait_rule(idle_minutes: float) -> str:
    """The long-wait rule every session carries in its system prompt (check-long-waits D2, D5): the check interval
    is half the inactivity limit, rounded down to whole minutes, at least 1."""
    interval = max(1, math.floor(idle_minutes / 2))
    return (
        f"Long waits: this session is ended after {idle_minutes:g} minutes without output from you (a running "
        "command does not count as output). Never wait silently on a command or a background task for longer than "
        f"{interval} minutes: run long commands so that you can check them, and check their progress at least once "
        f"every {interval} minutes (its latest output, a progress counter, whether the process is alive). If two "
        "checks in a row show no progress, treat it as hung: stop it, record what was seen, and continue another way "
        "or report it."
    )


def denial_rule(temp_dir: str) -> str:
    """The denial rule every session carries in its system prompt after the long-wait rule (fewer-owner-waits D6)."""
    return (
        "Denied commands: if the permission mode denies a command, do not stop. Do the same another allowed way: "
        f"temporary files go to `{temp_dir}`; to drop an edit, run `git restore -- <file>` naming the files, or "
        "re-write them; stop only processes you started, by their ID (`Stop-Process -Id <pid>`), or run servers as "
        "background tasks and stop them with the task tool. A hook message on a denial names the allowed way. If the "
        "phase cannot be completed without the denied command, end your final message with one line "
        "`BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <what you propose>`."
    )


CHANGE_LINE_RE =re.compile(r"^\s*CHANGE:\s*`?([A-Za-z0-9._-]+)`?\s*$", re.M)
BLOCKED_LINE_RE = re.compile(r"^[ \t]*BLOCKED:[ \t]*owner[ \t]*[—–-][ \t]*(.+?)[ \t]*$", re.M | re.I)

TEAM_DECIDES = (
    "If a decision is needed that your team's instructions (your `CLAUDE.md`, the owner's goal) allow your team to "
    "take, take it: record it in the change (or the handover result) and inform the owner with a non-blocking "
    "handover (`ho new --to <owner team> --expects ack --auto-close`), then continue. Use the BLOCKED line only for "
    "what those instructions reserve for the owner or, where they say nothing, for a decision, money, credentials, a "
    "production step."
)

# apply and act (no-loop N3, N4): how a worker that cannot go on ends, instead of re-checking every session
BLOCKED_NOTE = (
    "If you only wait for another team's result, stop; do not commit or comment just to record that you are still "
    "waiting. "
    # fewer-owner-waits D9: decide what the team's own policy allows, inform the owner without blocking
    + TEAM_DECIDES +
    " If only the owner can unblock you (a decision, money, credentials, a production step), end your final "
    "message with one line `BLOCKED: owner — <what is needed>`."
)

_HUB = "Start and end with `ho sync`. "

# every apply prompt, new or returned (archive-after-close D1, D3): archive runs only after the author closes
APPLY_NO_ARCHIVE = (
    "Do not archive the change and do not sync its specs into the main specs: archive is a separate phase that runs "
    "after the author closes the handover. If the change's tasks list an archive or spec-sync step, leave it "
    "unchecked; the archive phase checks it."
)

# every apply prompt, new or returned (report-local-todo D2, D3): the product team plans only from its own backlog
APPLY_LOCAL_TODO = (
    "If your work added an entry to your repository's own TODO or backlog, or materially changed one (a new item, a "
    "new obstacle, a new estimate, a status change), name each such entry in the `ho done` summary on a line "
    "starting `Local TODO:` (id, title, one line why). If there are none, leave the line out."
)

# review prompt (report-local-todo D4): the product team takes the named entries into its own backlog
REVIEW_LOCAL_TODO = (
    "If a result has a `Local TODO:` line, decide for each entry named there whether it belongs in the product "
    "backlog, record those that do (a new backlog item or a note on an existing one), and say what you decided in "
    "your close or return message. A local TODO entry missing from the product backlog is not a reason to return "
    "the handover: add it yourself."
)


def _change_ref(c: Candidate) -> str:
    if c.change:
        return f"the OpenSpec change `{c.change}`"
    return f"the OpenSpec change in `openspec/changes/` that cites {c.handover} (find it first)"


def _closing(c: Candidate) -> str:
    """How the phase ends; repeated in the message that continues a session cut by a time limit."""
    return {
        "propose": "End your final message with one line `CHANGE: <change-name>` naming the change you created.",
        "apply": f"When the work is finished, report it with `ho done {c.handover} -m \"<summary>\"`.",
        "review": f"If the result is accepted, close it with `ho close {c.handover}`; otherwise return it with "
                  f"`ho return {c.handover} --to <team> -m \"<what to change>\"`.",
        "archive": "Make no hub changes other than `ho sync`.",
        "act": f"Take the expected action ({c.expects or 'see the handover'}) and end with `ho sync`.",
    }[c.phase]


def goal_block(goal: str) -> str:
    """The owner's goal, added to product-team prompts during a goal run (goal-run design G5)."""
    return ("Owner's goal and guidelines for this run (follow them; they override the backlog order):\n\n"
            + _quote(goal))


def _with_rule(text: str, goal: str | None, no_goal: str | None = None) -> str:
    """`no_goal`: the no-goal block (goal-ends-with-run D1), given in place of the goal block in a run without one."""
    block = goal_block(goal) if goal else no_goal
    return text + "\n\n" + (block + "\n\n" if block else "") + STANDING_RULE


# product-team prompts of a run without a goal (goal-ends-with-run D1)
NO_GOAL_NOTICE = (
    "No owner goal is active in this run. Goals of earlier runs have ended and set no order of work; choose the next "
    "task by your team's usual task-choice rule."
)


def _local_time(iso: str | None) -> str | None:
    """`17:00, 2026-11-13` from a local ISO time; None when missing or unreadable."""
    try:
        at = dt.datetime.fromisoformat(iso) if iso else None
    except (TypeError, ValueError):
        return None
    return f"{at:%H:%M, %Y-%m-%d}" if at else None


def ended_goal_notice(path: str, status: str | None, ended: str | None) -> str:
    """The once-only request after a goal run (goal-ends-with-run D2); `ended` is a local ISO time. A goal run still
    recorded as `running` ended without a report and has no end time."""
    if not status or status == "running":
        head = f"The goal run on `{path}` ended without a report (its end time is unknown)."
    else:
        when = _local_time(ended)
        head = f"The goal run on `{path}` ended (`{status}`" + (f", {when}" if when else "") + ")."
    return (head + " If your backlog files still record an order of work set by that goal, remove that order now; "
            "keep its unfinished parts as ordinary backlog items.")


def phase_prompt(c: Candidate, goal: str | None = None, denials: list[dict] | None = None,
                 time_limits: list[dict] | None = None, no_goal: str | None = None) -> str:
    """`denials`: the worker's permission denials that were not escalated, named in a review prompt
    (escalate-denial D3); `time_limits`: the item's sessions wrapped up or cut by a time limit (wrap-up W6.3);
    `no_goal`: the no-goal block of a product-team prompt in a run without a goal (goal-ends-with-run D1)."""
    head = f"Handover {c.handover} (\"{c.title}\"). Phase: {c.phase}.\n\n"
    if c.phase == "propose":
        body = (
            f"{_HUB}Read the handover with `ho show {c.handover} --json`, acknowledge it with "
            f"`ho ack {c.handover}`, and create an OpenSpec change for it (the /opsx:propose workflow) "
            f"that cites {c.handover} in its proposal. Do not implement it in this session. The change's tasks "
            "must not include archiving the change or syncing its specs: archive is a separate phase that runs "
            "after the author closes the handover, so `ho done` is the last step of apply.\n" + _closing(c)
        )
    elif c.phase == "apply":
        ref = _change_ref(c)
        if c.return_comment is not None:
            body = (
                f"{_HUB}The author returned {c.handover} to your team with this comment:\n\n"
                + "\n".join("> " + line for line in (c.return_comment or "(no comment)").splitlines())
                + f"\n\nContinue {ref} according to the return comment (the /opsx:apply workflow). "
                "Do not create a new change and do not archive. "
            )
        else:
            body = f"{_HUB}Implement {ref} for {c.handover} (the /opsx:apply workflow). "
        body += (APPLY_NO_ARCHIVE + " " + _closing(c) + " " + APPLY_LOCAL_TODO + " If you need another team, send your own handover with `ho new` and stop that part. "
                 + BLOCKED_NOTE)
    elif c.phase == "review":
        body = (
            f"{_HUB}Your team sent {c.handover} and every recipient has finished. Read it and the "
            f"results with `ho show {c.handover} --json` and check the result. If it is accepted, "
            f"close it with `ho close {c.handover}`; otherwise return it with "
            f"`ho return {c.handover} --to <team> -m \"<what to change>\"`. " + REVIEW_LOCAL_TODO
        )
        if denials:
            body += (
                "\n\nDuring the worker's sessions these actions were denied by the permission mode and the worker "
                "went on without them:\n" + "\n".join(f"- {d.get('tool')}: `{d.get('input')}`" for d in denials)
                + "\nCheck that nothing the handover asks for was skipped because of them; if something was, "
                "return the handover."
            )
        if time_limits:
            body += "\n\n" + time_limit_note(time_limits)
    elif c.phase == "archive":
        body = (
            f"The author has closed handover {c.handover}. Archive {_change_ref(c)} "
            "(the /opsx:archive workflow). Make no hub changes other than `ho sync`."
        )
    elif c.phase == "act":
        body = (
            f"{_HUB}Act on the handover per the hub guide (AGENTS.md in the hub): read it with "
            f"`ho show {c.handover} --json` and take the expected action ({c.expects or 'see the handover'}). "
            "Routine work needs no OpenSpec change. " + BLOCKED_NOTE
        )
    else:
        raise ValueError(f"unknown phase {c.phase!r}")
    return _with_rule(head + body, goal, no_goal)


def _hours(seconds: float) -> str:
    """`45 min` under 2 h, `6 h`, `2 h 05 min` (wrap-up W6.3)."""
    minutes = round((seconds or 0) / 60)
    if minutes < 120:
        return f"{minutes} min"
    return f"{minutes // 60} h" + (f" {minutes % 60:02d} min" if minutes % 60 else "")


def _extensions(n: int) -> str:
    return f"{n} extension" + ("" if n == 1 else "s")


def time_limit_note(entries: list[dict]) -> str:
    """The review paragraph on the worker's sessions that ran into the time limit (wrap-up W6.3)."""
    items = []
    for e in entries:
        extensions = _extensions(int(e.get("extensions") or 0))
        if e.get("kind") == "wrap_up":
            outcome = e.get("outcome") or "?"
            if e.get("reason"):
                outcome += f", {e['reason']}"
            items.append(f"wrapped up after {_hours(e.get('elapsed_s'))} with {extensions} ({outcome})")
        else:
            items.append(f"cut by {e.get('reason') or 'max_time'} after {_hours(e.get('elapsed_s'))} with {extensions}")
    return (
        f"The worker's sessions on this handover ran into the time limit: {'; '.join(items)}. The task may be too big "
        "for one session: check the result's `Left:` list, and if work is left, return the handover for it or record "
        "it as a follow-up (a new backlog item or handover) and say which in your close or return message."
    )


def wrap_up_message(c: Candidate, minutes: int, extensions: int, grace: float, index_lock: bool = False,
                    goal: str | None = None) -> str:
    """Resumes a work session stopped at its last time limit and asks it to wrap up within `grace` minutes
    (wrap-up W5)."""
    ext = f" and {extensions} limit-check {'extension' if extensions == 1 else 'extensions'}" if extensions > 0 else ""
    text = (
        f"The dispatcher stopped this session: it reached its time limit after {minutes} min{ext}, in the {c.phase} "
        f"phase of handover {c.handover}, and no extension is left. You now have {grace:g} min to wrap up; after that "
        "the session is cut. The step that was running was cut off: the working tree may hold a partial edit, and an "
        "interrupted git command may have left a stale `.git/index.lock`" + (" (one exists now)" if index_lock else "")
        + ". Check `git status` and your last step first: finish the partial step only if it is quick, otherwise undo "
        "it (remove the lock only if no git process is running). Start no new work. Commit what works. Then report "
        "what is done the way this phase reports it, and name what is left so the author can hand it over as a "
        "follow-up: "
    )
    if c.phase == "apply":
        text += (
            "check off the finished tasks in the change's `tasks.md`, write the open ones under a `Left for a "
            f"follow-up` note there, commit, and report with `ho done {c.handover} -m \"<summary>\"` whose summary "
            "starts with `Wrapped up at the time limit.` and has a line `Left: <what is left>`. " + APPLY_NO_ARCHIVE
        )
    else:
        text += "say what is left on a line starting `Left:` in your final message. " + _closing(c)
    return _with_rule(text, goal)


TIMEOUT_LABELS ={"idle_timeout": "the inactivity limit (no output for too long)",
                  "max_time": "the maximum session duration"}


INTERRUPT_LABELS = {
    "sleep": "The computer slept during this session and the session gave no sign of life after the wake, so the "
             "dispatcher stopped it",
    "owner": "The owner stopped the dispatcher, and with it this session",
    "dispatcher_stopped": "The dispatcher stopped while this session ran (its window was closed, or the computer "
                          "restarted)",
}


def timeout_resume_message(c: Candidate, info: dict, index_lock: bool = False, goal: str | None = None) -> str:
    """Resumes a session the dispatcher ended by a time limit after it made progress (design T4), or one that was
    interrupted: the computer slept, the owner ended it, the dispatcher stopped (sleep-aware D5)."""
    reason = info.get("reason") or "max_time"
    minutes = round((info.get("duration_s") or 0) / 60)
    stopped_phase = info.get("phase") or c.phase
    if reason in INTERRUPT_LABELS:
        head = (f"{INTERRUPT_LABELS[reason]}, in the {stopped_phase} phase of handover {c.handover}. Time has passed "
                "and the hub or the repository may have changed meanwhile: check the state first (`ho sync`, "
                f"`ho show {c.handover}`). ")
    else:
        head = (f"The dispatcher stopped this session: it reached {TIMEOUT_LABELS.get(reason, reason)} (`{reason}`) "
                f"after {minutes} min, in the {stopped_phase} phase of handover {c.handover}. ")
        if info.get("limit_reason"):  # check-session-at-time-limit D5
            head += f"The product team judged the session hung: {info['limit_reason'].strip()} "
    text = head + (
        "Your committed work is kept, "
        "but the step that was running was cut off: the working tree may hold a partial edit, and an interrupted "
        "git command may have left a stale `.git/index.lock`" + (" (one exists now)" if index_lock else "") + ". "
        "Check `git status` and your last step first: finish or redo the partial step (remove the lock only if no "
        "git process is running), then continue the phase."
    )
    if reason == "idle_timeout":
        text += " A single step that produces no output for that long is cut again: split long waits into shorter steps."
    if stopped_phase != c.phase:
        return text + f"\n\nThen do the next phase in this session:\n\n{phase_prompt(c, goal)}"
    return text + " " + _closing(c)


def blocked_section(blocked: list[dict]) -> str:
    """Escalated and stalled items named in the idle prompt (goal-ends-with-run D3); empty when there are none."""
    if not blocked:
        return ""
    lines = [f"- {b.get('handover')} (team `{b.get('team')}`, {b.get('kind') or 'escalated'}): "
             + (" ".join(str(b.get("reason") or "").split()) or "no reason recorded") for b in blocked]
    return (
        "These items are escalated to the owner or stalled now:\n" + "\n".join(lines) + "\n"
        "A blocked item is no reason to leave other ready work waiting: choose ready work that does not depend on "
        "these items. Answer `none` only when every ready item waits for the owner or depends on a blocked item.\n\n"
    )


PARALLEL_NOTE = (  # parallel-sessions D7: work prompts when more than one session may run
    "Another team may be working on this computer at the same time. Stop only processes you started yourself, by "
    "their ID (never by name or image, never \"all node\" or \"any playwright\"); use no fixed shared ports or paths "
    "outside your repository and your temp directory; expect runs to be slower than usual."
)


TEST_SLOT_NOTE = (  # machine-wide-instances D8: work prompts when more than one session can run on the computer
    "Several sessions may run on this computer now. Run a full test suite as `radark-test-slot <command>` (for "
    "example `radark-test-slot python -m pytest`); it waits while another session's full test run is in progress, "
    "then runs your command and returns its exit code. Single quick tests do not need it."
)


def work_in_progress(running: list[dict] | None) -> str:
    """The work-in-progress section of the idle ask and the goal check (parallel-sessions D3); empty when nothing
    else runs. running: [{team, handover, title, phase}]."""
    if not running:
        return ""
    items = "; ".join(f"{w.get('team')} {w.get('handover') or '-'}"
                      + (f" \"{' '.join(str(w['title']).split())}\"" if w.get("title") else "")
                      + f" ({w.get('phase')})" for w in running)
    return (f"Work in progress right now (other sessions are working on it): {items}. Hand over or start only work "
            "that does not depend on these results and does not touch these handovers or the changes they work on; "
            "do not report them as stalled.\n\n")


def idle_prompt(blocked: list[dict] | None = None, notice: str | None = None, running: list[dict] | None = None) -> str:
    """The idle ask: the product team's whole choice of the next work (goal-ends-with-run D0, D3); `notice`: the
    no-goal block of a run without a goal (D1, D2); `running`: sessions working now (parallel-sessions D3)."""
    return (
        _HUB + work_in_progress(running)
        + "The other teams have no work waiting. Choose the next work by your team's usual task-choice rule (the "
        "rule your team's instructions name), from your backlog, your technical debt and your team's own regular "
        "tasks (the schedule your team's instructions name) together.\n\n"
        "A regular task that is overdue or due within a day goes first, in place of a usual task: do it yourself in "
        "this session (one regular task per ask), record it as your schedule asks, and answer `did_regular`; you will "
        "be asked again right after it. Otherwise, is there a backlog task that a technical team can do fully without "
        "a human (preferred), or at least partly? If so, hand the best one over through the hub as you normally "
        "would. If none should be started now, answer `none` and change nothing.\n\n"
        + blocked_section(blocked or []) +
        "Hand over exactly one backlog item per handover, the smallest useful piece. Bundle items only when "
        "they are strongly linked (one cannot be done or accepted without the other) or there is a strong "
        "reason to do them together; then state that reason in the handover. Do not hand over the rest of the "
        "priority list in the same pass; it will be asked for again once this work moves.\n\n"
        "Return your verdict: `handed_over` if you handed an item over, `did_regular` if you did a regular task "
        "yourself, otherwise `none`; the reason; and in `waiting_for_owner` the backlog items that cannot start "
        "before the owner decides something (pricing, spending, legal, credentials), each with why. Leave the list "
        "empty when nothing waits for the owner.\n\n"
        + (notice + "\n\n" if notice else "")
        + STANDING_RULE
    )


IDLE_VERDICTS = ("handed_over", "did_regular", "none")

IDLE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(IDLE_VERDICTS)},
        "reason": {"type": "string"},
        "waiting_for_owner": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"item": {"type": "string"}, "why": {"type": "string"}},
                "required": ["item", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "reason", "waiting_for_owner"],
    "additionalProperties": False,
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["technical", "product", "owner"]},
        "answer": {"type": "string"},
        "reason": {"type": "string"},
        "note_for_owner": {"type": "string"},  # optional (fewer-owner-waits D9, D10)
    },
    "required": ["verdict", "answer", "reason"],
    "additionalProperties": False,
}


def consult_prompt(question: dict, team: str, handover: str, change: str | None, goal: str | None = None,
                   no_goal: str | None = None) -> str:
    return (
        f"Consultation, not a work session. The `{team}` team, working on handover {handover}"
        f"{f' (OpenSpec change `{change}`)' if change else ''}, has asked this question:\n\n"
        f"{json.dumps(question, indent=2, ensure_ascii=False)}\n\n"
        "Decide whether the answer can affect product success, user count or other key product "
        "figures. Read the backlog and product documents if useful. Do not change anything: no file "
        "edits, no `ho` write commands, no contact with other teams.\n\n"
        "Return your verdict:\n"
        "- `technical`: it cannot affect them; the team chooses the best variant itself (answer may be empty);\n"
        "- `product`: it can; give the answer you choose and the reason;\n"
        "- `owner`: a human must decide (for example pricing, spending money, legal); give the reason.\n\n"
        + CONSULT_POLICY
    ) + ("\n\n" + goal_block(goal) if goal else "\n\n" + no_goal if no_goal else "")


# consultation (fewer-owner-waits D9): the product team decides what its own policy allows
CONSULT_POLICY = (
    "Your team's instructions (its `CLAUDE.md`, the owner's goal) may say which decisions your team takes and which "
    "are reserved for the owner. Decide everything they allow you to decide (`technical` or `product`), and answer "
    "`owner` only for what they reserve for the owner or, where they say nothing, for what a human must decide. When "
    "you decide something the owner should know about, put a short note in `note_for_owner`; the dispatcher sends it "
    "to the owner as a handover that needs only an acknowledgement. Otherwise leave it empty."
)


def team_decision_title(triage_team: str, team: str, handover: str) -> str:
    return f"{triage_team}: decided for {team} on {handover}"


def team_decision_body(*, triage_team: str, team: str, handover: str, question, verdict: dict) -> str:
    """The non-blocking notice to the owner about a decision the triage team took (fewer-owner-waits D10)."""
    decision = verdict["answer"].strip() or "the team chooses the best variant itself"
    lines = [
        f"Team `{triage_team}` decided a question of team `{team}` on {handover} itself, as its instructions allow. "
        "Nothing waits for you; acknowledge it with `ho ack <this ID>`.",
        "",
        f"- Verdict: {verdict['verdict']}",
        f"- Decision: {decision}",
        f"- Reason: {verdict['reason']}",
        "", "## Note for the owner", "", _quote(verdict.get("note_for_owner") or ""),
        "", "## Question", "", "```json", json.dumps(question, indent=2, ensure_ascii=False), "```",
        "", "If you disagree, send the team a handover with your decision.",
    ]
    return "\n".join(lines) + "\n"


# ---- limit check at the maximum duration (check-session-at-time-limit D3, D4)

LIMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["progressing", "hung"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}

DIGEST_TEXTS, DIGEST_TOOLS = 8, 12
PROGRESS_LABELS = {"hub": "hub activity", "commits": "new commits", "tasks": "newly checked tasks"}


def _span(seconds: float) -> str:
    minutes = max(0, round(seconds / 60))
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 120 else f"{minutes} min"


def session_digest(r, now: float, progress: list[str] | None) -> str:
    """What the product team reads about a session at its maximum duration; `now` is on the runner's awake clock,
    `progress` the sources from made_progress."""
    lines = [f"Team `{r.team}`, handover {r.handover}, phase {r.phase}.",
             f"Running for {_span(now - r.awake_start)}; its last event other than a tool progress heartbeat was "
             f"{_span(now - r.last_event_at)} ago."]
    if r.running_tool:
        name, elapsed, seen = r.running_tool
        lines.append(f"Tool running now: {name}, for {_span(elapsed + now - seen)}.")
    else:
        lines.append("No tool is running now.")
    lines.append("Progress since the session started: "
                 + (", ".join(PROGRESS_LABELS.get(p, p) for p in progress) if progress
                    else "none (no new commits, no newly checked tasks, no hub activity)") + ".")
    for title, kinds, size in (("Recent status texts", ("text",), DIGEST_TEXTS),
                               ("Recent tool calls and failed tool results", ("tool", "error"), DIGEST_TOOLS)):
        events = [e for e in r.recent if e[1] in kinds][-size:]
        lines += ["", f"{title} (oldest first, age in minutes):"]
        lines += [f"-{round((now - at) / 60)} min  " + ("FAILED: " if kind == "error" else "") + text
                  for at, kind, text in events] or ["(none)"]
    lines += ["", f"Full event stream (JSON lines) for deeper reading: {r.stream_path}"]
    return "\n".join(lines)


def limit_check_prompt(digest: str, goal: str | None = None) -> str:
    return (
        "Consultation, not a work session. A team's session has reached the dispatcher's maximum session "
        "duration. Decide whether it is still progressing or hung; the dispatcher extends a progressing session "
        "and ends a hung one. Do not change anything: no file edits, no `ho` write commands, no contact with "
        "other teams. Read the files in the team's repository or the event stream below if useful.\n\n"
        + _quote(digest) + "\n\n"
        "Return your verdict with a short reason:\n"
        "- `progressing`: the session moves towards finishing its phase: it takes new steps, a long run (a test "
        "suite, a build) goes on with steady output, it made recent commits or checked tasks;\n"
        "- `hung`: it repeats the same action without effect, waits for something that will not come, or works on "
        "something outside its phase."
    ) + ("\n\n" + goal_block(goal) if goal else "")


# ---- goal run (goal-run design G3, G6)

GOAL_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "continue", "blocked"]},
        "reason": {"type": "string"},
        "done": {"type": "array", "items": {"type": "string"}},
        "left": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "reason", "done", "left"],
    "additionalProperties": False,
}


def guidance_notice(given: str, current: str) -> str:
    """What changed in the goal file since the text the product team last saw."""
    if given and current.startswith(given) and current[len(given):].strip():
        changed = "The owner added this to the goal:\n\n" + _quote(current[len(given):])
    else:
        changed = "The owner edited the goal text; the whole new text is the goal below."
    return (
        "The owner's guidance changed since your last session. " + changed + "\n\n"
        "Check the work in flight against it: where needed, comment on or return your handovers, or send a "
        "follow-up handover; otherwise keep the guidance for later work. Then do the goal check below.\n\n"
    )


GOAL_ONLY_THIS_RUN = "Only this run's goal sets the order of work; goals of earlier runs have ended."  # D6


def goal_check_prompt(goal: str, notice: str = "", running: list[dict] | None = None) -> str:
    return _with_rule(
        _HUB + "Goal check: the owner started a goal run, and no team has work waiting now.\n\n"
        + work_in_progress(running) + notice
        + "Compare the goal below with the hub (your handovers and their results), the backlog and what the "
        "teams have finished so far (closed handovers, archived OpenSpec changes). " + GOAL_ONLY_THIS_RUN + " Then:\n"
        "- if goal work is left that a team can do without the owner, hand over the next piece through the hub "
        "as you normally would: exactly one backlog item per handover, the smallest useful piece. Bundle items "
        "only when they are strongly linked (one cannot be done or accepted without the other) or there is a "
        "strong reason to do them together; then state that reason in the handover. Hand over only work that "
        "belongs to the goal;\n"
        "- if goal work is still in progress, change nothing.\n\n"
        "Return your verdict: `complete` when every part of the goal is done; `continue` when you handed work "
        "over or goal work is still in progress; `blocked` when what is left cannot go on without the owner "
        "(a decision on pricing, spending, legal or credentials, or an escalation waiting for an answer). "
        "`reason`: one or two sentences. `done`: what is finished, with evidence (closed handover IDs, archived "
        "change names). `left`: what is still to do or blocked, each with why.",
        goal,
    )


def resume_message(verdict: dict, question: dict, default_answer: str) -> str:
    asked = json.dumps(question, ensure_ascii=False)
    if verdict["verdict"] == "product":
        return (
            f"Answer to your question {asked}:\n\nProduct decision: {verdict['answer']}. "
            f"Reason: {verdict['reason']}. Record it in the change as a product decision and continue."
        )
    return f"Answer to your question {asked}:\n\n{default_answer}"


# ---- escalation to the owner (design E2, E4, E6)

def _quote(text: str) -> str:
    return "\n".join("> " + line for line in (text.strip() or "(empty)").splitlines())


def escalation_title(team: str, reason: str) -> str:
    short = " ".join(reason.split())
    return f"{team}: {short[:80]}{'...' if len(short) > 80 else ''}"


def escalation_body(*, team: str, handover: str, reason: str, phase: str | None, change: str | None,
                    question, result_tail: str, session: str | None, repo: str,
                    denied: list[dict] | None = None) -> str:
    """`denied`: the session's denials as `denial_entry` dicts, listed under `## Denied` (fewer-owner-waits D8)."""
    lines = [
        f"The dispatcher stopped work on {handover} for team `{team}` and needs your decision.",
        "",
        f"- Reason: {reason}",
        f"- Handover: {handover}" + (f", phase {phase}" if phase else "")
        + (f", OpenSpec change `{change}`" if change else ""),
        f"- Session: `{session or '-'}`",
    ]
    if isinstance(question, str) and question.strip():  # a text question (a denial, fewer-owner-waits D8)
        lines += ["", "## Question", "", _quote(question)]
    elif question:
        lines += ["", "## Question", "", "```json", json.dumps(question, indent=2, ensure_ascii=False), "```"]
    if denied:
        lines += ["", "## Denied", ""] + [f"- {d.get('tool')}: `{d.get('input')}`" for d in denied]
    if result_tail.strip():
        lines += ["", "## What the session reported last", "", _quote(result_tail)]
    lines += [
        "", "## How to answer", "",
        "`ho respond <this ID> -m \"<answer>\"` (as team `owner`) resumes the same session with your answer; "
        "`ho decline <this ID> -m \"<reason>\"` resumes it with the refusal, and the agent continues without that part.",
        "",
        "Manual fallback: " + (f"`claude --resume {session}` in `{repo}`, then " if session else "")
        + f"`python -m radark clear {handover}`.",
    ]
    return "\n".join(lines) + "\n"


def unconfigured_title(w: dict) -> str:
    """A handover waiting for a team the dispatcher does not run (unconfigured-team-escalation U4)."""
    return f"{w['sender']}: {w['handover']} waits for team {w['team']}, which the dispatcher does not run"


def unconfigured_reason(w: dict, config: str) -> str:
    return (f"{w['handover']} \"{w['title']}\" from {w['sender']} to {w['team']} ({w['state']}) waits for team "
            f"{w['team']}, which is not set up in the dispatcher ({config})")


def unconfigured_body(w: dict, *, config: str, item: str | None, session: str | None, repo: str) -> str:
    team, sender = w["team"], w["sender"]
    lines = [
        f"Handover {w['handover']} \"{w['title']}\" from `{sender}` waits for team `{team}`, which is not set up in "
        f"the dispatcher: `{team}` is a team of the hub, but the configuration `{config}` has no `[[teams]]` entry "
        "for it, so no session works on the handover.",
        "",
        f"- Waiting handover: {w['handover']} (recipient `{team}`: {w['state']})",
        (f"- Waiting item: {item} of `{sender}`; the dispatcher holds it until you answer" if item
         else f"- Waiting item: none that the dispatcher works on for `{sender}`"),
    ]
    if item:
        lines.append(f"- Session: `{session or '-'}`")
    resumes = f"the session of {item} resumes with your answer" if item else "nothing is resumed"
    lines += [
        "", "## How to fix", "",
        f"1. Add the team to `{config}`:", "",
        "   ```toml", "   [[teams]]", f'   id = "{team}"', "   repo = '<path to its repository>'",
        '   kind = "technical"   # or "product"', "   ```", "",
        f"   restart the dispatcher and respond to this handover ({resumes}); {w['handover']} is then work of `{team}`.",
        "2. Or have the work done another way and respond with what was done.",
        "", "## How to answer", "",
        "`ho respond <this ID> -m \"<answer>\"` (as team `owner`)"
        + (f" resumes the session of {item} with your answer." if item else "."),
    ]
    if item:
        lines += ["", "Manual fallback: " + (f"`claude --resume {session}` in `{repo}`, then " if session else "")
                  + f"`python -m radark clear {item}`."]
    return "\n".join(lines) + "\n"


def idle_escalation_body(team: str, verdict: dict) -> str:
    lines = [f"Team `{team}` found no backlog item that can start without you.", "",
             f"Reason: {verdict['reason']}", "", "## Waiting for your decision", ""]
    lines += [f"- {w['item']}: {w['why']}" for w in verdict["waiting_for_owner"]]
    lines += ["", "Answer with `ho respond <this ID> -m \"...\"` (as team `owner`); the product team sees it "
              "the next time it is asked for work. Or hand a decision over directly with `ho new`."]
    return "\n".join(lines) + "\n"


def owner_resume_message(link: dict, action: str, answer: str) -> str:
    asked = link.get("question")
    head = (f"You stopped to wait for the owner ({link.get('reason')})."
            + (f" Your question: {json.dumps(asked, ensure_ascii=False)}" if asked else ""))
    if action == "decline":
        return (f"{head}\n\nThe owner declined:\n\n{_quote(answer)}\n\nDo not do that part. Record the refusal "
                "in the change (design or tasks notes) and continue with the rest of the phase without it.")
    return (f"{head}\n\nThe owner answered:\n\n{_quote(answer)}\n\nRecord it in the change as the owner's "
            "decision and continue.")


def owner_fresh_note(link: dict, action: str, answer: str) -> str:
    """Appended to a fresh phase prompt when the escalated session cannot be resumed."""
    verb = "declined" if action == "decline" else "answered"
    asked = link.get("question")
    return (f"\n\nEarlier work on this handover stopped for the owner ({link.get('reason')})"
            + (f", question: {json.dumps(asked, ensure_ascii=False)}" if asked else "")
            + f". The owner {verb}:\n\n{_quote(answer)}\n\nTake this into account"
            + (" and do not do that part." if action == "decline" else "."))


def parse_blocked(text: str) -> str | None:
    """The reason of the last `BLOCKED: owner — <reason>` line (em dash, en dash or hyphen), or None."""
    found = BLOCKED_LINE_RE.findall(text or "")
    return found[-1] if found else None


def parse_change(result_text: str) -> str | None:
    found = CHANGE_LINE_RE.findall(result_text or "")
    return found[-1] if found else None
