# Proposal: ship the example configurations with the package (HO-20261117-nymh)

Handover: HO-20261117-nymh ("RB-031: ship radark.toml.example and machine.toml.example with the package"), from
the product team.

## Why

`radark.toml.example` and `machine.toml.example` live only in the repository root. A user who installed radark
from git (or later from PyPI) has no example file: `docs/setup.md` says "it is not installed with the package" and
links to the repository copy, so a setup from zero needs a clone or a browser.

## What Changes

- Both examples move into the package, `radark/examples/radark.toml.example` and
  `radark/examples/machine.toml.example`, and become package data. These are the only copies: the root copies are
  removed (one source of truth, no two hand-kept files that can drift); every link points to the new place.
- New subcommand `radark example-config` (also `python -m radark` / `python -m harness`): prints the example
  `radark.toml` to standard output; `--machine` prints the example `machine.toml` instead; `-o FILE` writes it to
  `FILE` and refuses (exit 2, file untouched) when `FILE` exists unless `--force` is given; `--path` prints the
  installed file's path instead of its content. It reads no configuration, takes no lock, runs no hub command and
  starts no session.
- `docs/setup.md`, `README.md` and `radark/README.md` tell the user `radark example-config -o radark.toml` (and
  `--machine`) instead of "in the repository; it is not installed with the package" / `copy radark.toml.example`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirements "Example configuration command", "Writing an example file" and "Example configurations are
  package data".
- `setup-guide`: "Configuration and first dry run in the guide" gets the example file with
  `radark example-config`, not from the repository.

## Impact

- Files: `radark.toml.example`, `machine.toml.example` move (`git mv`) to `radark/examples/`.
- Code: `radark/__main__.py` (the subcommand, handled before any configuration is read), a small
  `radark/examples.py` helper (`importlib.resources`).
- Packaging: `pyproject.toml` `[tool.setuptools.package-data]` adds `examples/*.toml.example`.
- Tests: new `radark/tests/test_example_config.py`.
- Docs: `docs/setup.md`, `README.md`, `radark/README.md`.
- No new dependency (standard library `importlib.resources`); no configuration key changes.
