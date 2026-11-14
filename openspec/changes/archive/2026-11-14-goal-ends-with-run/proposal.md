# Proposal: a goal binds only its run; the idle ask is the full choice of next work

Handover: **HO-20261113-bo4f** (backlog item RB-005, from `radark-product`). Based on the product team's draft
`harness-goal-ends-with-run` (2026-11-12), updated to the current code; deviations are listed in design.md.

## Why

A pipeline is meant to work for hours unwatched, choosing work by the product team's usual rule: its backlog,
technical debt and its own regular tasks (for example a weekly report or usage statistics), overdue regular tasks
first. Two defects break that:

- **A goal outlives its run.** A run without a goal stood idle for five hours: the only item in progress was
  escalated to the owner, and the idle ask returned `none` because the product team still followed the order of
  work of the previous run's goal, which it had written into its own backlog files. Ready items were left waiting.
  The dispatcher does not ask again until the hub moves, so nothing happened until a human looked.
- **Regular tasks never run.** The idle ask is the product team's "choose the next task" step and runs after every
  finished task. Its prompt only asks to hand a backlog task to a technical team, and its verdict knows only
  `handed_over` and `none`. So the team's own regular tasks, even overdue ones, never ran.

## What Changes

- **The idle ask is the full choice of the next work.** The prompt asks the product team to choose by its usual
  task-choice rule (the rule its own instructions name; the engine does not name team files) from its backlog,
  technical debt and its own regular tasks together. A regular task that is overdue or due within a day goes first;
  the product team does it itself in that session and returns the new verdict `did_regular`. The next idle ask
  follows at once; after three `did_regular` in a row the dispatcher waits as after `none` (log `idle_regular_limit`).
- **A goal binds only its own run.** In a run without a goal, the product team's prompts (idle ask, review, act,
  triage consultation) say that no owner goal is active and earlier goals set no order of work. The first such
  prompt after a goal run names the ended goal once (file, end status, end time) and asks the team to remove its
  order of work from the backlog, keeping its unfinished parts as ordinary items. The goal check says only this
  run's goal counts.
- **A blocked item does not stop other work.** The idle prompt names escalated and stalled items and asks for ready
  work that does not depend on them; `none` is right only when every ready item waits for the owner or depends on a
  blocked item.
- **Re-ask on a quiet hub.** After `none` (or `handed_over`), the dispatcher asks again on new hub activity (as
  today) or after the new **`[loop] idle_reask_minutes`** (default 60; 0 = only on hub activity) of awake time since
  the last session; sleep does not count. A repeated `none` with the same items waiting for the owner sends no new
  escalation (log `idle_escalation_skipped`). The console line of a `none` gives its reason and `next ask ~HH:MM`;
  `dry-run` mentions the re-ask.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Asking for the next task when idle* (full choice incl. regular tasks, `did_regular`,
  blocked items named, re-ask after quiet awake time, no duplicate owner escalation); *Goal check* (only this run's
  goal counts); *Configuration* (`idle_reask_minutes`); new requirements *No active goal in a run without a goal*
  and *Ended goal removed from the backlog*.

## Impact

- `radark/prompts.py`: `idle_prompt(blocked, notice)` replaces `IDLE_PROMPT`; `IDLE_SCHEMA` gets `did_regular`;
  `NO_GOAL_NOTICE`, `ended_goal_notice(...)`; goal-check sentence.
- `radark/__main__.py`: `parse_idle_verdict`, idle-ask timing (awake clock, immediate re-ask after `did_regular`,
  limit of three), blocked list in the idle prompt, no-goal and ended-goal notices for product prompts, `ended` time
  in `goal.json`, duplicate idle escalation skipped, console lines, `dry-run`.
- `radark/config.py`, `harness.toml.example`, `radark/README.md`; tests in `radark/tests`.
- No hub or `ho` changes. Setting `idle_reask_minutes` in running pipelines is the owner's step.
