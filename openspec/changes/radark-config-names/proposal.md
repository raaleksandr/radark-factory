# Proposal: `radark.toml` / `.radark/` with a fallback to `harness.toml` / `.harness/`

Handover: **HO-20261114-upfg** (RB-013, "radark.toml / .radark/ with fallback to harness.toml / .harness/"), from
`radark-product`. Follows HO-20261113-6cg3 (module rename `harness` → `radark`), which left the configuration file
and run directory names for later (requirement "Configuration and run file names unchanged by the rename").

## Why

The package and the command are `radark`, but a pipeline is still configured in `harness.toml` and keeps its run
state in `.harness/`. New pipelines should use names that match the product, while pipelines that already run with
the old names must keep working after an upgrade with no file moves and no edits.

## What Changes

- **Configuration file resolution.** `--config` has no fixed default any more. Without `--config` the dispatcher
  uses `radark.toml` in the current directory if it exists, else the legacy `harness.toml` if it exists. If **both**
  exist it stops before anything else (exit 2) with a message naming both files. An explicit `--config <path>` is
  used as given, whatever its name. With neither file the error names `radark.toml` (and says `harness.toml` was not
  found either).
- **Run directory resolution.** An explicit `run_dir` in the configuration always wins, unchanged. Without `run_dir`:
  `.radark/` next to the configuration file; if `.radark/` does not exist but `.harness/` does, `.harness/` (legacy).
  If both exist and `run_dir` is not set: exit 2 with a message naming both directories.
- **Legacy note.** When a fallback picks an old name, the start lines of `run` / `once` and the output of `dry-run`
  and `plan` carry one line saying so, with the new name to rename to. No note when the old name is set explicitly
  (`--config harness.toml`, `run_dir = ".harness"`).
- **No automatic migration.** The engine never moves, renames or deletes the old file or directory. The README gets
  a short manual migration section.
- **Everything that names them:** messages in `config.py` and `hub.py` ("fix 'ho' in <config file>" names the file
  actually read), CLI help, module docstrings, the example file (`harness.toml.example` → `radark.toml.example`), the
  sandbox (`make_sandbox.py` writes `radark.toml` and lets the run directory default to `.radark/`), `.gitignore`
  (both old and new names), README, `radark/README.md`, `CLAUDE.md`, and the specs. Prompts already use the run
  directory the dispatcher resolved; this is kept and covered by a test.
- **Spec:** the requirement "Configuration and run file names unchanged by the rename" is replaced by
  "Configuration file and run directory names" with the rules above.

Not changed: configuration keys, environment variable names given to sessions and hooks (`HARNESS_RUN_DIR`,
`HARNESS_PARALLEL_SESSIONS`, `HARNESS_TEST_SLOT`, …), the hub format and `radark-handover`, the machine-wide record
format.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: the configuration file and run directory name requirement (new defaults, legacy fallback,
  ambiguity stop, legacy note).

## Impact

- Code: `radark/config.py` (resolution of the file and the run directory, legacy notes), `radark/__main__.py`
  (`--config` default, start lines, `dry-run` / `plan` / `status`, help), `radark/hub.py` (message),
  `radark/sandbox/make_sandbox.py`, the example file, `.gitignore`.
- Tests: new cases in `radark/tests/test_config.py` and a CLI-level test; existing fixtures write an explicit
  `run_dir = "run"`, so the golden prompts do not change.
- A running pipeline that uses `harness.toml` with `run_dir = ".harness"` (started with `--config harness.toml` or
  from its directory with only `harness.toml` present): same file, same run directory, same prompts; only a one-line
  legacy note appears in the start lines when the configuration file itself was found by the fallback.
