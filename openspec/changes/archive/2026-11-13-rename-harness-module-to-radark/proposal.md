# Proposal: rename the Python package `harness` to `radark`

Handover: **HO-20261113-6cg3** (backlog item RB-002), from `radark-product`.

## Why

The product is called radark and its console script is `radark`, but the importable package is still `harness`, so
the owner types `python -m harness ...` and the console script points at `harness.__main__`. The import name should
match the product name, without breaking the commands, escalation texts and docs that name `python -m harness` today.

## What Changes

- The package moves from `harness/` to `radark/` (code, `hooks/`, `sandbox/`, `README.md`, tests); imports,
  `pyproject.toml` (console script `radark = "radark.__main__:main"`, package include/exclude, package data) and every
  place that builds a path to the package, its hooks or its sandbox script follow.
- A thin compatibility package `harness` stays: `python -m harness <args>` runs the same dispatcher with the same
  arguments, the same standard output and the same exit code; it prints one deprecation line to standard error.
  `import harness` and `from harness.<module> import ...` keep working too and give the same module objects as
  `radark` (see design D2).
- Texts the engine writes (escalation messages and the `clear` hint, the argparse program name and `--help`,
  `dry-run` output, the hooks-not-loaded hint, the sandbox hints) and the docs (`README.md`, the package README,
  `CLAUDE.md`, `docs/`) name `python -m radark` / `radark`, and say once that `python -m harness` is a deprecated alias
  kept for at least one release.
- **Not changed:** the config file name `harness.toml`, the run directory `.harness/`, the file
  `harness.toml.example`, configuration keys, the run log format.

No **BREAKING** change: every command that works today keeps working for at least one release.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `harness-dispatcher`: adds a requirement on the package and command names — the dispatcher is started as
  `python -m radark` or `radark`, `python -m harness` is a deprecated alias with identical results, and the texts
  the dispatcher writes name `python -m radark`.

## Impact

- Code: every module under `harness/` moves to `radark/`; new `harness/__init__.py` and `harness/__main__.py` (alias
  only); `pyproject.toml`; `radark/runner.py` (hook directory is resolved from the package, so it follows the move);
  `radark/prompts.py`, `radark/__main__.py`, `radark/sandbox/make_sandbox.py` (texts and paths).
- Tests: `harness/tests` moves to `radark/tests`; imports and `monkeypatch` targets change from `harness.` to
  `radark.`; new tests for the alias and the package paths. The test command becomes `python -m pytest radark/tests`.
- Docs: `README.md`, `radark/README.md`, `CLAUDE.md`, `docs/` where they name the command or the package path.
- Installed pipelines: none need a change. Hook commands are generated per session from the installed package
  (absolute paths), so team settings name no `harness/hooks` path; the owner's existing `python -m harness`
  commands keep working after installing the release.
