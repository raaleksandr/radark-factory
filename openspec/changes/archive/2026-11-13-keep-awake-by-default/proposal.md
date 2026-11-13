# Proposal: keep the computer awake for the whole run by default

Handover: **HO-20261113-xk2k** (backlog item RB-006), from `radark-product`. Based on the product team's draft
`harness-keep-awake-by-default`, updated to the current code (package `radark`) and written on top of the archived
change `keep-awake-covers-until` (HO-20261113-aidk).

## Why

The owner almost always starts a run to have it work, and rarely to let the computer sleep during it. Today keeping
awake is off unless `--keep-awake` or `[loop] keep_awake` says otherwise, so a run started without the flag can stop at
the first idle sleep: the screen turns black after a few minutes of no input, and without keeping awake the computer
may then enter standby (see the README "Keep awake" note). The safe choice has to be spelled out every time, and the
one-off choice ("let it sleep") is the default.

## What Changes

- **BREAKING (default behavior):** with neither `--keep-awake` nor `[loop] keep_awake`, a run (plain, one-shot or goal
  run) keeps the computer awake for the whole run, as with `--keep-awake on` today.
- Letting the computer sleep stays available: `--keep-awake off` for one run, `[loop] keep_awake = "off"` to restore
  the old default. Moments, daily ranges and the end-time cover (`keep-awake-covers-until`) are unchanged.
- The terminal says so in every run that keeps awake by default (owner decision 2026-11-13): the start line reads
  `Keep awake: whole run (default; --keep-awake off lets the computer sleep)` and `dry-run` prints `Would keep awake:
  whole run (default; --keep-awake off lets the computer sleep)`; an explicit `on` (option or configuration) keeps
  today's line without the note. `--until 12:00` alone also gets the default line (design D3). The
  `keep_awake_setting` record now appears in a run started without the option.
- On a system without the Windows power API, the default prints no `!` line and keeps nothing; an explicit setting
  still prints the `!` line (design D5).
- `harness.toml.example` and `radark/README.md` (`[loop]` table, "Keep awake", "Screen off for the night") state the
  new default and how to turn it off.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "Keeping the computer awake" (default is the whole run; `off` lets the computer sleep),
  "Keeping awake not available" (no warning for the default) and "Reporting keeping awake" (start line and `dry-run`
  without the option).

## Impact

- `radark/awake.py` (`KeepAwake` gets a flag marking a setting that comes from the default), `radark/config.py`
  (default of `[loop] keep_awake`), `radark/__main__.py` (`keep_awake_text` note, `start_keep_awake` on a system
  without the power API).
- Tests: `radark/tests/test_keep_awake.py` (default now `on`), `radark/tests/conftest.py` (the `env` fixture replaces
  the real keeper, so no test holds a real Windows keep-awake request), and tests that compare full start or
  `dry-run` output.
- `harness.toml.example`, `radark/README.md`.
