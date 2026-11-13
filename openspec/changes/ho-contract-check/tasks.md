# Tasks

Change for HO-20261113-k2wq (RB-003). The `ho` side is HO-20261113-cbcj to `radark-handover` (sent in propose).

## 0. Shape from radark-handover

- [x] 0.1 Read HO-20261113-cbcj (`ho show HO-20261113-cbcj --json`): take the exact `ho --version` and `ho --version --json` outputs from radark-handover's `ho done`. If the shape differs from design D1, update D1 and the fake's default answer (D5) to match before coding. If it is not done yet, do not guess: the item waits (the dispatcher holds it); comment on HO-20261113-cbcj if something is unclear.

## 1. Probe and constant

- [x] 1.1 In `radark/hub.py`, add `SUPPORTED_HO_CONTRACTS = (1,)`, a `HoVersion(version, contract)` dataclass and `check_ho(cmd, hub, timeout=60) -> HoVersion | str` per design D1–D3 (env without `HO_TEAM`, `HO_HUB` set; missing / no answer / too old / unsupported messages naming the command, found and needed versions and the remedy). Verify: unit tests in `radark/tests/test_hub.py` with the fake `ho`: compatible → `HoVersion("0.2.0", 1)`; non-existent command → missing message; `_version` with `exit: 2` → too-old message; non-JSON stdout → too old; contract `2` with version `0.9.0` → message naming `0.9.0`, `2` and `1`; supported set `(1, 2)` formats as `1 or 2`; the call has no `HO_TEAM`.
- [x] 1.2 In `radark/tests/fakes/fake_ho.py`, answer `--version` per design D5 (default compatible; `"_version": {"exit": N}` → exit N with no stdout; another dict → printed) and document the key in the module docstring. Verify: the tests of 1.1 use it; existing tests still pass (1.4).

## 2. Start path

- [x] 2.1 In `radark/config.py`, let `summary()` take an optional `ho` text and print `ho: <version> (contract <n>)` right after `Claude Code: ...`. In `radark/__main__.py` `main()`, run `check_ho` for `plan`, `run`, `once` and `dry-run` before the first hub call and before the summary (design D4); on a message print `ho incompatible: <message>` to stderr and return 2; on success pass the line to `summary()`. `escalations`, `clear`, `keep`, `note` skip the check. Verify: tests (new `radark/tests/test_ho_check.py` or existing dispatcher tests) with the fake `ho`: `dry-run` compatible → output contains `ho: 0.2.0 (contract 1)` and continues as before; `dry-run` and `run --once` with missing, too-old and wrong-contract `ho` → exit code 2, message on stderr naming found/needed, no `claude` call (fake claude log empty), no lock file, no `dispatcher_start` in the run log, no other `ho` call than `--version` in `.calls`; `plan` with a wrong contract → exit 2, no prediction; `escalations` with a wrong-contract `ho` works.
- [x] 2.2 Adjust existing tests that inspect the fake's `.calls` and now see the `--version` call first (ignore it where the test is about other calls; do not weaken what they check).
- [x] 2.3 Run the full suite `python -m pytest radark/tests`; all pass. Note the count and any failing or flaky tests per hub `AGENTS.md` §10.

## 3. Docs

- [x] 3.1 In `radark/README.md`, near the configuration / start description: the start check (`ho --version --json`), the supported contract (1) and where the constant lives, the start line, the exit code 2 and the four stop cases with what to do (install a matching radark-handover; both packages are upgraded together). Verify: the section names these and no private data (neutral examples only).

## 4. Manual check

- [x] 4.1 Make a sandbox (`python radark/sandbox/make_sandbox.py <temp dir>`) and run `python -m radark --config <dir>/harness.toml dry-run` twice: with the installed `ho` (expected: the too-old stop if it has no `--version`) and with `ho` set to radark-handover's working-tree `ho.py` (expected: the `ho:` line and a normal dry run). Record the exact start line and stop messages for the hand-back. The sandbox lives outside the repository and is not committed.

## 5. Hand back

- [x] 5.1 Commit locally (no push, tag, release or reinstall) with a message citing HO-20261113-k2wq; verify `git status` is clean.
- [ ] 5.2 `ho done HO-20261113-k2wq -m "..."` listing both change names (this one and radark-handover's), the commits in both repositories (radark-handover's from its `ho done`), the test counts of both suites, the exact `ho --version` outputs (text and JSON), the start line, the exact stop message for a wrong contract version, and any failing or flaky tests; then `ho sync`.

## Apply results

- 0.1: shape as in design D1 (see D6); no change to the fake's default.
- 2.3: `python -m pytest radark/tests` → 566 passed (3:45), none failing or flaky. New: `radark/tests/test_ho_check.py`.
- 4.1: installed `ho` (no `--version`) → exit 2, `ho incompatible: ho '<path>\ho.EXE' has no --version (exit 1): it is older than this radark-factory supports. Found: no version; needed: JSON contract 1. Install a radark-handover release that has 'ho --version' with contract 1.`; radark-handover working-tree `ho.py` → start line `ho: 0.2.0 (contract 1)` and a normal dry run (exit 0).

## Notes

- HO-20261113-cbcj to radark-handover was sent in the propose session (the handover asks this team to request it), so radark-handover can work while this change waits; it references HO-20261113-k2wq, so the dispatcher holds this item until that part is done.
- Assumptions: the JSON shape of design D1 (radark-handover decides); exit code 2 and the `ho incompatible: ` prefix (D3/D4); `plan` checks but prints no summary line (D4); a timeout is a fifth stop case besides missing / too old / wrong contract.
- Closing HO-20261113-cbcj (and telling radark-handover to archive) happens after radark-product closes HO-20261113-k2wq; archiving this change and syncing its delta spec happen in the separate archive phase. Neither is a task of this change.
