# Design

## Context

See proposal.md - Why. `--until` and `--keep-awake` are parsed separately in `radark/__main__.py` `main()`
(`until` as epoch seconds → `d.until`; `parse_keep_awake` → `d.keep_awake`, a `KeepAwake` from `radark/awake.py`).
The keeper thread (`Keeper`) decides from `wanted(setting, now)` alone and knows nothing of the end time. A session
running at the end time finishes first (up to `session_max_minutes`, longer with limit checks), so a keep-awake moment
equal to the end time always leaves that session unprotected.

## Goals / Non-Goals

**Goals:** "work until X without sleep" protects the whole run whichever of the two natural spellings the owner uses
(`--keep-awake` or `--keep-awake X`).

**Non-Goals:** daily ranges (`HH:MM-HH:MM`) and `[loop] keep_awake` stay as they are; no new option; no change to how
`--until` ends a run; keep-awake by default (RB-006) is a separate, later change.

## Decisions

### D1. Turn the moment into the whole run once, at start

In `main()`, after both options are read and before the dispatcher starts (one place, so `run`, `once`, `plan` and
`dry-run` behave alike): if `until` is set, the keep-awake setting's mode is `until` and
`setting.until.timestamp() >= until`, replace it with a setting of mode `on` that keeps the given moment and text in a
new optional field (e.g. `given`, default `None`), used only for reporting. `wanted()` and `Keeper` are unchanged, so
the keeper runs as for `on` and stops with the run (`stop_keep_awake`; Windows drops the request with the process).

The replacement is a small pure helper (in `radark/awake.py` or `__main__.py`) so tests can call it directly. Only
`--keep-awake` can give a moment: the configured default cannot be one.

Comparison: both moments are whole local minutes from the same parsing, so "at or after" is a plain `>=` on the two
timestamps.

Alternatives:
- *Keep awake while any session runs, past every moment:* changes the meaning of an earlier moment that the owner
  chose on purpose (sleep allowed during the later part of a run). Rejected.
- *Only a warning at start:* the owner would still lose the session in an unattended night run. Rejected; the owner's
  intent for an equal or later moment is clear.
- *Make the keeper aware of the running session:* more state across threads for the same effect. Rejected.

### D2. Reporting

`keep_awake_text` gives `whole run (until 12:00 given, the run ends at 12:00)` for a replaced setting (both times
formatted like the existing `until` text). The `keep_awake_setting` log record has `mode: "on"`, `text` as given on
the command line and `until` as the given moment (so the record says both what was given and what applies). A goal
run's `goal_start.keep_awake` keeps the given text. `dry-run` prints the same text after `Would keep awake: `.

### D3. Documentation

`radark/README.md`: in "Keep awake", one paragraph on the combination with `--until` (equal or later moment → whole
run; earlier moment unchanged); in "Pause / stop", the example `run --until 12:00 --keep-awake` for "until 12:00
without sleep", noting that a running session can outlast the end time.

### D4. Spec text kept extendable

The delta keeps "Keeping the computer awake" as one paragraph with the end-time rule as its own last sentence and the
new scenarios next to "Until a moment", so RB-006 (keep-awake by default) can change the default sentence without
touching this rule.

## Assumptions (unattended session)

- Change name without the `harness-` prefix (`keep-awake-covers-until`), as the handover allows; the capability ID
  `harness-dispatcher` stays.
- The product draft's decisions are kept; checked against the current code (`main()` parses both options in one place
  for every command, `KeepAwake.mode` already has `on`), none needed changing. Only paths, commands and the neutral
  "Why" were updated.

## Risks / Trade-offs

- [The owner gives a later moment to have the computer sleep after it even if the run goes on] → unlikely with an end
  time before it (the run starts no new steps after the end time anyway); the start line names the change, so it is
  visible at once.
- [A run whose last session hangs keeps the computer awake longer] → bounded by `session_max_minutes` and the limit
  checks, the same as with bare `--keep-awake` today.

## Migration Plan

No stored state; takes effect on the next run. Rollback: revert the commit.
