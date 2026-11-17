# Design

## Context

Handover HO-20261117-g5ag (RB-025, RB-028). The parallel tests drive the real `Dispatcher` with fake `ho` and fake
`claude` (`radark/tests/fakes/`). Parallel sessions order themselves through files: `touch` and `wait_for` (bounded,
default 30 s). Two places still use wall-clock timing:

- `test_end_time_lets_both_sessions_finish` sets `d.until` from `threading.Timer(1.0, ...)`.
- `ordered()` (used by `test_two_sessions_run_at_once_and_end_in_either_order[app|backend]` and
  `test_console_log_has_whole_lines`) makes the second session end after the first with `{"sleep": 2}`.

And one assertion depends on thread scheduling: the worker threads of app and backend are started in selection
order (app, then backend) from the main loop, but each writes `session_start` inside `Dispatcher.session()` after
taking the dispatcher lock (`BigLock`) and a progress snapshot; which thread gets the lock first is up to the OS
scheduler. The test asserts `seq[:2] == [start app, start backend]` and that the `(2 running)` console line is the
backend one.

## Goals / Non-Goals

**Goals:**
- Both tests (and every test using `ordered()`) pass on a loaded machine; 20/20 runs of each under load.
- Wait for observable conditions with generous upper bounds; normal-case runtime the same or shorter.
- Keep asserting what the tests are for: both sessions run at once; they end in the given order; the end time
  stops new starts but lets running sessions finish.

**Non-Goals:**
- No engine change (no guaranteed order of start records): see D1.
- No retries, skip or xfail; no new dependency (no `pytest-repeat`; the 20-run check is a shell loop).
- Not reworking other tests in the module whose short waits are negative checks (`within: 1` proving a session
  does *not* start); load cannot make them fail in the wrong direction.

## Decisions

**D1 — The start-record order is not behaviour; no engine fix.** Selection is deterministic (app first) and both
workers start before either session can end; only the order in which two concurrently started workers write their
`session_start` is scheduling. No spec promises that order, and the cockpit history pairs start and end records
per team, not by global order. Forcing it would serialise worker start-up for no user value. The spec delta adds a
clarifying scenario ("both start records before either end, in either order"). Alternative considered: write
`session_start` in the main thread before starting the worker — rejected, it moves the snapshot and the console
start line out of the worker and changes engine code for a test assertion. If apply finds a real race (for
example a session that can end before the other is recorded as started), it changes the engine, says so in the
report and adds a test for it, as the handover asks.

**D2 — RB-025 assertions.** Replace `seq[:2] == [app, backend]` with
`sorted(seq[:2]) == [("session_start", "app"), ("session_start", "backend")]` (both started before any end); keep
`seq[2:] == [end first, end second]`. Replace `any("(2 running)" in x and "backend" in x ...)` with
`any("(2 running)" in x for x in lines)` (one of the two start lines counts two).

**D3 — Deterministic end order through the run log.** New fake `claude` step
`{"wait_for_event": "<runs.jsonl path>", "event": "session_end", "team": "<team>", "within": s}`: polls the file
(every 0.05 s, default bound 30 s like `wait_for`) until a complete JSON line with that `event` and `team` exists;
partial or unreadable lines are ignored. In `ordered()` the second session replaces `{"sleep": 2}` with a wait for
the first session's `session_end`. The dispatcher writes the second's `session_end` only after its process exits,
so the end order is guaranteed and the test is about 2 s faster. Alternative: a longer sleep — rejected, still a
timer.

**D4 — RB-028 end time after an observed start.** Replace the `threading.Timer(1.0, ...)` with a daemon thread
that waits (poll 0.05 s, at most 30 s) for `backend.started`, then sets `d.until = time.time()`. At that moment
both sessions run (app waits for the same file, then sleeps 1.5 s; backend sleeps 4 s after the touch), which is
exactly the situation the test is about. If the file never appears within 30 s the thread sets `until` anyway, so
the loop still ends and the test fails on its assertions instead of hanging.

**D5 — Verification under load.** Each of the two tests (RB-025: both parametrisations) is run 20 times in a row
with a shell loop over `python -m pytest <nodeid> -q` while the rest of the suite runs in parallel in another
process (that full run goes through `radark-test-slot`), and the pass counts are recorded in tasks.md and in the
`ho done` summary. Assumption (unattended run, nobody to ask): when the parallel suite cannot run because another
session holds the test slot for long, an artificial CPU load (one busy Python process per core, stopped by its PID
afterwards) is used instead, and the report says so.

## Risks / Trade-offs

- [The fake's new step reads the dispatcher's run log] → it reads complete lines only and has a bound; the run
  log is already the tests' observable (`log_events`).
- [The backend `(2 running)` check was a weak proof that backend started second] → selection order stays covered
  by `test_pick_free` and the dry-run parallel tests; this test now proves concurrency and end order.
- [Another flake shows up in the full suite] → reported per hub `AGENTS.md` §10, not hidden.
