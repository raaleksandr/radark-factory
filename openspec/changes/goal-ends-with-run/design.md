# Design: a goal binds only its run; the idle ask is the full choice of next work

## Context

See proposal.md – Why. The current state that matters:

- A goal run is `GoalRun` (`radark/state.py`), mirrored to `goal.json` in the run directory (`path`, `hash`,
  `started`, `status`, `result`, …). Its status is `running` until `end_goal()` sets the end status. One dispatcher
  per run directory (run lock), so in a run without a goal a `goal.json` still saying `running` means the goal run
  ended without its report (crash, closed window).
- `goal_for(team)` gives the goal text to every product-team prompt of a goal run (phase prompts, triage
  consultation, limit check, wrap-up, resume, goal check). A run without a goal gives nothing, so a team may keep
  following a goal order it wrote into its own files.
- The idle ask (`idle_ask()`, `prompts.IDLE_PROMPT`) runs only when `hub_latest()` moved past
  `meta.last_idle_ask`; after a `none` with owner items it sends an escalation and moves `last_idle_ask` past it, so
  nothing is asked until another team acts.
- Escalated and stalled items: `goal_blocked_items()` (handover, team, reason, kind) — usable in any run.
- Awake time: `radark.clock.awake()` stops while the computer sleeps; `nap()` waits in the main loop.
- Since the draft: RB-014 added `note_for_owner` and the team-decision notice (triage), RB-015 the wrap-up of a work
  session at its last time limit, RB-003 the `ho` contract check. None changes the idle ask; see D7.

## Goals / Non-Goals

**Goals:**
- A run without a goal behaves as the team's usual mode, whatever earlier goals said.
- One blocked item never idles the pipeline for more than `idle_reask_minutes` of awake time.
- The product team's regular tasks run through the idle ask.

**Non-Goals:**
- No change to goal-run selection (a goal run still never polls an idle hub; its goal check decides).
- The dispatcher does not edit team repositories; the product team removes the old order itself.
- No new rule for which task to pick; the product team's own rule is used as is (the engine only points to it).
- The product team's own rule text (outside this repository) is not part of this change.

## Decisions

