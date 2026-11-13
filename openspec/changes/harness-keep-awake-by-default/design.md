# Design

## Context

See proposal.md - Why. The default lives in one place: `harness/config.py` reads `[loop] keep_awake` with
`loop.get("keep_awake", "off")` and the `Config.keep_awake` field defaults to `KeepAwake()` (mode `off`). `--keep-awake`
replaces the configured value for one run (`harness/__main__.py`, after argument parsing); `start_keep_awake` prints
and logs nothing for `off` and otherwise starts the `Keeper` thread (`SetThreadExecutionState` with
`ES_SYSTEM_REQUIRED`). The owner's `harness.toml` has no `keep_awake` key, so the new default applies to it at once.

Tests build their config in `harness/tests/conftest.py` (`write_config`) without `keep_awake`; `test_keep_awake.py`
adds the key with `set_key`, which inserts a line after `[loop]` (a second `keep_awake` line would be a TOML error).
Most dispatcher tests use the real `Keeper` only because the default is `off` today.

## Goals / Non-Goals

**Goals:** a run started without any keep-awake setting works through the night; one-off sleep stays one flag away.

**Non-Goals:** no new option or form; moments and ranges unchanged; no change to the lid action, the power button or
the display timeout (the display still turns off; only idle sleep is blocked, as today); no change to
`scripts/screen-off.ps1`.

## Decisions

### D1. Change the default value, not the meaning of "not set"

`[loop] keep_awake` defaults to `"on"` (`loop.get("keep_awake", "on")` and the `Config.keep_awake` field default
`KeepAwake("on", text="on")`). Everything downstream already handles `on`: start line `Keep awake: whole run`,
`keep_awake_setting` record, `dry-run` line, goal `goal_start.keep_awake = "on"`, stop with the run.

Alternatives:
- *A separate "unset" mode resolved to `on` at start:* an extra state with the same effect. Rejected.
- *Default to a daily range:* the owner asked for working runs in general, at night as well. Rejected.

### D2. Tests do not hold a real keep-awake request

The `env` fixture in `conftest.py` replaces the `Keeper` used by `harness.__main__` with a no-op fake (as
`FakeKeeper` in `test_keep_awake.py`, which keeps its own fixture), so no test run blocks the test machine's sleep and
no test depends on Windows. Not done through `keep_awake = "off"` in the written config, because `set_key` would then
add a second key. Tests that compare the full start output get the new `Keep awake: whole run` line where it now
appears; `test_config_default_off` becomes `test_config_default_on`, and a test covers `[loop] keep_awake = "off"`
giving no keep-awake line and no record.

### D3. Order with `harness-keep-awake-covers-until`

Both changes modify the requirements "Keeping the computer awake" and "Reporting keeping awake". This delta is written
on top of that change's text (it includes the end-time sentence and scenarios), so `harness-keep-awake-covers-until`
is to be applied and archived first; archiving this one first would put not-yet-built end-time behavior into the main
spec. With the new default, `run --until 12:00` alone already keeps the whole run awake; the covers-until change still
matters for `--keep-awake 12:00` given explicitly.

### D4. Documentation

README: `[loop]` table `keep_awake` `"on"`; "Keep awake" opens with "by default the dispatcher keeps the computer
awake for the whole run; `--keep-awake off` (one run) or `[loop] keep_awake = "off"` lets Windows put it to sleep as
its power plan says"; the "Screen off for the night" paragraph drops "with keeping awake on" as a condition the owner
has to add. `harness.toml.example`: `# keep_awake = "on"`.

## Risks / Trade-offs

- [A run left going on battery drains it, since idle sleep no longer stops it] → a low battery still puts the computer
  to sleep (Windows critical-battery action is not blocked); `--keep-awake off` for runs on battery.
- [An owner used to the old default is surprised the computer stays on] → the start line `Keep awake: whole run` is
  printed in every such run, and the README states the change.
- [A hanging run keeps the computer awake longer] → bounded as today by `session_max_minutes`, the limit checks, and
  the run's end.

## Migration Plan

No stored state; takes effect on the next run. To keep the old behavior, set `[loop] keep_awake = "off"`. Rollback:
revert the commit.
