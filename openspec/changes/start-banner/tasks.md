# Tasks: start banner at run start (HO-20261117-u2vc)

## 1. Banner

- [x] 1.1 Add `radark/banner.py` with `BANNER` (raw string, no trailing newline) and `lines()`: `RA DARK` and
  `FACTORY` in block letters on two letter rows, a factory with chimneys and smoke below; at most 25 lines, every line
  printable ASCII, at most 80 characters, no trailing spaces, no tabs (design D1)
- [x] 1.2 In `radark/__main__.py` `main()`, print `banner.BANNER` immediately before the configuration summary print
  (design D2); nothing else in the start output changes

## 2. Tests

- [x] 2.1 Add `radark/tests/test_banner.py`: banner form (ASCII 0x20-0x7E, at most 80 characters, no trailing space,
  at most 25 lines), the lettering (known line) and the factory (chimney and smoke) (design D4)
- [x] 2.2 `dry-run` output starts with the banner, has it once, and the summary and dry-run lines follow unchanged;
  dry-run leaves `console.log` unchanged (design D3)
- [x] 2.3 `once`: `console.log` has the header line, then the banner, then the summary
- [x] 2.4 No banner for `plan`, `escalations` and a start refused by a configuration error
- [x] 2.5 Run the existing tests that check run / dry-run start output; adjust only those that break solely because
  of the leading banner, with one shared helper that strips it, and list them in the apply notes

## 3. Docs and checks

- [x] 3.1 `radark/README.md`: one sentence that run, once and dry-run start with an ASCII banner (no switch)
- [x] 3.2 Sandbox check: `python radark/sandbox/make_sandbox.py <tmp>` and
  `python -m radark --config <tmp>/radark.toml dry-run`; look at the window output; record the result in the notes
- [x] 3.3 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10 (known flaky:
  `test_parallel.py::test_two_sessions_run_at_once_and_end_in_either_order[backend]`,
  `test_parallel.py::test_end_time_lets_both_sessions_finish`), never retried or skipped
- [x] 3.4 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [x] 3.5 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-u2vc -m "<summary>"`, naming the dry-run / `console.log` assumption (design D3)

## Notes

- Assumption (unattended propose, 2026-11-17): dry-run keeps writing no `console.log`; the banner reaches
  `console.log` in run and once mode (design D3). Posted as a comment on HO-20261117-u2vc.
- Apply (2026-11-17): the banner is 24 lines, at most 66 columns: `RA DARK` and `FACTORY` in 6-column `#` letters
  (two letter rows), then smoke (`~`, `(`, `)`) over three chimneys and a saw-tooth factory hall. Tests in
  `radark/tests/test_banner.py`; `run --dry-run` is covered too.
- Apply 2.5: no existing test compared whole run or dry-run stdout or asserted on its first line in a way the leading
  banner breaks, so no shared strip helper was needed and no existing test was changed.
- Apply 3.2: sandbox `dry-run` shows the banner first, then `Hub: ...` and the rest of the start output as before.
- Apply 3.3: full suite 1010 passed, 1 failed in 885 s: the known flaky
  `test_parallel.py::test_end_time_lets_both_sessions_finish` (`backend` session neither started nor ended before the
  1 s end time; passes alone 3 of 3 runs). Unrelated to the banner; reported in the `ho done` result per hub
  `AGENTS.md` section 10, not retried in the suite or skipped.
- Apply 3.4: the diff has no owner paths, product names or hub / run excerpts.
- Archive is a separate phase after the author closes the handover; it is not a task of this change.
