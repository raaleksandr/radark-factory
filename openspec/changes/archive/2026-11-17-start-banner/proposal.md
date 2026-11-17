# Proposal: start banner at run start

Handover: **HO-20261117-u2vc** (RB-027, "start banner - RA DARK FACTORY ASCII art at run start"), from
`radark-product`. An experiment requested by the owner.

## Why

When a run starts, the window shows the configuration summary right away, and nothing marks the start of a new run
at a glance - in the window or when scrolling back through `console.log`, which collects many starts. The owner
wants a striking picture at the start of every run: the name of the factory in big letters and a drawing of a
factory with smoking chimneys.

## What Changes

- New static ASCII banner: the lettering **RA DARK FACTORY** in big block letters (with the space in "RA DARK", as
  the owner wrote it) and, below or beside it, a factory building with chimneys and smoke.
- Plain printable ASCII only (0x20-0x7E), no line longer than 80 characters, no trailing spaces, at most 25 lines;
  no colours, no animation, no new dependency (the art is a constant in a small module of its own).
- Printed once per start by `run`, `once` (and `run --once`) and `dry-run` (and `run --dry-run`), immediately
  before the existing start output (the configuration summary). Everything after it is unchanged: same lines, same
  order.
- It goes through standard output like the other start lines, so in run and once mode it also lands in
  `console.log` (after the header line of that start).
- Not printed by `plan`, `status`, `cockpit`, `escalations`, `clear`, `keep`, `note` or `test-slot`, and not when the
  start stops before the summary (configuration error, incompatible `ho`, machine error).
- No switch to turn it off (experiment; a later item may remove it or add one).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: a new requirement *Start banner* - the banner printed at the start of run, once and
  dry-run, its form (ASCII, width, height) and where it appears (window, `console.log`).

## Impact

- New module `radark/banner.py` (the art constant); one call in `radark/__main__.py` before the summary print.
- New tests in `radark/tests/` (banner form; `run`, `once`, `dry-run` output start with it; `console.log`; other
  commands do not print it). Existing start-output tests must pass unchanged.
- `radark/README.md`: one sentence on the start banner.
- No change to the run log, the state, the hub, the cockpit or the `ho` contract.
