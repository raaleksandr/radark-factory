# Tasks: start banner at run start (HO-20261117-u2vc)

## 1. Banner

- [ ] 1.1 Add `radark/banner.py` with `BANNER` (raw string, no trailing newline) and `lines()`: `RA DARK` and
  `FACTORY` in block letters on two letter rows, a factory with chimneys and smoke below; at most 25 lines, every line
  printable ASCII, at most 80 characters, no trailing spaces, no tabs (design D1)
- [ ] 1.2 In `radark/__main__.py` `main()`, print `banner.BANNER` immediately before the configuration summary print
  (design D2); nothing else in the start output changes

## 2. Tests

- [ ] 2.1 Add `radark/tests/test_banner.py`: banner form (ASCII 0x20-0x7E, at most 80 characters, no trailing space,
  at most 25 lines), the lettering (known line) and the factory (chimney and smoke) (design D4)
- [ ] 2.2 `dry-run` output starts with the banner, has it once, and the summary and dry-run lines follow unchanged;
  dry-run leaves `console.log` unchanged (design D3)
- [ ] 2.3 `once`: `console.log` has the header line, then the banner, then the summary
- [ ] 2.4 No banner for `plan`, `escalations` and a start refused by a configuration error
- [ ] 2.5 Run the existing tests that check run / dry-run start output; adjust only those that break solely because
  of the leading banner, with one shared helper that strips it, and list them in the apply notes

## 3. Docs and checks

- [ ] 3.1 `radark/README.md`: one sentence that run, once and dry-run start with an ASCII banner (no switch)
- [ ] 3.2 Sandbox check: `python radark/sandbox/make_sandbox.py <tmp>` and
  `python -m radark --config <tmp>/radark.toml dry-run`; look at the window output; record the result in the notes
- [ ] 3.3 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10 (known flaky:
  `test_parallel.py::test_two_sessions_run_at_once_and_end_in_either_order[backend]`,
  `test_parallel.py::test_end_time_lets_both_sessions_finish`), never retried or skipped
- [ ] 3.4 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [ ] 3.5 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-u2vc -m "<summary>"`, naming the dry-run / `console.log` assumption (design D3)

## Notes

- Assumption (unattended propose, 2026-11-17): dry-run keeps writing no `console.log`; the banner reaches
  `console.log` in run and once mode (design D3). Posted as a comment on HO-20261117-u2vc.
- Archive is a separate phase after the author closes the handover; it is not a task of this change.
