# Design

Handover: HO-20261125-mjzz (RB-035).

## Context

`Dispatcher.usage_hold()` computes the windows that hold (`held_windows`, budgeted windows exempt) and, for the
latest one, calls `wait_for_reset(..., "threshold")`, which sets `meta.backoff_until = max(old, until)` and
`meta.usage_wait = {until, window, utilization, cause}`. Both loops (`loop_serial`, `_loop_parallel`) then wait while
`backoff_until > now`. Nothing ever lowers `backoff_until`: a threshold wait stored by an earlier run keeps holding
even when the current run's thresholds (its `--budget-*` or a raised `usage_pause_percent`) no longer reach the
window. `limit_hit` waits come from `start_backoff`, other pipelines' holds from `shared_hold` (cause
`other_pipeline`). A threshold wait is never written as a machine-wide hold.

## Goals / Non-Goals

**Goals:** a stored threshold wait is re-evaluated with the current run's thresholds before every step; dropped with
a console line and a log event when it no longer holds; `limit_hit` and `other_pipeline` waits unchanged; `dry-run`
reports the stored wait honestly.

**Non-Goals:** changing how the `limit_hit` back-off or machine-wide holds work; a new output of the `status`
subcommand (it reports the machine layer; the optional item of the handover is covered by `dry-run` and
`run --once`, which print `usage_report`); changing the state file format.

## Decisions

### D1 — Re-check inside `usage_hold`, before the hold is computed

A new method `drop_stale_threshold_wait()` runs first in `usage_hold()`. `usage_hold()` is already called before
every new step in both loops (their first iteration is the run start), and `budget_end()` runs before it, so a
budgeted window at or above its budget still ends the run first (spec scenario "Threshold still reached"). No other
call site is needed.

### D2 — When a stored wait counts as stale

Drop only when all of these hold:

1. `meta.usage_wait` exists with `cause == "threshold"` and a `window`;
2. `meta.backoff_until > now` and `meta.backoff_until <= usage_wait["until"]` — the pending back-off is wholly the
   threshold wait's. If `backoff_until` is later (a `limit_hit` or doubling back-off extended it without rewriting
   `usage_wait`), the wait is kept: it cannot be told which part is the threshold's, and keeping is the safe side;
3. the stored window is not among `held_windows(effective_usage(), cfg.usage_pause_percent, now, set(budget))` —
   with the current run's thresholds the window no longer holds (below the threshold, budgeted for this run, reset,
   or no live reading). A `rejected` status still holds, as today.

Then: pop `backoff_until` and `usage_wait` from `meta`, reset `_usage_announced`, write a run-log event
`usage_wait_dropped` (window, utilization, the threshold that applies now — the budget for a budgeted window, else
`usage_pause_percent` — and `budget: true|false`), print one line, save the state. `backoff_minutes` (the doubling
counter of the back-off without a known reset) is left alone.

After the drop the rest of `usage_hold()` runs as usual: if another window holds now, a new threshold wait starts for
it; `shared_hold()` still applies another pipeline's hold (it compares with `backoff_until`, now absent, so a live
machine hold is re-applied and kept).

Alternative considered: never store threshold waits and recompute them each time. Rejected — the stored wait feeds
the reminder lines, the resume line and `run --once`; dropping a stale one is the smallest change.

### D3 — Console wording

`{stamp}  Usage: {window} {pct} used is below {threshold}% ({run budget | usage_pause_percent}); the stored usage
wait no longer applies, resuming.` — one plain line, not a `!` problem line. Exact wording may be tuned in apply;
tests check the window name, the share and the threshold.

### D4 — `usage_report` (dry-run / `run --once`)

The D2 predicate is a pure helper `stale_threshold_wait(meta, usage, threshold, budget, now)` used by D1 and here.
When `backoff_until > now` and no window holds: for a stale threshold wait print `guard: a stored threshold wait
({window}, until {clock}) no longer applies with this run's thresholds; next step would start`; otherwise print the
back-off line with its cause, e.g. `guard: below the threshold, but in usage-limit back-off until {clock} (cause
limit_hit)`. `dry-run` writes nothing, so it only reports; the drop happens in a real run.

## Risks / Trade-offs

- The drop uses the same latest reading as the hold, so the decision matches what a fresh run without a stored wait
  would do. Accepted.
- Parallel loop: `usage_hold()` runs under the dispatcher lock in `_loop_parallel`, so the state change is safe.

## Assumptions (unattended session)

- "At run start and before each step" is met by the existing `usage_hold()` call sites.
- The optional `status` item of the handover is met through `dry-run` / `run --once` output, not the `status`
  subcommand.
- Log event name `usage_wait_dropped` chosen here; nothing reads it yet.
- Apply: the D2 helper also keeps the wait of a budgeted window whose budget is reached (`budget_reached` for that
  window). In a run `budget_end()` ends the run first anyway; the check keeps `dry-run` from claiming the next step
  would start while its budget line says the run would end.
- Apply: when the window has reset or has no live reading, the console line says so instead of naming a share
  (`Usage: seven_day has reset or has no current reading (threshold 95%, run budget); ...`).
