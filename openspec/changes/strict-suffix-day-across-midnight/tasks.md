# Tasks

Handover: HO-20261117-ln7w. Assumptions recorded in design.md (D1–D3): the day is shown only when the "stopped by"
moment is on another calendar day than the end time, in `day_clock` form relative to the current day.

## 1. Implementation

- [ ] 1.1 In `radark/__main__.py`, make `Dispatcher.until_mode()` render the "stopped by" time with
  `day_clock(by, time.time())` when `by.date() != at.date()`, and `{by:%H:%M}` otherwise; update its docstring
  (cite strict-suffix-day-across-midnight D1/D2). Verify: `python -m pytest radark/tests/test_until_strict.py`
  passes unchanged (same-day cases).

## 2. Tests

- [ ] 2.1 In `radark/tests/test_until_strict.py`, add a start-line test: now 22:10, end time 23:59 today, strict,
  `wrap_up_minutes = 15` → `Run ends at 23:59 today, in 109 min (strict: running sessions wrap up at 23:59, stopped by
  00:14 tomorrow)`. Verify: the test passes and fails without 1.1.
- [ ] 2.2 Add a test with the end time 23:59 on a later date (now on day N, end
  time on day N+1 at 23:59) and 15 min grace → the suffix ends `stopped by 00:14 on <date of day N+2>`; check both
  `start_until()` and `dry-run` (`Would end: ...`). Verify: the tests pass.
- [ ] 2.3 Keep the same-day cases unchanged (the existing `test_start_line` and `test_dry_run_with_a_strict_end_time`
  expectations with `stopped by 12:15`), and add a case with an end time tomorrow at 07:00 showing `stopped by 07:15`
  without a day. Verify: the tests pass.

## 3. Verification and report

- [ ] 3.1 Run the full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; note the count.
  Failing or flaky tests follow hub `AGENTS.md` §10 (never hidden by retries or skips).
- [ ] 3.2 `openspec validate strict-suffix-day-across-midnight --strict` passes; commit locally (no push, tag,
  release or reinstall), citing HO-20261117-ln7w.
- [ ] 3.3 `ho done HO-20261117-ln7w -m "<summary with the test count>"`, then `ho sync`.

## Workflow follow-up

- Archive the change and sync its specs only after `radark-product` closes HO-20261117-ln7w (separate phase).
