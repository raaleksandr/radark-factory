# Proposal: machine-wide layer for several dispatcher instances

Handover: **HO-20261114-cda3** (RB-001, "several pipeline instances on one PC"), from `radark-product`. Builds on
the archived change `parallel-sessions` (HO-20261114-wwqw), which handled several sessions inside one dispatcher
and left several dispatcher instances out (its D9).

## Why

One PC runs one pipeline at a time today. Every dispatcher instance (one `harness.toml` and its run directory) keeps
its own usage record, its own session count, its own keep-awake and its own run lock. Two instances started at once
(for example `pipeline-a` and `pipeline-b`) both draw from one Claude account but each sees only its own usage
readings, together start more sessions and full test runs than the machine carries, and may both work in the same
team repository. The owner wants to run several pipelines on one PC safely.

## What Changes

- **Machine directory**: a per-user directory outside every run directory and repository, shared by all instances
  of the same OS user (`%LOCALAPPDATA%\radark\machine` on Windows, `$XDG_STATE_HOME/radark/machine` or
  `~/.local/state/radark/machine` elsewhere; overridden by `RADARK_MACHINE_DIR` for tests and sandboxes).
- **Machine limits** in one file the owner edits once, `<machine dir>/machine.toml` (`[machine] sessions = 2`,
  `test_runs = 1` by default); 0, negative or non-integer values are refused at start (exit 2). Example file
  `machine.toml.example`.
- **Shared usage**: five-hour / seven-day readings from any instance's sessions update one machine-wide record; the
  usage hold, the run budget (`--budget-5h/7d`, still per run) and the threshold check before every start use the
  newest reading of all instances. A usage-limit hit seen by one instance holds new starts in all instances until
  the reset.
- **Machine session limit**: before an instance starts a work session or a whole-hub step (idle ask, goal check) it
  takes a machine session slot in addition to its own `parallel_sessions` place; at the limit it waits with a
  console line naming the reason and starts when a slot frees.
- **Machine test-run limit**: a new command `python -m radark test-slot -- <command>` (in sessions also on `PATH`
  as `radark-test-slot`) runs a full test suite while holding a machine test-run slot; sessions get a prompt note
  and the team `CLAUDE.md` guidance tells agents to run full suites through it.
- **One repository, one instance**: a team repository (resolved path, case-insensitive on Windows) belongs to at most
  one running instance; a second instance whose configuration contains it refuses at start (exit 2) naming the
  repository and the other instance's configuration path. `dry-run` and `status` are not blocked and show the
  conflict.
- **Crash safety**: every machine-layer claim is an OS file lock released when the process dies; records next to the
  locks (PID, process start time, configuration path) are only informative and treated as stale when their lock is
  free.
- **Keep-awake**: no new machinery; Windows combines `SetThreadExecutionState` requests of all processes, which is
  documented and checked; each instance's sleep watch and wake grace stay as they are.
- **Visibility**: a new read-only command `python -m radark status` (machine directory, limits, other running
  instances with configuration path and sessions running, slots in use, shared usage reading, repository conflicts
  of this configuration); the start lines and `dry-run` show the other instances and the machine limits.
- A single instance with today's configuration behaves as today, except that it reads and writes the shared usage
  record and holds machine-layer locks.

## Capabilities

### New Capabilities

None. The behaviour belongs to the dispatcher, like the requirements of `parallel-sessions`.

### Modified Capabilities

- `harness-dispatcher`: new requirements for the machine directory and limits, shared usage, the machine session
  and test-run limits, repository ownership across instances, crash release, keep-awake with several instances and
  the `status` command.

## Impact

- Code: new `radark/machine.py` (directory, OS locks, slots, instance and repository records, shared usage, the
  `test-slot` command); `radark/__main__.py` (start order, loop waits, usage decisions, `status`, `dry-run` lines);
  `radark/runner.py` (`session_env`: `RADARK_MACHINE_DIR`, `HARNESS_TEST_SLOT`, `PATH`); `radark/prompts.py`
  (test-slot note); `radark/config.py` unchanged except for reporting.
- Files: `machine.toml.example`, README sections (root and `radark/README.md`), team `CLAUDE.md` guidance in the
  README, sandbox (`radark/sandbox/make_sandbox.py`) gets a machine directory per sandbox.
- Tests: new `radark/tests/test_machine.py` and dispatcher tests with two instances on one temporary machine
  directory; fake `ho` / `claude` only.
- No change to `ho`; nothing in the machine layer assumes one hub or one `ho` install.
