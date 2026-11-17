# Tasks: opt-in strict end time for `--until` (HO-20261117-aor7)

## 1. Option and configuration

- [x] 1.1 `radark/config.py`: `Config.until_strict: bool = False` from `[loop] until_strict`; refuse a non-boolean
  with `ConfigError("loop.until_strict must be true or false, not …")` (design D1)
- [x] 1.2 `radark/__main__.py`: `--until-strict` / `--no-until-strict` (`argparse.BooleanOptionalAction`, default
  `None`) on the `run` and `dry-run` parsers; refuse either form without `--until` (exit 2, message of D1) before
  the configuration is read; `Dispatcher.until_strict` = flag if given, else `cfg.until_strict`; never stored

## 2. Runner: stop at a wall-clock moment

- [x] 2.1 `radark/runner.py`: `Runner.wall = time.time` (injectable); `run(..., end_at=None, on_end_at=None)`; in the
  poll loop call `on_end_at(r)` once when `wall() >= end_at` and the session is not being ended; on `"stop"` set
  `interrupt_cause = "end_time"`, end the process tree and mark the deadline handling expired (design D2)
- [x] 2.2 A limit check thread running at the stop ends as today (`on_deadline_abort`, verdict ignored); no new
  check starts after the stop

## 3. Dispatcher: strict end time

- [x] 3.1 `Dispatcher.session()`: pass `end_at` per design D3 (work session `U`; wrap-up and non-work sessions
  `U + G`; `None` without `--until`) and an `on_end_at` callback: strict → `"stop"`, default → the hint (task 4.1)
- [x] 3.2 End-time wrap-up (design D4): a work session (not a wrap-up) returned with cause `end_time` and `G > 0`,
  and `time.time() < U + G` → log `end_time_stop`, console `! <team> <ID>: end time HH:MM reached; asking the
  session to wrap up within G min`, resume with `wrap_up=True`, `timeout_s = G`, `end_at = U + G`; log
  `end_time_wrap_up`; no `time_limits` entry
- [x] 3.3 Step outcome after the end-time wrap-up (design D4): keep the wrap-up's outcome when it ended normally
  with the phase complete (`phase_complete`), or when it is `usage_limit` / `waiting_for_owner`; otherwise
  `outcome = "interrupted"`, `interrupt_cause = "end_time"` so `after_session` stores `resume_after_timeout`
- [x] 3.4 `radark/prompts.py`: `end_time_wrap_up_message(...)` (design D4 text; apply: `Left for a later run` note
  in `tasks.md`, no `ho done` unless the phase is complete); `INTERRUPT_LABELS["end_time"]`;
  `radark/__main__.py`: `INTERRUPT_CAUSE["end_time"] = "end time"`
- [x] 3.5 `limit_watch.deadline()`: in strict mode with `time.time() >= U`, return `WRAP_UP` (or `None` when
  `G = 0`) without a limit check (design D5)
- [x] 3.6 Parallel sessions: every worker's session gets its own `end_at`/`on_end_at`; `drain()` waits for the
  wrap-ups; the end-time wrap-up is not blocked by `ending()` (design D8)

## 4. Hint and reporting

- [x] 4.1 Default mode `on_end_at`: once per run, under the lock, print `Note: the end time HH:MM has passed; the
  running session finishes. To end on time, use --until-strict.` (plural for several running sessions; date when
  not today) and log `end_time_passed` (design D6)
- [x] 4.2 `start_until`: suffix `(strict: running sessions wrap up at HH:MM, stopped by HH:MM)`,
  `(strict: running sessions stop at HH:MM)` with `G = 0`, or `(running sessions finish first)`; `run_until` gets
  `strict`, `goal_start` gets `until_strict` (design D7)
- [x] 4.3 `dry-run`: `Would end: …` with the same suffix (design D7)

## 5. Tests (fake clock / fake claude, no real waits)

- [x] 5.1 New `radark/tests/test_until_strict.py`: strict + apply session running at the end time → `end_time_stop`,
  wrap-up resume with the end-time prompt, no limit check and no extension, wrap-up stopped after the grace period
  (`interrupted` / `end_time`), no new session, run ends with exit 0
