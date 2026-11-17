# Proposal: strict end-time suffix shows the day when "stopped by" passes midnight

Handover: **HO-20261117-ln7w** (RB-032, "strict end-time suffix shows the day when 'stopped by' passes midnight"),
from `radark-product`.

## Why

With `--until 23:59 --until-strict` and the default 15-minute grace period the start line and `dry-run` print
`(strict: running sessions wrap up at 23:59, stopped by 00:14)`. The "stopped by" moment (end time +
`wrap_up_minutes`) is on the next calendar day, but the text carries no day, so it reads as if sessions were
stopped *before* the end time. The owner must be able to tell unambiguously when sessions are stopped.

## What Changes

- When the "stopped by" moment of a strict end time falls on a different calendar day than the end time, the
  strict-mode suffix carries the day in the form already used for day-qualified clock times: `00:14 tomorrow`, or
  `00:14 on 2026-11-20` when that day is not tomorrow (relative to the current day, like the `Run ends at ...` text
  before it).
- When it falls on the same day as the end time, the text stays exactly as it is today.
- Applies to both places that print the suffix: the run's start line (`Run ends at ...`) and `dry-run`
  (`Would end: ...`). The run log record (`run_until`) does not change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `harness-dispatcher`: requirement *Reporting an end time* — the strict-mode "stopped by" moment names its day
  when it is on a different calendar day than the end time.

## Impact

- `radark/__main__.py`: the strict-mode suffix helper (`Dispatcher.until_mode`), reusing `day_clock`.
- `radark/tests/test_until_strict.py`: new cases (across midnight to tomorrow, across midnight on a later date);
  the existing same-day cases stay unchanged.
- No configuration, CLI, log or state format change.
