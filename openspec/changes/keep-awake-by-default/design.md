# Design

Change for HO-20261113-xk2k (RB-006).

## Context

See proposal.md - Why. The default lives in one place: `radark/config.py` reads `[loop] keep_awake` with
`loop.get("keep_awake", "off")`, and the `Config.keep_awake` field defaults to `KeepAwake()` (mode `off`).
`--keep-awake` replaces the configured value for one run (`radark/__main__.py` `main()`, after argument parsing), then
`cover_end_time` turns a moment at or after `--until` into the whole run (archived change `keep-awake-covers-until`).
`start_keep_awake` prints and logs nothing for `off`; otherwise it writes `keep_awake_setting`, then prints a `!` line
on a system without the Windows power API, or prints `Keep awake: ...` and starts the `Keeper` thread
(`SetThreadExecutionState` with `ES_SYSTEM_REQUIRED`). `dry-run` prints `Would keep awake: ...` for any mode but
`off`. A configuration without a `keep_awake` key gets the new default at once.

Tests build their config in `radark/tests/conftest.py` (`write_config`) without `keep_awake`; `test_keep_awake.py`
adds the key with `set_key`, which inserts a line after `[loop]` (a second `keep_awake` line would be a TOML error),
and has its own `fake_keeper` fixture that replaces `radark.__main__.Keeper` and sets `os.name` to `nt`. Most
dispatcher tests use the real `Keeper` only because the default is `off` today.

## Goals / Non-Goals

**Goals:** a run started without any keep-awake setting works through the night; one-off sleep stays one flag away;
the terminal says when keeping awake comes from the default.

**Non-Goals:** no new option or form; moments, ranges and the end-time cover unchanged; no change to the lid action,
the power button or the display timeout (the display still turns off; only idle sleep is blocked, as today); no
change to the screen-off script.

## Decisions

### D1. Change the default value, not the meaning of "not set"

Without the key, `[loop] keep_awake` gives `KeepAwake("on", text="on", default=True)`; the `Config.keep_awake` field
default is the same value. `KeepAwake` gets a field `default: bool = False` (reporting only, like `given`). A value
written in the configuration (`"on"` too) and any `--keep-awake` value are parsed as today, so `default` is `False`
for them. `keep_awake_text` adds ` (default; --keep-awake off lets the computer sleep)` to `whole run` when `default`
is set; the start line and `dry-run` both use it. Everything else downstream already handles `on`:
`keep_awake_setting` record (mode `on`, text `on`), goal `goal_start.keep_awake = "on"`, stop with the run. The log
record gets no new field: the note is for the owner at the console; the record's mode is what matters.

Alternatives:
- *A separate "unset" mode resolved to `on` at start:* an extra state with the same effect. Rejected.
- *Default to a daily range:* the owner asked for working runs in general, at night as well. Rejected.
- *`text="default"` as the marker (one of the draft's options):* would make `goal_start.keep_awake` read `default`,
  while the handover asks for `on`. Rejected in favor of a separate field.

### D2. Tests do not hold a real keep-awake request

The `env` fixture in `conftest.py` replaces the `Keeper` used by `radark.__main__` with a no-op fake (`start` and
`stop` doing nothing, `changes` reporting no change), so no test run blocks the test machine's sleep.
`test_keep_awake.py` keeps its own `fake_keeper` fixture, which replaces it again with a recording fake. Not done
through `keep_awake = "off"` in the written config, because `set_key` would then add a second key. Tests that compare
the full start or `dry-run` output get the new line where it now appears; `test_config_default_off` becomes
`test_config_default_on`, and a test covers `[loop] keep_awake = "off"` giving no keep-awake line, no record and no
keeper.

### D3. `--until 12:00` alone prints the default line

With the default `on` and `--until 12:00` alone, `cover_end_time` does nothing (it only changes mode `until`), so the
run keeps awake for the whole run, including a session that finishes after 12:00, and the start line is
`Keep awake: whole run (default; --keep-awake off lets the computer sleep)`; `dry-run` prints the same after
`Would keep awake:`. The note is printed rather than nothing extra, because the owner asked that every run keeping
awake by default says so, and `--until` is not a keep-awake setting. `--until 12:00 --keep-awake 12:00` keeps its
covered-moment line `Keep awake: whole run (until 12:00 given, the run ends at 12:00)` without the default note.

### D4. Order with `keep-awake-covers-until`

Both changes modify "Keeping the computer awake" and "Reporting keeping awake". That change is archived, and this
delta is written on top of the current main spec text, which includes its end-time sentence and scenarios. The
draft's task "check covers-until is applied" is therefore dropped.

### D5. Default on a system without the Windows power API

`start_keep_awake` today writes `keep_awake_setting` and prints one `!` line when the power API is missing. With `on`
as the default, every run on such a system would print a warning the owner never asked for. So for a setting with
`default` set, `start_keep_awake` on such a system prints nothing, writes no record and starts no keeper; an explicit
setting keeps today's behavior. Not in the draft; added so that the new default does not become a permanent warning.
`dry-run` is unchanged (it prints the setting as on Windows).

### D6. Documentation

`radark/README.md`: `[loop]` table `keep_awake` `"on"` (`"off"` lets the computer sleep); "Keep awake" opens with "by
default the dispatcher keeps the computer awake for the whole run and says so at the start; `--keep-awake off` (one
run) or `[loop] keep_awake = "off"` lets Windows put it to sleep as its power plan says" and lists the default start
line; "Screen off for the night" no longer presents keeping awake as something the owner has to turn on (it holds
unless keeping awake is turned off). `harness.toml.example`: `# keep_awake = "on"`.

## Risks / Trade-offs

- [A run left going on battery drains it, since idle sleep no longer stops it] → a low battery still puts the computer
  to sleep (the critical-battery action is not blocked); `--keep-awake off` for runs on battery.
- [An owner used to the old default is surprised the computer stays on] → the start line with the default note is
  printed in every such run, and the README states the change.
- [A hanging run keeps the computer awake longer] → bounded as today by `session_max_minutes`, the limit checks, and
  the run's end.
- [A configuration with `keep_awake = "on"` written out shows no note] → intended: the owner chose it explicitly.

## Migration Plan

No stored state; takes effect on the next run. To keep the old behavior, set `[loop] keep_awake = "off"`. Rollback:
revert the commit.
