# Proposal

## Why

The pipeline is meant to work for hours unwatched, choosing work by the product team's usual rule: its backlog,
technical debt (two useful tasks, then at most one technical-debt task) and its own regular product tasks (statistics,
store ranks, competitors), overdue regular tasks first. Two defects broke that:

- **A goal outlived its run.** On 2026-11-12 the owner started a run without a goal. At 09:24 the only item, BL-179
  (HO-20261111-d33q), was escalated to the owner. The idle ask at 09:25 returned `none`: the product team still
  followed the goal of the 2026-11-11 run, written into its `backlog/BACKLOG.md`, although that run had ended the day
  before; BL-182 and BL-183 (P1) were ready. The dispatcher does not ask again until the hub moves, so the pipeline
  stood idle for five hours.
- **Regular product tasks never ran.** The idle ask is the product team's "choose the next task" step and runs after
  every finished task (about 15 times on 2026-11-10/11). Its prompt asks only to hand a backlog task to a technical
  team, and its verdict knows only `handed_over` and `none`. So, although the team's rule says "schedule first", every
  idle ask handed over a team task and the weekly store review (due 2026-11-09), store ranks (due 2026-11-10) and
  competitor watch (due 2026-11-12) never ran.

## What Changes

- **The idle ask is the full choice of the next work.** The prompt asks the product team to choose by its usual rule
  from everything at once: its backlog, technical debt and its own regular product tasks. A regular task that is
  overdue or due within a day goes first, in place of a usual task, and the product team does it itself in that
  session. The verdict gets a third value, `did_regular`; after it the dispatcher asks again at once, so the next
  task follows without a pause.
- **A goal binds only its own run.** In a run without a goal, every product-team prompt (idle ask, review, act) states
  that no owner goal is active and earlier goals set no order of work. The first such prompt after a goal run names
  that goal (file, end status, end time) and asks the team to remove its order of work from the backlog, keeping its
  unfinished parts as ordinary items. The goal check says only this run's goal counts.
- **A blocked item does not stop the pipeline.** The idle prompt names escalated and stalled items and asks for ready
  work that does not depend on them; `none` is right only when every ready item waits for the owner or depends on a
  blocked item.
- **The idle ask is repeated on a quiet hub.** After a `none`, the dispatcher asks again on new hub activity (as today)
  or after `[loop] idle_reask_minutes` of awake time (default 60; 0 = only on hub activity). A repeated `none` sends no
  new owner escalation when the items waiting for the owner are unchanged. The console shows the reason of a `none` and
  the next ask time.
- **Product team's own rule (outside this repository):** "one regular task per run" becomes "one per choice", and
  "due within a day" is added. Sent to `product` as an owner handover on 2026-11-12 (not part of the
  harness code).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Asking for the next task when idle* (choice includes the team's regular tasks, `did_regular`
  verdict, blocked items named, repeat after a quiet period, no duplicate owner escalation); *Goal check* (only the
  current run's goal counts); new requirements *No active goal in a run without a goal* and *Ended goal removed from
  the backlog*.

## Impact

- `harness/prompts.py`: idle prompt (choice rule, regular tasks, blocked items, no-goal notice), `IDLE_SCHEMA`
  (`did_regular`), ended-goal notice, goal-check sentence.
- `harness/__main__.py`: `parse_idle_verdict`, idle-ask timing (awake time, immediate re-ask after `did_regular`),
  blocked list in the prompt, ended-goal notice read from `goal.json` once per goal, no duplicate idle escalation,
  console lines, `dry-run`.
- `harness/config.py`, `harness.toml.example`, `harness.toml`: `idle_reask_minutes`.
- `harness/README.md`; tests in `harness/tests`.
- No hub changes. The product team's rule change is a handover, not code here.
