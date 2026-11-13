# Proposal

## Why

The run of 2026-11-10 (`run --until 12:00 --keep-awake 12:00`, started 02:19) was meant as "work until 12:00 without
sleep". `--until` stops starting new steps at 12:00, but a session running at that moment finishes first (here the
apply session of HO-20261110-walr, started 11:25). `--keep-awake 12:00` ended at 12:00 on the clock, regardless of that
session: the console shows `12:00  Keep awake ended; the computer may sleep.` and then
`12:58  ! computer slept 12:00–12:58 (58 min)`. The last session lost an hour, and the two options, which look like one
setting to the owner, are not tied together.

## What Changes

- When a run has an end time (`--until`) and its keeping-awake moment is at or after that end time, the computer is
  kept awake for the whole run: until the run really ends, including the session that finishes after the end time.
  A keeping-awake moment before the end time keeps its meaning (the owner allows sleep during the run's later part).
- The start line and `dry-run` say so: `Keep awake: whole run (until 12:00 given, the run ends at 12:00)`, and the
  setting record in the run log notes the given moment.
- The README "Keep awake" and "Pause / stop" parts state that "work until X without sleep" is
  `run --until X --keep-awake` (the bare flag), and that a running session can outlast the end time.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "Keeping the computer awake" (a moment at or after the end time covers the whole run) and
  "Reporting keeping awake" (the start line for that case).

## Impact

- `harness/__main__.py` (applying the end time to the keep-awake setting after both options are read; start line and
  `dry-run` text), `harness/awake.py` only if the setting type needs a field for the given moment.
- Tests in `harness/tests/test_keep_awake.py` (and `test_until.py` if the combination is tested there).
- `harness/README.md`.
- No new options; `[loop] keep_awake` (only `off`, `on`, a range) is unaffected.
