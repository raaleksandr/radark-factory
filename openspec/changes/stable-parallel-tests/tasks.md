# Tasks

Handover HO-20261117-g5ag (RB-025, RB-028). Test code only; see design D1 for why the engine is not changed.

## 1. Reproduce and confirm the causes

- [ ] 1.1 Run `test_end_time_lets_both_sessions_finish` and `test_two_sessions_run_at_once_and_end_in_either_order`
  in a loop under load (design D5) before the fix and note failures and their signs (backend never started; start
  records backend before app) in the notes below; verify: notes recorded (zero failures is a valid result, noted as
  such; the causes in design D1/D4 then rest on the code paths named there).

## 2. Fake claude step

- [ ] 2.1 Add the `wait_for_event` step to `radark/tests/fakes/fake_claude.py` (design D3) and list it in the
  file's step documentation; verify: a test in `test_parallel.py` where a session step waits for a `session_end`
  record of another team, and one where the record never appears and the step returns after its `within` bound.

## 3. Test fixes

- [ ] 3.1 `ordered()`: the second session waits for the first one's `session_end` instead of `{"sleep": 2}`
  (design D3); verify: `test_two_sessions_run_at_once_and_end_in_either_order` (both) and
  `test_console_log_has_whole_lines` pass.
- [ ] 3.2 `test_two_sessions_run_at_once_and_end_in_either_order`: order-independent start assertions and
  `(2 running)` check (design D2); verify: both parametrisations pass.
- [ ] 3.3 `test_end_time_lets_both_sessions_finish`: set the end time once `backend.started` exists, bounded at
  30 s (design D4); verify: the test passes and its runtime is about the same as before (note both).

## 4. Verification and report

- [ ] 4.1 Run each of the two tests (RB-025 both parametrisations, RB-028) 20 times in a row under load (design
  D5); verify: pass counts recorded in the notes below (expected 20/20 each).
- [ ] 4.2 Full suite through the test slot: `radark-test-slot python -m pytest radark/tests`; verify: all pass; any
  other failing or flaky test is listed in the notes per hub `AGENTS.md` §10.
- [ ] 4.3 Public-repository check of the diff (no owner paths, product names or hub excerpts); verify: review of
  `git diff`.
- [ ] 4.4 Commit locally (no push), then `ho done HO-20261117-g5ag -m "<summary>"` naming the cause found for each
  test, the 20-run pass counts and the full-suite result; verify: `ho show HO-20261117-g5ag --json` shows
  radark-factory `done`.

## Notes

- Assumption (unattended run): if a parallel full suite cannot run during the 20-run check because another
  session holds the test slot, artificial CPU load is used instead (design D5).

## Workflow follow-up

- Archive the change and sync its specs only after the author closes the handover (separate archive phase).
