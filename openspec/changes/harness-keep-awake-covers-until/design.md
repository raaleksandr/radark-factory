# Design

## Context

See proposal.md - Why. `--until` (run-until-time) and `--keep-awake` (keep-computer-awake) are parsed separately in
`harness/__main__.py` (`args` → `d.until`, `d.keep_awake`); the keeper thread (`harness/awake.py`, `Keeper`) decides
from `wanted(setting, now)` alone and knows nothing of the end time. A session running at the end time finishes first
(up to `session_max_minutes`, longer with limit checks), so a keeping-awake moment equal to the end time always leaves
that session unprotected.

## Goals / Non-Goals

**Goals:** "work until X without sleep" protects the whole run whichever of the two natural spellings the owner uses
(`--keep-awake` or `--keep-awake X`).

**Non-Goals:** daily ranges (`HH:MM-HH:MM`) and `[loop] keep_awake` stay as they are; no new option; no change to how
`--until` ends a run.

## Decisions

### D1. Turn the moment into the whole run once, at start

After both options are read (run and `dry-run`), if `until` is set, the setting's mode is `until` and its moment is
at or after the end time, replace the setting with mode `on`, keeping the given moment for reporting (e.g. a
`given` field on `KeepAwake`, or a separate value next to it). The keeper then runs as for `on` and stops with the run
(`stop_keep_awake`, and Windows drops the request with the process).

Alternatives:
- *Keep awake while any session runs, past every moment:* changes the meaning of an earlier moment that the owner
  chose on purpose (sleep allowed during the later part of a run). Rejected.
- *Only a warning at start:* the owner would still lose the session in an unattended night run. Rejected; the owner's
  intent for an equal or later moment is clear.
- *Make the keeper aware of the running session:* more state across threads for the same effect. Rejected.

Comparison at minute precision: both moments come from `parse_until` and are whole minutes, so "at or after" is a
plain `>=` on the two datetimes.

### D2. Reporting

`keep_awake_text` gives `whole run (until 12:00 given, the run ends at 12:00)` for the replaced setting; the
`keep_awake_setting` log record has `mode: "on"`, `text` as given and `until` as the given moment (so the record says
both what was given and what applies). A goal run's `goal_start.keep_awake` keeps the given text. `dry-run` prints the
same text after `Would keep awake: `.

### D3. Documentation

README: in "Keep awake", one paragraph on the combination with `--until` (equal or later moment → whole run; earlier
moment unchanged); in "Pause / stop", the example `run --until 12:00 --keep-awake` for "until 12:00 without sleep".

## Risks / Trade-offs

- [The owner gives a later moment to have the computer sleep after it even if the run goes on] → unlikely with an end
  time before it (the run would not start new steps after the end time anyway); the start line names the change, so it
  is visible at once.
- [A run whose last session hangs keeps the computer awake longer] → bounded by `session_max_minutes` and the limit
  checks, the same as with `--keep-awake` bare today.

## Migration Plan

No stored state; takes effect on the next run. Rollback: revert the commit.
