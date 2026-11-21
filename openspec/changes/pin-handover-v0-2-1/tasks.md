# Tasks

Handover: HO-20261121-gcrx. radark-handover part: HO-20261121-g3zr (sent in the propose session).

## 1. radark-handover v0.2.1 is ready

- [x] 1.1 Run `ho sync`, then `ho show HO-20261121-g3zr --json`: verify radark-handover reported `done`; read the
  version, contract and commit IDs from its `done` event. If it is not done yet, stop here and report the change as
  waiting for HO-20261121-g3zr (design D1).
- [x] 1.2 In the radark-handover working copy, run `ho --version --json` with its `ho.py`
  (`python <radark-handover>/ho.py --version --json`) and verify it reports version `0.2.1`; note the contract. If
  the contract is not `1`, comment on HO-20261121-gcrx and stop (design D3).

## 2. Pin and tag table

- [x] 2.1 In `pyproject.toml`, change the pin to `radark-handover @ git+https://github.com/raaleksandr/radark-handover.git@v0.2.1`;
  in `radark/hub.py`, set `HO_RELEASE_CONTRACTS = {"v0.2.0": 1, "v0.2.1": 1}` (contract from 1.2). Verify
  `python -m pytest radark/tests/test_ho_pin.py` passes.
- [x] 2.2 Add a test in `radark/tests/test_ho_pin.py` that the real table still lists `v0.2.0` and `v0.2.1` with
  contract `1` (spec scenario "Earlier tag stays known"); keep the made-up `v0.2.0` fixtures (design D2). Verify the
  pin tests pass.
- [x] 2.3 Update docs that name the *current pin* (search `README.md`, `radark/README.md` for `v0.2.0` / pinned
  release text) to `v0.2.1`; sample `ho --version` outputs stay (design D5). Verify with a search that no text
  claims `v0.2.0` is the pinned tag.
- [x] 2.4 Commit `pin-handover-v0-2-1: pin radark-handover v0.2.1 (HO-20261121-gcrx)`.

## 3. Release version and full check

- [ ] 3.1 Bump `version` in `pyproject.toml` from `0.7.0` to `0.8.0` (design D4) and verify
  `python -m radark --version` prints `radark 0.8.0` from the working tree; commit as `Release 0.8.0`. No tag, push
  or install.
- [ ] 3.2 Run the full suite `radark-test-slot python -m pytest radark/tests`; all must pass. Record the test count;
  failing or flaky tests follow hub `AGENTS.md` §10.
- [ ] 3.3 Run `ho sync`; close HO-20261121-g3zr (`ho close HO-20261121-g3zr`), since its result was verified in 1.2,
  so radark-handover can archive its change. Verify `ho show HO-20261121-g3zr --json` shows status `closed`.
- [ ] 3.4 Last step: `ho done HO-20261121-gcrx -m "..."` with radark-handover version and contract, radark-factory
  version 0.8.0, commit IDs of both teams, change names (this change and radark-handover's), test counts, and the
  owner's order of steps (tag radark-handover v0.2.1 first, then tag/release radark-factory 0.8.0 and reinstall);
  then `ho sync`. Verify `ho show HO-20261121-gcrx --json` shows radark-factory `done`.

## Workflow follow-up

- After the author closes HO-20261121-gcrx: archive this change and sync its specs (separate archive phase).

## Notes (apply session)

- 1.1: HO-20261121-g3zr is `done` (radark-handover 0.2.1, contract 1, commit 34e4659, change fix-console-encoding)
  and was already closed by radark-factory on 2026-11-21 after verification.
- 1.2: `python <radark-handover>/ho.py --version --json` reports version `0.2.1`, contract `1`.
- 2.3: no doc names the current pinned tag; `0.2.0` in `radark/README.md` are sample outputs (design D5), unchanged.
