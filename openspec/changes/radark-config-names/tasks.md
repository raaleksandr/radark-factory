# Tasks: radark-config-names (HO-20261114-upfg)

Archiving this change and syncing its specs are not tasks here: that is a separate phase after the author closes
the handover. `ho done` is the last step.

## 1. Golden baseline

- [ ] 1.1 Run `python -m pytest radark/tests/test_workflow_golden.py radark/tests/test_prompts.py` before any code
      change and note the result (the golden prompts must stay byte-for-byte the same for an explicit `run_dir`).

## 2. Resolution in `config.py` (design D1-D4)

- [ ] 2.1 Add `resolve_path(arg, cwd)`: explicit path as given; else `radark.toml`, else `harness.toml` with a legacy
      note; both -> `ConfigError` naming both files; neither -> `ConfigError` naming `radark.toml`.
- [ ] 2.2 In `load()`: explicit `run_dir` as today; else `.radark`, fallback `.harness` with a legacy note, both ->
      `ConfigError` naming both directories.
- [ ] 2.3 Add `Config.notes` (tuple of legacy lines) and a `legacy_note` argument to `load()`.
- [ ] 2.4 Messages: the `ho` contract message in `config.py` and the one in `hub.py` name the configuration file
      actually read (or "the configuration file" where unknown); module docstring of `config.py`.

## 3. CLI in `__main__.py`

- [ ] 3.1 `--config` default `None`, resolved through `resolve_path` before anything else; ambiguity and missing file
      exit 2 with "Configuration error: ..." before the `ho` check and before any session. Update help and the
      module docstring.
- [ ] 3.2 Print `cfg.notes` once with the start lines of `run` / `once` and at the top of `dry-run` and `plan`.
- [ ] 3.3 `status`: same resolution; a resolution error goes to the existing "not read" path (design D1).

## 4. Machine-wide layer (design D5)

- [ ] 4.1 Confirm no record format change is needed; add tests: a record whose configuration path has the old name is
      another pipeline for an instance with a new-name path; the same resolved path is the same pipeline.

## 5. Names everywhere (design D6)

- [ ] 5.1 `git mv harness.toml.example radark.toml.example`; `run_dir` line becomes a comment with the new default.
- [ ] 5.2 `radark/sandbox/make_sandbox.py`: write `radark.toml` without `run_dir`; update docstring and printed command.
- [ ] 5.3 `.gitignore`: add `radark.toml` and `.radark/`, keep the old entries.
- [ ] 5.4 README, `radark/README.md` (configuration section, examples, the `run_dir` default, the `ho` error table,
      new "Migrating from harness.toml / .harness/" section) and `CLAUDE.md` (sandbox command).
- [ ] 5.5 Check workflow templates, hooks and prompts for a hard-coded run directory name; the run directory in prompts
      must be the resolved one (add a test that a prompt naming `<run_dir>/tmp/<team>/` uses `.radark` by default).
- [ ] 5.6 Test fixtures (`radark/tests/conftest.py`) write `radark.toml`; update `test_ho_check.py` for D4.

## 6. Tests for the resolution cases

- [ ] 6.1 `test_config.py`: new names only; old names only (fallback + both notes); both configuration files (error
      naming both); both run directories (error naming both); explicit `--config` with an old name (no note);
      explicit `run_dir = ".harness"` (used as is, no note); neither file (error naming `radark.toml`); the old file
      and directory still exist afterwards.
- [ ] 6.2 CLI-level test: both configuration files -> exit 2, no `ho` call and no session (fake `ho` / `claude` record
      nothing); old names only -> `dry-run` output contains the legacy lines.

## 7. Verification

- [ ] 7.1 Sandbox: `python radark/sandbox/make_sandbox.py <dir>` then `dry-run` from `<dir>` with the new names, and
      again after renaming to `harness.toml` / `.harness/`; record the start lines (with neutral paths) in the notes
      below.
- [ ] 7.2 Golden prompts unchanged for the explicit-`run_dir` fixtures; list any intended difference.
- [ ] 7.3 Grep the repository for `harness.toml` / `.harness` and record what remains and why (legacy fallback code,
      tests, migration docs, `.gitignore`, archived changes).
- [ ] 7.4 Full suite `python -m pytest radark/tests` passes; failing or flaky tests follow hub `AGENTS.md` section 10
      and are reported in the result.
- [ ] 7.5 Check the diff for private data (owner paths, product or company names, hub or run excerpts); commit locally
      only (no push, tag, release or reinstall), commit messages cite HO-20261114-upfg.

## 8. Report

- [ ] 8.1 `ho done HO-20261114-upfg -m "..."` listing the commits, the resolution rules as implemented, what changes
      for a running pipeline with `harness.toml` and `run_dir = ".harness"` (expected: nothing but wording), new or
      changed settings (`--config` default; none in the file), the sandbox start lines, the grep result and the test
      result.

## Notes

- Assumptions made without the owner (design): environment variable names (`HARNESS_*`) stay unchanged as out of
  scope; `status` keeps its read-only "not read" behaviour on ambiguity instead of exiting 2; the example file is
  renamed without keeping a legacy copy; no split of the change.
