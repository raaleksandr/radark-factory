# Proposal: `radark --version` (HO-20261117-c3hc)

Handover: HO-20261117-c3hc ("RB-029: radark --version flag"), from the product team.

## Why

`radark` has no version flag. The setup guide has to send a new user to `pip show radark-factory` or
`uv tool list`, or to the `dry-run` start summary, which needs a configuration and a hub, to learn which engine is
installed. A plain `radark --version` is the usual way to check an install.

## What Changes

- New top-level flag `--version` of `radark` / `python -m radark` (and the deprecated `python -m harness`). It
  prints two short lines on standard output and exits 0:
  ```
  radark 0.6.0
  ho: needs contract 1; found ho 0.2.0 (contract 1)
  ```
- It reads no configuration file, needs no subcommand, takes no lock, runs no hub command other than the `ho`
  version probe, and starts no session.
- The engine version comes from the installed package metadata of `radark-factory`; a source checkout (an
  editable install, or the working tree on `PYTHONPATH`) shows the version in its `pyproject.toml` and says
  `(source checkout)`; with neither, `unknown`.
- The second line probes `ho` on `PATH` (`ho --version --json`, a short time limit). A missing, too old,
  silent or incompatible `ho` is one note on that line; the exit code stays 0 (an info command, not a start
  check).
- `README.md` and `docs/setup.md` use `radark --version` to check the install instead of `pip show` /
  `uv tool list`; `radark/README.md` lists the flag under Commands.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirement "Version flag" (output, sources, exit code, no configuration, `ho`
  probe, alias).
- `setup-guide`: "Prerequisites and install in the guide" checks the installed engine with `radark --version`.

## Impact

- Code: `radark/__main__.py` (the flag), a small helper for the version lines (engine version, `ho` line), reusing
  `radark/hub.py` `check_ho` with an optional hub (no `HO_HUB` set when there is no configuration).
- Tests: new `radark/tests/test_version_flag.py` with the fake `ho`.
- Docs: `README.md`, `docs/setup.md`, `radark/README.md`.
- No new dependency (standard library `importlib.metadata`, `tomllib`); no configuration key changes.
