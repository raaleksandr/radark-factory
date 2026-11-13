# Proposal

## Why

The owner almost always starts a run to have it work, and rarely to let the computer sleep during it. Today keeping
awake is off unless `--keep-awake` or `[loop] keep_awake` says otherwise, so a run started without the flag can stop at
the first idle sleep: the screen turns black after about 5 minutes of no input, and without keeping awake the computer
may then enter standby (see the README "Keep awake" note on the display-off of 2026-11-08). The safe choice has to be
spelled out every time, and the one-off choice ("let it sleep") is the default.

## What Changes

- **BREAKING (default behavior):** with neither `--keep-awake` nor `[loop] keep_awake`, a run (plain, one-shot or goal
  run) keeps the computer awake for the whole run, as with `--keep-awake on` today.
- Letting the computer sleep stays available: `--keep-awake off` for one run, `[loop] keep_awake = "off"` to restore
  the old default. Moments and daily ranges are unchanged.
- The start line `Keep awake: whole run` and the `keep_awake_setting` record now appear in a run started without the
  option; `dry-run` without the option prints `Would keep awake: whole run`.
- `harness.toml.example` and the README (`[loop]` table, "Keep awake") state the new default and how to turn it off.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "Keeping the computer awake" (default is the whole run; `off` lets the computer sleep) and
  "Reporting keeping awake" (start line and `dry-run` without the option).

## Impact

- `harness/config.py` (default of `[loop] keep_awake`), `harness/awake.py` only if the `KeepAwake()` default is used
  as "not set" somewhere.
- Tests: `harness/tests/test_keep_awake.py` (default now `on`), and the shared test setup so that other dispatcher
  tests do not hold a real Windows keep-awake request (fake keeper or `keep_awake = "off"` in the test config).
- `harness.toml.example`, `harness/README.md`.
- Depends on `harness-keep-awake-covers-until` for the text of the same requirement (see design D3).
- The assistant's memory rule "keep awake only on request" no longer fits after this change and is to be updated.
