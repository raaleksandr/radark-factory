# Design: start banner at run start

Handover HO-20261117-u2vc (RB-027).

## Context

`radark/__main__.py` `main()` handles `run`, `once` and `dry-run` along one path: configuration, `tee_console`
(run and once only), `check_ho`, the machine directory, `record_pipeline`, then
`print(config_mod.summary(...))` - the first line of the start output - and then `dry_run(d)` or the loop. Commands
`status` and `cockpit` return before the configuration is read; `note`, `escalations`, `clear`, `keep` and `plan`
return before the summary. Standard output in run and once mode is a `Tee` that copies to `console.log`.

## Goals / Non-Goals

**Goals:** a static ASCII banner printed once at the start of run, once and dry-run, before the summary, through
standard output; unchanged start output after it.

**Non-Goals:** colours, animation, a figlet dependency, a switch to turn it off, a banner for other commands,
writing `console.log` in dry-run.

## Decisions

### D1. The art is a constant in `radark/banner.py`

`BANNER: str` - lines joined with `\n`, no trailing newline - plus `def lines() -> list[str]`. A module of its own
keeps 20-odd lines of art out of `__main__.py` and lets tests import it. Kept as a Python raw string, so backslashes
in the letters and the smoke need no escaping; not a resource file, so no packaging change.

The art (drawn by hand at apply time):

- top: `RA DARK FACTORY` in block letters. 15 letters do not fit on one 80-column line in letters 6 columns wide,
  so the lettering takes two rows of letters: `RA DARK` on the first, `FACTORY` on the second (each row about 5-6
  lines high, letters about 5-7 columns wide plus a gap). The space between `RA` and `DARK` is a visible gap of at
  least one letter width.
- bottom: a factory - a building with a saw-tooth roof, windows and a door, two or three chimneys, smoke as `(`,
  `)`, `~` curls rising from them; about 8-10 lines.
- total at most 25 lines, every line at most 80 characters, no trailing spaces (stripped in the constant itself),
  characters 0x20-0x7E only (no tabs).

Alternative: lettering beside the factory - rejected: the letters alone already need most of the 80 columns.

### D2. Printed right before the summary

In `main()`, immediately before `print(config_mod.summary(cfg, ...))`: `print(banner.BANNER)`. This is the one
point all of run, once and dry-run pass just before their start output, after every check that refuses a start with
exit 2 before any start output (configuration, `ho` contract, hub lock, machine directory). So a refused start shows
only its error, and `plan` (which returns earlier) shows nothing new. `check_owner` runs after the summary today and
still does: its error follows the banner and the summary, as it follows the summary now.

`print` writes to `sys.stdout`, which in run and once mode is the `Tee`: the banner lands in `console.log` after the
start's header line without extra code (the handover asks for "the same output path").

The deprecated alias `harness` runs the same `main()`: it prints the banner too (its stdout must equal `radark`'s,
`test_alias.py`).

### D3. Dry-run keeps writing no `console.log`

The handover says the banner appears "in the window and in the run's `console.log`" for run and also dry-run. Today
dry-run does not tee to `console.log`, the spec keeps read-only modes from changing it, and the handover also says
nothing else in the start output changes. Assumption (unattended propose, recorded here and as a comment on the
handover): in dry-run the banner appears in the window only; `console.log` gets it in run and once mode. Product can
check `console.log` with `radark once` on the sandbox. If product wants dry-run to write `console.log`, that is a
separate item.

### D4. Tests

New `radark/tests/test_banner.py`:

- form: every line of `banner.lines()` consists of characters 0x20-0x7E, is at most 80 long, has no trailing space;
  at most 25 lines; the constant has no tab and no carriage return.
- lettering: a known line of the letter rows (a fixed string from the constant); the factory: a chimney row and a
  smoke character present (a loose check, so redrawing the smoke does not break it).
- `dry-run` with the existing fake `ho` fixtures: stdout starts with the banner followed by a newline, the banner
  occurs exactly once, and the line after it is the summary's first line; existing dry-run assertions still pass.
- `once` with the fake `claude`: `console.log` has the header line, then the banner lines, then the summary.
- `plan`, `escalations` and a start refused by a configuration error print no banner line.

Existing start-output tests must pass unchanged; any that compare whole stdout of run or dry-run and break only
because of the leading banner are adjusted to strip it with one shared helper, and listed in the apply notes.

## Risks / Trade-offs

- [Tests that assert on the very first stdout line of run or dry-run] -> grep for them at apply; strip the banner
  with one helper rather than weakening assertions.
- [The owner dislikes the art] -> experiment by design; one constant and one call to remove.
- [Wide letters overflow 80 columns] -> the form test fails; the art is fixed before commit.
