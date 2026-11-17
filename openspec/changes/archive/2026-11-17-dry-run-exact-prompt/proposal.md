# Proposal: dry-run prints the exact prompt a session gets

Handover: **HO-20261117-6i2k** (RB-017, "dry-run prints the exact work prompt, including the parallel note"), from
`radark-product`.

## Why

`dry-run` is how the owner sees what a session would be told. A real session start sends the phase prompt (or the
resume message after a time limit) followed by the parallel note when `parallel_sessions > 1` (and the test-slot
note when more than one session can run on the computer), but `dry-run` builds its prompt separately and prints
only the phase prompt. The printed prompt is therefore not the one the session gets, and the two code paths can
drift further apart.

## What Changes

- One helper builds the prompt of a session start for a work item (new phase session or resume after a time limit,
  plus the parallel and test-slot notes). The real start path and `dry-run` both use it, so the printed prompt is
  the same string the session would receive.
- `dry-run` with `parallel_sessions > 1` therefore prints the parallel note at the end of the prompt; with
  `parallel_sessions = 1` it prints nothing extra (as before), unless another dispatcher's session runs on the
  computer, in which case the test-slot note appears there too, as it would in the real prompt.
- `dry-run` stays read-only: building the prompt for it MUST NOT change the state (today the real path drops a
  review's stored, not-escalated denials while it builds the prompt).
- The fresh-session fallbacks (resume failed) and the owner-answer path already append the note; `dry-run` does
  not print them, so they get no new output.
- No other change to `dry-run` output: same lines, same order.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Dry run with parallel sessions* - the prompt `dry-run` prints is exactly the prompt the
  session would get, including the parallel note when more than one session is allowed.

## Impact

- `radark/__main__.py`: a prompt helper on `Dispatcher` used by `run_candidate` and `dry_run`; `work_prompt`
  gets a read-only mode.
- Tests in `radark/tests/test_parallel.py` (and `test_machine.py` for the test-slot note if needed).
- No change to the run log, the state format, the hub, the cockpit or the `ho` contract.
