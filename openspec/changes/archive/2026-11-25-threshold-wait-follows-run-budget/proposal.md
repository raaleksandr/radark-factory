# Proposal

Handover: **HO-20261125-mjzz** (backlog item RB-035, from `radark-product`): a run's usage budget overrides a
stored threshold wait.

## Why

A run that reaches `usage_pause_percent` stores its wait in the state file (`meta.backoff_until` and `usage_wait`
with `cause: "threshold"`). The wait outlives the run: a later run started with a higher budget (`--budget-5h` /
`--budget-7d`) or a raised `usage_pause_percent` prints its budget (for example "seven_day up to 95% (now 90%)")
and then still waits for the old reset, because the run loop only compares `backoff_until` with the clock. The only
workaround is a hand edit of the state file. A threshold wait is a decision made against the thresholds of the run
that stored it; it must follow the thresholds of the run that is running now.

## What Changes

- Before every new step (so also at run start) a stored wait with cause `threshold` is re-evaluated against the
  current run's thresholds: the run budget for a budgeted window, else `usage_pause_percent`, using the same latest
  reading the hold uses. When the window no longer holds, the wait is dropped from the state file, a short console
  line and a run-log event `usage_wait_dropped` say so, and the step starts. When it still holds, the wait stays as
  today.
- A `limit_hit` wait (real rejection by the provider, including the doubling back-off) and an `other_pipeline` hold
  are not dropped by a higher budget or threshold.
- `dry-run` (and `run --once` while held) report a stored wait with its cause and until-time, and say when a stored
  threshold wait would be dropped for this run instead of claiming a back-off.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirement "Stored threshold wait follows the current run's thresholds" (a stored
  threshold wait is re-evaluated against the current run's thresholds; `limit_hit` and another pipeline's hold are
  not); modified requirement "Reporting usage waits" (the drop is announced and logged, and `dry-run` shows a stored
  wait with its cause).

## Impact

- Code: `radark/__main__.py` (`Dispatcher.usage_hold`, a new helper that drops a stale threshold wait,
  `usage_report`).
- Tests: a new or extended test module for usage waits (`radark/tests/test_usage.py` / `test_budget.py`), with the
  fake `claude` and `ho`.
- State file format unchanged; a run without a budget and with an unchanged threshold behaves exactly as before.