**D0. The idle ask is the whole choice, including regular tasks.** `idle_prompt()` asks the product team to choose
by its usual task-choice rule from its backlog, technical debt and its own regular tasks ("the schedule your team's
instructions name"; no team file is named, the engine stays team-agnostic). An overdue or due-within-a-day regular
task goes first, done by the team itself in this session, one per idle ask. `IDLE_SCHEMA` and `parse_idle_verdict`
accept `did_regular`. After `did_regular` the dispatcher leaves the idle ask due (it does not move
`last_idle_ask` past the hub and sets the re-ask mark so the next loop asks at once); the regular task changes the
product repository, not the hub. A counter `meta.idle_regular_streak` (reset by any other verdict or any work
session) stops this after 3 in a row: the dispatcher then waits as after `none` and logs `idle_regular_limit`.
Alternatives: a separate timed "product turn" (rejected: a second path and setting); the product team handing the
regular task to itself through the hub (rejected: hub noise and a review step for work only it does).

**D1. No-goal notice in product prompts.** `prompts.NO_GOAL_NOTICE` is added, in place of the goal block, to the
idle prompt and to the product team's phase prompts (review, act) and triage consultation when the run has no goal.
Technical teams' prompts are unchanged. Implementation: `goal_for(team)` keeps returning the goal text in a goal
run; a sibling `no_goal_for(team)` returns the notice (plus D2's ended-goal notice when due) for the product team
in a run without a goal, and `prompts._with_rule` / `phase_prompt` / `consult_prompt` take it as an extra block.
Alternative: a cleanup session at the end of each goal run. Rejected: a goal run often ends by `--until`, `STOP` or
a usage limit, when no new session may start; and a stale order can also come from notes.

Proposed text (final wording is fixed in apply and quoted in `ho done`):
> No owner goal is active in this run. Goals of earlier runs have ended and set no order of work; choose the next
> task by your team's usual task-choice rule.

**D2. Ended-goal cleanup asked once, from `goal.json`.** In a run without a goal the dispatcher reads `goal.json`
at start. When it exists, the ended goal is identified by `path` + `started` (not by `hash`: the owner may append a
note with the `note` command after the run, which changes the hash but not the goal). When that key differs from
`meta.goal_cleanup_done`, the next product-team session prompt also carries
`prompts.ended_goal_notice(path, status, ended)`. After that session ends with any outcome other than
`interrupted` or `usage_limit`, `meta.goal_cleanup_done = key`. `end_goal()` writes a new `ended` field (local ISO
time) into `goal.json`; for an older file without it the end time is `started` + `result.duration_s` +
`result.slept_s` when those exist, otherwise omitted. A `goal.json` still `running` is named with the status
"ended without a report" and no end time.

Proposed text:
> The goal run on `<file>` ended (`<status>`, <HH:MM, date>). If your backlog files still record an order of work
> set by that goal, remove that order now; keep its unfinished parts as ordinary backlog items.

**D3. Blocked items in the idle prompt.** `IDLE_PROMPT` becomes `idle_prompt(blocked, notice)`; `blocked` is
`goal_blocked_items()` rendered as bullets (handover, team, kind, reason) with: "A blocked item is no reason to
leave other ready work waiting: choose ready work that does not depend on these items. Answer `none` only when every
ready item waits for the owner or depends on a blocked item." Empty list → the section is left out.

**D4. Re-ask by awake time.** New `[loop] idle_reask_minutes` (int ≥ 0, default 60, 0 = off). The dispatcher keeps
in memory the `awake()` reading at the end of the last session (any session, including the idle ask itself) or at
process start; `idle_ask()` runs when the hub moved (as today) or when `awake() - mark >= idle_reask_minutes * 60`.
Sleep is thus not counted without extra bookkeeping. The `none` console line adds `next ask ~HH:MM` (now + the
remaining minutes; it is an estimate, a sleep moves it). `meta.idle_reask_at` (wall time of that estimate) is stored
for `dry-run`, which prints "next idle re-ask ~HH:MM if the computer stays awake, or on hub activity". Deviation
from the draft (`meta.idle_awake_s` accumulated in the state): the awake clock is simpler and already sleep-aware;
after a dispatcher restart the count starts again from the restart, which only delays one re-ask.
Alternative: wall-clock timer. Rejected: on wake it would always be expired and fire an ask after every sleep.

**D5. No duplicate idle escalation.** The sorted list of `waiting_for_owner` items of the last idle escalation is
stored in `meta.idle_escalated_items`; a `none` with the same set sends nothing and logs `idle_escalation_skipped`.
A different set sends a new escalation (the previous one stays open). Alternative: never send again while one is
open. Rejected: a new owner item would never reach the owner.

**D6. Goal-check sentence.** `goal_check_prompt` gets: "Only this run's goal sets the order of work; goals of
earlier runs have ended." No other goal-run change.

**D7. Interplay with recent changes.**
- Wrap-up (RB-015) and limit checks resume the same session: the notices are given only in the first prompt of a
  session; a wrapped-up session counts as having run for D2 (its outcome is not `interrupted`/`usage_limit`).
- Team-decision notice / `note_for_owner` (RB-014): unchanged; it concerns triage, not the idle ask.
- `ho` contract check (RB-003): no new `ho` command or field is needed.
- Idle ask stays off unless `idle_ask = true`; the no-goal and ended-goal notices apply whether or not it is on.

## Deviations from the draft

- Paths `harness/` → `radark/`; capability stays `harness-dispatcher` (current name).
- No `harness.toml` in this repository: the setting is documented in `harness.toml.example` and the README only.
- The "product team's own rule" bullet is dropped (not this repository's work).
- Why text rewritten neutrally (public repository).
- Triage consultation also carries the no-goal notice (it is a product-team prompt that a goal run also enriches).
- D2 keys the ended goal by `path` + `started`, not `hash`; a `running` leftover is treated as ended.
- D4 uses the in-memory awake clock instead of `meta.idle_awake_s`.
- `did_regular` limit of 3 is in the spec (draft had it only as a risk mitigation).

## Risks / Trade-offs

- [The team redoes the same regular task in a loop] → the limit of 3 (D0); its schedule updates "next due" dates.
- [A regular task takes long] → one product session under the usual limits; technical work waits only for it.
- [The team still declines ready work with a reason of its own] → visible on the console with its reason; the
  re-ask gives another chance; a repeated pattern is for the team's rule, not the dispatcher.
- [Hourly re-asks on an empty backlog cost a short product session each] → at most ~8 in a quiet 8-hour run; the
  usage guard applies; 0 turns it off.
- [The cleanup request edits the product backlog inside a review or act session] → one small doc edit, asked once.

## Migration Plan

Older `goal.json` without `ended` works (D2). Older state without the new `meta` keys works (absent = nothing
escalated, no cleanup done, streak 0). Rollback: `idle_reask_minutes = 0`; the notices are prompt text only.

## Implementation notes (apply, unattended)

- D0: `last_idle_ask` is moved past the hub after every verdict, `did_regular` included; the immediate re-ask comes
  from `meta.idle_regular_streak` (1 or 2 → due at once), so the behaviour is the one D0 describes. The streak is not
  reset by the limit: while the last three asks all returned `did_regular`, the next one waits as after `none`.
- D4: the awake mark comes from the sleep watch's clock (`Dispatcher.awake_now()`), so tests use a fake clock. An
  interrupted idle ask is due again at once (in-memory retry flag) also when it was due by time or by a regular task.
  The idle ask log record gains `cause` (`hub | retry | regular | time`) and `blocked`.
- D1: the no-goal block goes to every fresh phase prompt of the product team (also the fresh prompt that replaces a
  resume that failed), not only review and act; resumes, limit checks and wrap-ups never carry it.
- D2: the session that carried the request is logged as `ended_goal_notice` (key, outcome, counted). A work session
  stopped for a wrap-up is counted by its wrap-up part (D7).
- D5: the escalated set is the sorted list of `item` texts; it is stored only when the escalation handover was sent.