- [x] 5.2 Strict: a deadline after the end time runs no limit check; a wrap-up that completes its phase keeps
  `finished`; `wrap_up_minutes = 0` stops at the end time without a wrap-up; a non-work session is stopped at
  `U + G`; the next run resumes the `end_time` session with the end-time resume message
- [x] 5.3 Strict with two parallel sessions: both stopped and wrapped up, the run ends after both
- [x] 5.4 Default mode: the session finishes as today (extension still given) and the hint is printed exactly once,
  also with a second session after the end time; no hint without `--until`, in strict mode, or when idle
- [x] 5.5 Parsing and validation: `--until-strict`, `--no-until-strict` over `until_strict = true`, flag without
  `--until` refused (exit 2, no session), `until_strict = "yes"` refused, config key without `--until` no effect
- [x] 5.6 Start line and `dry-run` text in both modes; update the start-line expectations in `test_until.py` /
  `test_keep_awake.py` and list every changed test in the notes
- [x] 5.7 Keep `test_end_time_lets_both_sessions_finish` (`radark/tests/test_parallel.py`) stable and unchanged in
  meaning (default mode)

## 6. Docs, checks and report

- [x] 6.1 `radark/README.md`: `[loop]` table (`until_strict`), **Pause / stop** (`--until`, `--until-strict`, the
  hint, the start line), **Time limits** / **Wrap-up** (stop at a strict end time, cause `end_time`)
- [ ] 6.2 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; record the number of tests;
  failing or flaky tests are reported per hub `AGENTS.md` section 10, never retried or skipped
- [x] 6.3 Manual check: `python radark/sandbox/make_sandbox.py <tmp>` then `dry-run --until HH:MM` with and without
  `--until-strict`; record the output in the notes (no private paths)
- [ ] 6.4 Commit locally (no push, tag, release or reinstall); `ho done HO-20261117-aor7 -m "<summary with the
  number of tests>"`

## Notes

- Assumptions made without an owner (see design, *Assumptions*): option names, the flag without `--until` is
  refused, the end-time wrap-up does not ask for `ho done` unless the phase is complete, non-work sessions get the
  grace period without a prompt, the default start line gets a `(running sessions finish first)` suffix.
- Apply notes (HO-20261117-aor7):
  - `duration_text` prints `118 min` below 2 h (existing format), so the examples `in 1 h 58 min` in the proposal,
    design and delta spec were corrected to `in 118 min`; the console format is unchanged.
  - The end line keeps its existing form `→ interrupted, end time (…)` (cause after a comma, as for every cause).
  - The limit check's own session (run outside `session()`) gets the non-work end moment too (`U + G` strict, the
    hint in the default mode).
  - The end-time wrap-up keeps its outcome only when it ended normally (not `error`) with the phase complete, or as
    `usage_limit` / `waiting_for_owner`; a `question` from it is not triaged after the end time (it becomes
    `interrupted` / `end_time` and the next run resumes the session).
  - Tests use the real clock with short times (end time 2 s ahead, grace 0.05 min = 3 s) instead of a patched wall
    clock: the runner's end moment is fixed when a session starts, and short real waits keep the tests simple;
    the strict test module runs in about 50 s.
  - Changed existing tests: `radark/tests/test_until.py::test_start_line_and_log` (start line suffix
    `(running sessions finish first)`, `run_until.strict` false). `test_keep_awake.py` needed no change;
    `test_parallel.py::test_end_time_lets_both_sessions_finish` is unchanged (default mode).
  - Manual check (sandbox, `dry-run`): `Would end: 23:59 today, in 15 h 08 min (running sessions finish first)`;
    with `--until-strict`: `Would end: 23:59 today, in 15 h 08 min (strict: running sessions wrap up at 23:59,
    stopped by 00:14)`; `dry-run --until-strict` alone: `--until-strict needs --until (an end time); without --until
    the run has no end time.`, exit 2.
