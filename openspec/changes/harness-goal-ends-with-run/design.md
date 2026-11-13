# Design

## Context

See proposal.md - Why. The current state that matters:

- A goal lives in `goal.json` in the run directory (path, hash, text, status, last verdict, `result`). A run without
  `--goal` sets no goal and its prompts say nothing about goals, so a team may keep following a goal it wrote into its
  own files (the product team keeps its order of work in the counter line of `backlog/BACKLOG.md`).
- The product team's usual task-choice rule (two useful tasks, then at most one technical-debt task; regular tasks
  from `backlog/REGULAR.md` when due) lives in its `CLAUDE.md` and `backlog/README.md`. The dispatcher only has to
  point to it, not repeat it.
- The idle ask (`idle_ask()`, `IDLE_PROMPT`) runs only when `hub_latest()` moved past `meta.last_idle_ask`; after a
  `none` with owner items it sends an escalation and sets `last_idle_ask` past that escalation, so nothing new is asked
  until another team acts.
- Escalated and stalled items are known from the state (`state.blocked(hid)`, `goal_blocked_items()`).
- Awake time is already tracked for goal runs and sleep is detected (sleep-aware); `nap()` sleeps in the main loop.

## Goals / Non-Goals

**Goals:**
- A run without a goal behaves as the team's usual mode, whatever earlier goals said.
- One blocked item never idles the pipeline for more than `idle_reask_minutes`.

**Non-Goals:**
- No change to goal-run selection (a goal run still never polls an idle hub; its goal check decides).
- The dispatcher does not edit team repositories; the product team removes the old order itself.
- No new rule for which task to pick; the product team's own rule is used as is.
- Running work sessions in parallel is `harness-parallel-teams`, not this change.

## Decisions

**D0. The idle ask is the whole choice, including regular tasks.** `idle_prompt()` asks the product team to choose by
its usual task-choice rule from its backlog, technical debt and its own regular product tasks ("the schedule your
team's instructions name"; the dispatcher does not name the file, so the harness stays team-agnostic). Overdue or
due-within-a-day regular task first, done by the team itself in this session, one per idle ask. `IDLE_SCHEMA` and
`parse_idle_verdict` accept `did_regular`. After `did_regular` the dispatcher does not move `last_idle_ask` past the
hub, so the next loop asks again at once (the regular task changes the product repository, not the hub).
Alternatives considered: a separate "product turn" on a timer (rejected: the idle ask already runs after every
finished task; a timer adds a second path and a setting); having the product team hand the regular task to itself
through the hub (rejected: hub noise and a review step for work only it does).

**D1. No-goal notice in product prompts, not a goal-end session.** `prompts.NO_GOAL_NOTICE` is appended to the idle
prompt and to the product team's review and act prompts when `self.goal is None`. Alternative considered: a cleanup
session at the end of each goal run. Rejected: a goal run often ends by `--until`, `STOP` or a usage limit, when no
new session may start; and a stale order can also come from notes, not only from a goal run. The notice costs one
paragraph per prompt and corrects any leftover order on the next product session.

**D2. Ended-goal cleanup asked once, from `goal.json`.** At the start of a run without a goal the dispatcher reads
`goal.json`; when its `status` is not `running` and its `hash` differs from `meta.goal_cleanup_done`, the next
product-team prompt also carries `prompts.ended_goal_notice(path, status, ended)`. After that session ends with any
outcome other than `interrupted` or `usage_limit`, `meta.goal_cleanup_done = hash`. `end_goal()` writes a new
`ended` field (local ISO time) into `goal.json`; for an older file without it the end time is derived from `started`
plus `duration_s` plus `slept_s`, and omitted if that fails. Alternative: ask every time. Rejected: noise, and a team
could re-edit its backlog on each prompt.

**D3. Blocked items in the idle prompt.** `IDLE_PROMPT` becomes `idle_prompt(blocked, notice)`. `blocked` is the
list from `goal_blocked_items()` (handover, team, kind, reason), rendered as bullets with the instruction from the
spec; empty list → the section is left out. The verdict schema is unchanged.

**D4. Re-ask by awake time.** New `[loop] idle_reask_minutes` (int, default 60, 0 = off). After each idle ask and
each session the dispatcher stores `meta.last_session_end` (wall time) and accumulates awake idle seconds in
`meta.idle_awake_s`, reset when any session starts; the existing sleep detection subtracts slept time, so a night's
sleep does not trigger a re-ask on wake. `idle_ask()` runs when the hub moved (as today) or when `idle_awake_s >=
idle_reask_minutes * 60`. The console line of a `none` verdict adds `next ask ~HH:MM` (now + remaining minutes,
awake). Alternative: wall-clock timer. Rejected: on wake the timer is always expired and the PC would run an ask at
once after every sleep, which the sleep-aware design avoids elsewhere.

**D5. No duplicate idle escalation.** The sorted list of `waiting_for_owner` item IDs of the last idle escalation is
stored in `meta.idle_escalated_items`; a `none` verdict with the same set sends nothing and logs
`idle_escalation_skipped`. A different set sends a new escalation (the previous one stays open; the owner answers
whichever is current). Alternative: never send again while one is open. Rejected: a new owner item would then never
reach the owner.

**D6. Goal-check sentence.** `goal_check_prompt` gets one sentence: only this run's goal sets the order of work;
earlier goals have ended. No other goal-run change.

## Risks / Trade-offs

- [`did_regular` repeated in a loop (the team redoes the same regular task)] → The team's schedule has day limits and
  "Next due" dates updated after each run; the dispatcher also counts consecutive `did_regular` verdicts and, after
  3 in a row, waits for hub activity or `idle_reask_minutes` as after `none` (logged `idle_regular_limit`).
- [A regular task takes long (store reads, reports)] → It runs as one product session under the usual session limits;
  technical work waits only for that session, which is the owner's chosen priority for overdue regular tasks.

- [The product team still declines ready work with a reason of its own] → It is visible on the console with its
  reason, and the re-ask after `idle_reask_minutes` gives it another chance with the same notice; a repeated pattern is
  for the product team's rule, not the dispatcher.
- [Hourly re-asks cost a product session (~1–2 min) each on a truly empty backlog] → ~8 short sessions a day at most
  in a 8-hour quiet run; the usage guard still applies; 0 turns it off.
- [The cleanup request edits the product backlog in a review or act session] → It is one small doc edit, same as the
  team's usual bookkeeping; it is asked once per goal.
- [A new goal run while the old order is still in the backlog] → D6 tells the goal check that only the current goal
  counts.

## Migration Plan

`harness.toml` gets `idle_reask_minutes = 60` with a comment; `harness.toml.example` documents it. Older `goal.json`
files without `ended` work (D2). Rollback: set `idle_reask_minutes = 0`; the notices are prompt text only.
