# Tasks: ship the example configurations with the package (HO-20261117-nymh)

## 1. Package data

- [ ] 1.1 `git mv radark.toml.example radark/examples/radark.toml.example` and the same for
  `machine.toml.example`; no copy stays in the root (design D1)
- [ ] 1.2 `pyproject.toml` `[tool.setuptools.package-data]` `radark`: add `"examples/*.toml.example"`
- [ ] 1.3 Update comment lines inside both example files that say how to get / copy them to name
  `radark example-config` (`--machine`); settings unchanged (design D4)

## 2. Command

- [ ] 2.1 Add `radark/examples.py`: `NAMES`, `read(kind) -> bytes`, `path(kind) -> Path` through
  `importlib.resources` (design D3)
- [ ] 2.2 In `radark/__main__.py`, add the `example-config` subparser (`--machine`, `-o FILE`, `--force`, `--path`)
  and dispatch it before any configuration, lock or `ho` call; behaviour and messages per the design D2 table
  (exclusive create unless `--force`, bytes as stored, stdout through `sys.stdout.buffer`)

## 3. Tests

- [ ] 3.1 Add `radark/tests/test_example_config.py`: a copy of the `radark` package (without `tests`) in a temporary
  directory, `python -m radark example-config` / `--machine` / `--path` in a subprocess with only that copy on
  `PYTHONPATH` and an empty working directory: output equals the packaged file, `--path` is inside the copy
- [ ] 3.2 `-o`: writes the exact bytes; existing file → exit 2, content unchanged, message names the file and
  `--force`; `--force` replaces; missing parent directory → exit 2; `--path` with `-o` and `--force` without `-o` →
  exit 2; `--config <missing file>` still works and no run directory is created
- [ ] 3.3 Documented copy is the packaged one: example links in `docs/setup.md`, `README.md`, `radark/README.md`
  resolve to `radark/examples/<name>`, byte-equal to `examples.read()`; no root `*.toml.example` exists or is linked;
  `pyproject.toml` package data matches both files
- [ ] 3.4 `python -m harness example-config`: same standard output and exit code as `python -m radark`

## 4. Docs and checks

- [ ] 4.1 `docs/setup.md` section 5 and the `machine.toml` sentence (design D4)
- [ ] 4.2 `README.md` Quick start and the `machine.toml.example` link; `radark/README.md` Setup step 2,
  "Machine limits" and Commands (design D4)
- [ ] 4.3 Wheel check: `python -m pip wheel . --no-deps -w <temp dir>` (if the isolated build fails offline, retry
  with `--no-build-isolation`), list the wheel with `zipfile` for both `radark/examples/*.toml.example`; record the
  command and result in the notes below (neutral, no owner paths); if no build is possible, record the error
- [ ] 4.4 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped; record the number of tests
- [ ] 4.5 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [ ] 4.6 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-nymh -m "<summary>"`, naming the command form, the test count, the wheel check and the
  assumptions below

## Notes

- Assumptions (unattended propose, 2026-11-17), recorded in design.md:
  - one source of truth by moving the files into `radark/examples/` (no root copy, no build-time copy) (D1);
  - the command is `radark example-config [--machine] [-o FILE [--force]] [--path]`; `-o` never overwrites without
    `--force`; plain output goes to standard output (D2);
  - the wheel check is a manual step recorded here and in `ho done`, guarded by a package-data test (D5).
