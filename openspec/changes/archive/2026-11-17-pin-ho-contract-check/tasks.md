# Tasks: a release cannot pin an incompatible ho (HO-20261117-c5ns)

## 1. Table

- [x] 1.1 `radark/hub.py`: add `HO_RELEASE_CONTRACTS = {"v0.2.0": 1}` under `SUPPORTED_HO_CONTRACTS`, with a comment
  that it must be updated together with the `radark-handover` pin in `pyproject.toml` (design D1); the start check
  does not use it

## 2. Pin test

- [x] 2.1 New `radark/tests/test_ho_pin.py` with helpers `pin_tag(dependencies)` and
  `pin_problem(tag, table, supported)` (design D2)
- [x] 2.2 Test: the real `pyproject.toml` pin (read with `tomllib`) has a tag that is in `HO_RELEASE_CONTRACTS` with
  a contract in `SUPPORTED_HO_CONTRACTS`; skip only if `pyproject.toml` is absent (installed package)
- [x] 2.3 Tests on in-memory data: tag mapped to an unsupported contract fails with a message naming tag, found and
  supported contracts; unknown tag fails; dependency without `@<tag>` or missing fails; a supported entry passes
- [x] 2.4 Manual wrong-pin check for the done note: edit the pin in `pyproject.toml` to an unknown tag (e.g.
  `v9.9.9`) and run `python -m pytest radark/tests/test_ho_pin.py` (fails); then add a table entry `"v9.9.9": 2`
  and run it again (fails on the unsupported contract); restore both with
  `git restore -- pyproject.toml radark/hub.py` (re-applying task 1.1 if not yet committed) and see it pass;
  record the outputs in the notes

## 3. Docs

- [x] 3.1 `README.md` "Development": add the owner's release steps (design D4): bump pin, table and
  `SUPPORTED_HO_CONTRACTS` together when the required contract changes (and add the tag to the table on any pin
  change), take the contract from that tag's `ho --version --json`, the full suite must pass, then tag and release
- [x] 3.2 `radark/README.md` "Compatibility of `ho`": one sentence on `HO_RELEASE_CONTRACTS` and the pin test

## 4. Checks and report

- [x] 4.1 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped
- [x] 4.2 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [x] 4.3 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-c5ns -m "<summary>"`: the wrong-pin check (task 2.4), the number of tests, and the
  assumption of design D3

## Notes

- Assumption (unattended propose, 2026-11-17): a tag-to-contract table rather than a minimum-tag constant (design
  D1), and no optional test against an installed `ho` (design D3: tests use only the fake `ho`).
- Apply (2026-11-17): `pin_problem` takes the dependency list (`pin_problem(dependencies, table, supported)`)
  instead of the bare tag, so its message can name the pin itself (spec: "the message SHALL name the pin").
  An extra case checks two supported contracts during a migration.
- Wrong-pin check (task 2.4): pin `@v9.9.9` -> `tag v9.9.9 is not in HO_RELEASE_CONTRACTS (supported contracts: 1)`
  (1 failed, 9 passed); with `"v9.9.9": 2` in the table -> `tag v9.9.9 has ho contract 2, the engine supports
  contract(s) 1` (1 failed, 9 passed); both files restored -> 10 passed.
- Full suite (task 4.1): 1029 passed in 8 min 13 s.
