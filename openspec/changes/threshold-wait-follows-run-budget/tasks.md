# Tasks

Handover: HO-20261125-mjzz (RB-035). Archiving the change and syncing its specs are a separate phase after the author
closes the handover; they are not tasks of this change.

## 1. Stale threshold wait

- [x] 1.1 Add a pure helper `stale_threshold_wait(meta, usage, threshold, budget, now)` in `radark/__main__.py` that
      returns the stored threshold wait when it no longer holds under the given thresholds (design D2), else None
- [x] 1.2 Add `Dispatcher.drop_stale_threshold_wait()` and call it first in `usage_hold()`: drop `backoff_until` and
      `usage_wait`, reset `_usage_announced`, log `usage_wait_dropped`, print one line, save the state (D1–D3)
- [x] 1.3 `usage_report`: name the cause of a stored back-off and say when a stored threshold wait would be dropped
      (D4)

## 2. Tests (fake `ho` and `claude`, temporary folders only)

- [x] 2.1 Regression: the state holds a threshold wait (seven_day at 90 %, `usage_pause_percent` 90, until
      tomorrow); a run with `--budget-7d 95` and the reading at 90 % does not wait, runs the step, and the wait is
      gone from the state; the console line and the `usage_wait_dropped` event are present
- [x] 2.2 Raised `usage_pause_percent` (95) with a stored threshold wait and the reading at 91 %: dropped, step runs
- [x] 2.3 Still reached: budget 95 % with the reading at 95 % ends the run at the budget, wait not dropped; an
      unbudgeted window at 92 % with threshold 90 keeps its wait
- [x] 2.4 A `limit_hit` wait is not dropped by a higher budget; another pipeline's hold (machine layer) is not dropped
- [x] 2.5 A `backoff_until` later than the threshold wait's until-time is kept (D2 item 2)
- [x] 2.6 The serial and the parallel loop both drop a stale wait
- [x] 2.7 `dry-run` reports a stored wait with its cause, and the "no longer applies" line for a stale threshold wait

## 3. Docs and finish

- [x] 3.1 `radark/README.md`, usage guard / budget section: one sentence on stored threshold waits
- [x] 3.2 Full suite: `radark-test-slot python -m pytest radark/tests`; failing or flaky tests per hub `AGENTS.md`
      section 10, reported in the result
- [x] 3.3 Commit locally (no push, tag, release or reinstall), citing HO-20261125-mjzz
- [ ] 3.4 `ho done HO-20261125-mjzz -m "<change name, commit IDs, test counts, failing/flaky tests>"` — the last step
