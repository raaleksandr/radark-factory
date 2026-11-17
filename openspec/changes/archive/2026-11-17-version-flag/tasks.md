# Tasks: `radark --version` (HO-20261117-c3hc)

## 1. Probe and version lines

- [x] 1.1 In `radark/hub.py`, split `check_ho` into `probe_ho(cmd, hub, timeout, supported) -> HoProbe` (kind `ok`
  / `missing` / `timeout` / `old` / `unsupported`, version, contract, features) and `check_ho`, which formats the
  existing messages from it unchanged; allow `hub=None` (leave `HO_HUB` as in the environment, still drop
  `HO_TEAM`) (design D3)
- [x] 1.2 Add `radark/version.py`: `engine_version()` (source checkout `pyproject.toml` next to the package, else
  `importlib.metadata.version("radark-factory")`, else `unknown`; design D2), `HO_COMMAND = ["ho"]` resolved with
  `shutil.which` at call time, and `lines()` giving the two lines of design D1 with a 10 s probe limit
- [x] 1.3 In `radark/__main__.py` `main()`, add the top-level `--version` as a custom `argparse.Action` (`nargs=0`)
  that prints `version.lines()` and exits 0 before the subcommand check and before any configuration is read
  (design D4)

## 2. Tests

- [x] 2.1 Add `radark/tests/test_version_flag.py` (fake `ho` through `radark.version.HO_COMMAND`): compatible `ho`
  → both lines exactly, exit 0; output and exit code of `main(["--version"])`
- [x] 2.2 Works in an empty directory (no `radark.toml` / `harness.toml`), and with `--config <missing file>
  --version`: exit 0, no configuration error, no run directory created, no `ho` call other than `--version`
- [x] 2.3 `ho` missing → `no ho found on PATH`, exit 0; too old (exit 1 / no version) → `without a usable
  --version (too old)`, exit 0; unsupported contract `2` → `found ho 0.9.0 (contract 2), not supported`, exit 0;
  no answer within the limit → the timeout phrase, exit 0
- [x] 2.4 Engine version: installed metadata (monkeypatched `importlib.metadata.version`, no `pyproject.toml`
  beside the package), source checkout (a temporary `pyproject.toml` with `name = "radark-factory"`), a
  `pyproject.toml` of another project is ignored, neither → `unknown`
- [x] 2.5 `python -m harness --version` in a subprocess: same stdout as `python -m radark --version`, exit 0, one
  deprecation line on stderr
- [x] 2.6 `radark/tests/test_ho_check.py` passes unchanged (start-check messages are the same)

## 3. Docs and checks

- [x] 3.1 `docs/setup.md` Install check: `radark --version` instead of `pip show radark-factory` / `uv tool list`;
  replace the "has no `--version` flag" sentence (design D5)
- [x] 3.2 `README.md` Quick start: a `radark --version` line after the install line; `radark/README.md` Commands:
  `python -m radark --version`, and one sentence in "Compatibility of `ho`" (design D5)
- [x] 3.3 Manual check: `python -m radark --version` from the working tree, and from an empty temporary directory
  with the working tree on `PYTHONPATH`; record both outputs (neutral, no owner paths) in the notes below
- [x] 3.4 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped; record the number of tests
- [x] 3.5 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [x] 3.6 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-c3hc -m "<summary>"`, naming the test count and the assumptions below

## Notes

- Assumptions (unattended propose, 2026-11-17), recorded in design.md:
  - the second line names the needed JSON contract, not a minimum `ho` release (`ho >= 0.2.0` in the handover's
    example) — the engine checks contracts (D1);
  - a source checkout is recognised by a radark-factory `pyproject.toml` next to the package and shows
    `(source checkout)` (D2);
  - the flag probes `ho` on `PATH` (no configuration is read) with a 10 s limit (D3);
  - no `--version --json` and no per-subcommand `--version` (Non-Goals).
- Manual check (task 3.3), 2026-11-17, `ho` 0.2.0 on `PATH`:
  - from the working tree: `python -m radark --version` printed `radark 0.5.0 (source checkout)` and
    `ho: needs contract 1; found ho 0.2.0 (contract 1)`, exit 0;
  - from an empty temporary directory with the working tree on `PYTHONPATH`: the same two lines, exit 0, the
    directory stayed empty; `--config <missing file> --version run` and `python -m harness --version` the same
    (the alias adds its one deprecation line on stderr).
- Apply decisions: `check_ho` delegates to the new `probe_ho` (`radark/hub.py`); a probe that cannot start the
  resolved `ho` is reported as `no ho found on PATH`, like one not found by `shutil.which`. `main(["--version"])`
  exits through `SystemExit(0)` like argparse's `--help`.
- Full suite (task 3.4), 2026-11-17: `radark-test-slot python -m pytest radark/tests`: 1086 passed in 562 s. An
  earlier run was stopped from outside by the session's 10-minute background limit at about 80 %; every test after
  that point failed on the fake `ho` (`ho inbox failed`), an aborted environment, not a test result; the clean
  rerun above passed in full.
