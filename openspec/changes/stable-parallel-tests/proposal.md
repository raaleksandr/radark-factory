## Why

Handover HO-20261117-g5ag (backlog items RB-025 and RB-028) asks to make two flaky tests in
`radark/tests/test_parallel.py` stable, so a full suite on a loaded machine is a real signal and no known-flaky
exceptions are needed. Both flakes come from the tests relying on wall-clock timing instead of an observable
condition:

- **RB-025** `test_two_sessions_run_at_once_and_end_in_either_order[backend]` failed once with the `session_start`
  records in the order backend, app. The dispatcher picks app first and starts its worker thread, then backend's;
  each worker writes its `session_start` record after taking the dispatcher lock, so on a loaded machine the
  backend thread can take the lock first. The selection order is deterministic, the order of the two start
  records is thread scheduling, and the test asserts it (and, through `"(2 running)"` + `backend`, also which
  session's start line counts two). The end order relies on a fixed `sleep 2` in the second session.
- **RB-028** `test_end_time_lets_both_sessions_finish` sets the end time from a fixed 1.0 s `threading.Timer`. When
  the backend session has not started within that second (loaded machine), the end time is reached first, no new
  session is started and the test sees only app.

## What Changes

- `test_end_time_lets_both_sessions_finish`: set the end time once the backend session has observably started
  (its `backend.started` file exists), bounded by a generous timeout, instead of after a fixed 1.0 s.
- `test_two_sessions_run_at_once_and_end_in_either_order`: assert that both sessions started before either ended,
  without fixing the order of the two start records; assert the `(2 running)` line without fixing its team. The
  end order (the behaviour under test) is made deterministic: the second session waits until the first session's
  `session_end` record is in the run log instead of sleeping a fixed 2 s.
- Fake `claude` gets one new test step that waits (bounded, like `wait_for`) until the run log has a record with
  a given event and team; the shared `ordered()` helper uses it (also used by
  `test_console_log_has_whole_lines`).
- No engine change: the order of two start records of sessions started at the same time is not specified
  behaviour (the spec delta says so explicitly). No skip, xfail or retry.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Number of parallel sessions* gets a scenario stating that sessions started at the same
  time may write their start records in either order (clarification; no behaviour change).

## Impact

- `radark/tests/test_parallel.py`, `radark/tests/fakes/fake_claude.py` (test code only).
- `openspec/specs/harness-dispatcher/spec.md` (one clarifying scenario on archive).
- Normal-case runtime of the two tests stays about the same or shorter; timeouts are upper bounds only.
