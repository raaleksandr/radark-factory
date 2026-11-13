# Proposal: `--until X --keep-awake X` keeps the computer awake until the run really ends

Handover: **HO-20261113-aidk** (backlog item RB-007), from `radark-product`. Based on the product team's draft
`harness-keep-awake-covers-until`, updated to the current code (package `radark`, v0.2.0).

## Why

An overnight run with `--until 12:00 --keep-awake 12:00` was meant as "work until 12:00 without sleep", but lost an
hour of its last session to sleep. `--until` stops starting new steps at 12:00, while a session running at that moment
finishes first; `--keep-awake 12:00` ends at 12:00 on the clock, regardless of that session, so the console showed
`12:00  Keep awake ended; the computer may sleep.` and then a sleep line of about an hour. The two options look like
one setting to the owner, but they are not tied together.

## What Changes

- When a run has an end time (`--until`) and its keep-awake moment is at or after that end time, the computer is
  kept awake for the whole run: until the run really ends, including the session that finishes after the end time.
  A keep-awake moment before the end time keeps its meaning (the owner allows sleep during the run's later part).
- The start line and `dry-run` say so: `Keep awake: whole run (until 12:00 given, the run ends at 12:00)`, and the
  `keep_awake_setting` record in the run log has `mode: "on"` and the given moment.
- `radark/README.md` "Keep awake" and "Pause / stop" state that "work until X without sleep" is
  `run --until X --keep-awake` (the bare flag), that an equal or later moment now means the same, and that a running
  session can outlast the end time.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "Keeping the computer awake" (a moment at or after the end time covers the whole run) and
  "Reporting keeping awake" (the start line, log record and `dry-run` text for that case).

## Impact

- `radark/__main__.py`: applying the end time to the keep-awake setting after both options are read (shared by `run`,
  `once`, `plan` and `dry-run`), `keep_awake_text`, `start_keep_awake`.
- `radark/awake.py`: one optional field on `KeepAwake` for the given moment (design D1).
- Tests in `radark/tests/test_keep_awake.py`.
- `radark/README.md`.
- No new options; `[loop] keep_awake` (only `off`, `on`, a range) is unaffected; no stored state changes.
