# Tasks: a finished session with a non-escalated denial is logged `finished` (HO-20261117-mw63)

## 1. Outcome decided before it is reported

- [x] 1.1 `radark/runner.py`: add `SessionResult.unescalated_denials: int = 0`
- [x] 1.2 `radark/__main__.py`: let `phase_complete` be called from `session()` (team, handover, phase; design D1);
  record the chosen form in the notes
- [x] 1.3 `Dispatcher.session()`: for a work session with outcome `waiting_for_owner`, after the denial events are
  logged and before `session_end`, apply `denial_only(r) and normal_end(r) and phase_complete(...)` with
  `since or r.started`; when it holds set `r.outcome = "finished"` and `r.unescalated_denials = len(r.denials)`
  (design D1)
- [x] 1.4 `session_end` and the `rec["sessions"]` entry: add `unescalated_denials=<count>` only when non-zero
  (design D3)
- [x] 1.5 `end_line`: append `; N permission denial(s), not escalated` after the duration when
  `r.unescalated_denials` is non-zero (design D3); goal steps use the same line
- [x] 1.6 `after_session`: replace its own denial check with `if r.unescalated_denials:
  self.denial_not_escalated(cand, rec, r)`; no second `phase_complete` call for this case (design D2)

## 2. Tests

- [x] 2.1 `radark/tests/test_denial.py`: a completed apply with one non-escalated denial → captured console end line
  `→ finished (…; 1 permission denial, not escalated)`, `session_end` outcome `finished` with `denials == 1` and
  `unescalated_denials == 1`, session entry outcome `finished`; no console line or record of it says
  `waiting_for_owner`
- [x] 2.2 Two denials in a completed phase → `2 permission denials, not escalated`
- [x] 2.3 A denial with an escalation marker, and a denial without `done` → end line, `session_end` and session
  entry stay `waiting_for_owner`, no `unescalated_denials`
- [x] 2.4 Update `test_console_and_run_log` (it asserted the raw `waiting_for_owner` in `session_end`); keep the
  `!` lines and the `denial_not_escalated` event as they are; list every other test changed in the notes
- [x] 2.5 Goal report: the step line of such a session says `finished` with the denial note, and the "Permission
  denials not escalated" section is unchanged
- [x] 2.6 Cockpit history: a `session_end` with outcome `finished` and `unescalated_denials` shows as `finished`
  with its denial count (existing reader; add a test only if none covers it)

## 3. Docs and checks

- [x] 3.1 `radark/README.md` (outcome paragraph): replace "its `session_end` keeps the raw `waiting_for_owner`" by
  the new behaviour, the end-line wording and the `unescalated_denials` field
- [x] 3.2 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; record the number of tests;
  failing or flaky tests are reported per hub `AGENTS.md` section 10, never retried or skipped
- [x] 3.3 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts; invented
  `HO-…` IDs only)
- [x] 3.4 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-mw63 -m "<summary, number of tests>"`, naming the field and wording chosen (design D3)

## Notes

- Assumptions (unattended propose, 2026-11-17): field name `unescalated_denials` (a count on `session_end` and the
  session entry), end-line wording `→ finished (<duration>; N permission denial(s), not escalated)`; the decision
  moves into `session()` rather than delaying the end report (design D1–D3).
- Consumers checked during propose: selection and `cockpit_now` do not branch on the outcome word; the goal report's
  escalated list comes from blocked records. No change needed there (design Context).
- Apply (2026-11-17): `phase_complete` keeps its `Candidate` signature (existing tests call it that way);
  `session()` builds a `Candidate` from team, handover, phase and the record's change. The check in `session()` runs
  only for phases with a completion signal (`PHASE_SIGNALS`: propose, apply, act, review, archive) and only when
  `denial_only` and `normal_end` already hold, so `ho show` is not called for other sessions. In `after_session` the
  `BLOCKED: owner` override also uses `r.unescalated_denials` instead of a second `phase_complete` call.
- Tests changed: `test_denial.py::test_console_and_run_log` (expects `finished`, `denials == 1`,
  `unescalated_denials == 1`), `test_goal_report_lists_denials_not_escalated` (step line). Tests added:
  `test_finished_end_line_with_one_denial`, `test_finished_end_line_with_two_denials`,
  `test_escalated_denial_still_waits_for_the_owner[marker|not_done]`,
  `test_cockpit_history.py::test_finished_session_with_unescalated_denials` (no test covered a `finished` session
  with denials in the history reader; the reader needed no change).
- Full suite (2026-11-17): 1034 passed in 466 s; no failing or flaky tests.
