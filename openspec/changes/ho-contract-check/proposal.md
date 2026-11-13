# Proposal: check `ho` compatibility at start

Handover: **HO-20261113-k2wq** (backlog item RB-003), from `radark-product`. The `ho` side (`ho --version` and its
JSON form) is asked of `radark-handover` in **HO-20261113-cbcj**, which references HO-20261113-k2wq.

## Why

The dispatcher calls `ho ... --json` and trusts the output shape. After a release of one package without the other,
a changed JSON shape, or an `ho` that is missing or too old, surfaces as a confusing failure hours into an unattended
run. The owner wants such a mismatch to stop the dispatcher at start, before any session, with one clear message.

## What Changes

- At start of `run`, `once`, `dry-run` and `plan`, before any other hub command and before any session, the
  dispatcher runs the configured `ho` (`ho = ...` in `harness.toml`) with `--version --json` and reads the package
  version and the JSON contract version.
- The contract versions the engine supports are one constant in the code (today exactly `1`).
- It **stops with one clear message** (exit code 2, no session, no lock, no `dispatcher_start` log event) when:
  - `ho` cannot be started (missing executable);
  - `ho` has no `--version` (non-zero exit or no usable JSON answer) — "too old";
  - `ho` does not answer within the time limit;
  - its contract version is not supported.
  The message names the `ho` command, the found versions (or that none were found), the needed contract version(s),
  and what to do (install a matching `radark-handover`, or a `radark-factory` that supports the found contract).
- A compatible `ho` adds one line to the start summary, e.g. `ho: 0.2.0 (contract 1)`.
- The fake `ho` in the tests answers `--version` (compatible by default; configurable to be old or wrong).
- `radark/README.md` documents the check, the line, the messages and the supported contract.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirements *Compatibility of ho* (start check, supported contract constant),
  *Stopping on an incompatible ho* (exit 2 with one message) and *Reporting the ho version* (start line).

## Impact

- `radark/hub.py`: the version probe and the supported-contract constant.
- `radark/config.py`: `summary()` takes an optional `ho` line.
- `radark/__main__.py`: the check in the start path of `run` / `once` / `dry-run` / `plan`.
- `radark/tests/fakes/fake_ho.py`: `--version` support; new tests for each case.
- `radark/README.md`.
- Depends on `radark-handover` shipping `ho --version --json` (HO-20261113-cbcj); its final shape decides the field
  names the engine reads. Until that release is installed, the real `ho` stops the dispatcher as "too old" — intended.
- No new config keys, no hub writes.
