# Tasks

Change for HO-20261114-cda3 (RB-001). Builds on the archived `parallel-sessions`. Tests use fake `ho` / `claude`
and a temporary `RADARK_MACHINE_DIR`, never the real machine directory. Sections 1–4 are the handover's suggested
first part; 5–6 the second (design, Assumptions).

## 1. Machine layer basics

- [x] 1.1 New `radark/machine.py`: `machine_dir()` (D1: override, Windows / POSIX defaults, creation),
  `FileLock` (D4: non-blocking OS lock on byte 0 with `msvcrt` / `fcntl`, release, records written after lock and
  removed before release, stale-record cleanup), `load_limits()` (D2: `machine.toml`, defaults 2 / 1, integer ≥ 1,
  `bool` refused, last valid kept on a later invalid read). Verify with `radark/tests/test_machine.py`: override
  used; default path per platform (patched env); limits default, valid, `0` / `"two"` / `true` refused naming the key;
  a lock held by a child process (`subprocess` holding it) is not acquirable, and is acquirable at once after the
  child is killed; a stale record is ignored and removed.
- [x] 1.2 Start checks in `radark/__main__.py` (D1, D2, D5): `run`, `once`, `dry-run` exit 2 for an unusable machine
  directory, one inside the run directory or a team repository, or invalid limits, before any session. Verify with
  CLI tests for each refusal (message names the directory / file and key).
- [x] 1.3 Instance record (D1, D4, D5): taken after the run lock, released at exit; `sessions` count field. Verify:
  record present while a fake run runs, gone after it; a killed instance's record is reported stale.

## 2. Shared usage

- [x] 2.1 `usage.json` read / merge / write under `usage.lock` with the 10 s bound and own-reading fallback (D3).
  `on_usage` writes changed readings; `effective_usage()` used by `usage_hold`, `budget_reached`, `exhausted_window`,
  `start_budget`, `usage_report` and the goal-limit check. Verify with tests: two dispatchers (two run directories,
  one machine directory) — a reading from instance A's fake session holds instance B's next start; B's
  `--budget-5h` ends B on A's reading; newest `seen_ts` wins per window; lock timeout falls back and logs
  `machine_usage_unavailable` once.
- [x] 2.2 Shared hold after `usage_limit` (D3): written with `by`, waited for by every instance, wait line says
  `(hit in another pipeline)` for another instance's hold; own back-off doubling unchanged. Verify: A's
  `usage_limit` with a known reset → B starts nothing before it and starts after; with an unknown reset → B waits
  A's back-off end; a single instance's back-off tests unchanged.

## 3. Machine session limit

- [x] 3.1 `Machine.try_session_slot` / release with records and the instance's `sessions` count (D7). Taken in the
  sequential loop before a candidate, owner-answer resume, idle ask and goal check, and in the parallel loop before a
  worker starts; released in the step's `finally` after processing. Limit checks and triage consultations take
  none. Verify with dispatcher tests on fake runners: limit 2 with A running 2 → B waits and starts after one of A's
  ends, in both end orders; limit 2 with A `parallel_sessions = 2` running 1 and B running 1 → A waits; a slot is
  released after an error, an interruption and a usage-limit outcome.
- [x] 3.2 Waiting (D7): console lines (`machine limit: <k> sessions running in other pipelines`, own / other
  variant, `machine slot free - starting`), `machine_wait` / `machine_wait_end` events, nap ≤ 30 s through the
  existing wait path; STOP, PAUSE, `--until`, Ctrl+C honoured; the wait is not counted toward `empty_continues`,
  `no_progress` or the idle streak; `once` waits. Verify with tests for the line text, STOP during the wait, a goal
  run whose check waits (no `stalled`), and `once` starting after the slot frees.
- [x] 3.3 Single instance with defaults = old behaviour. Verify: the full existing suite passes unchanged, and a test
  that a lone instance with `parallel_sessions = 1` never logs `machine_wait`.

## 4. One repository, one instance

- [x] 4.1 Repository claims (D6): keys from `normcase(realpath)`, claimed after the instance record, released at
  exit; refusal message and exit 2 releasing everything taken; two teams of one configuration sharing a repository
  are fine. Verify: B refused naming the repository and A's configuration path (and B's run lock is released);
  different letter case / relative path refused on Windows (skipped elsewhere with a reason only for the case
  check); after A is killed, B starts.
- [x] 4.2 `dry-run` shows conflicts without claiming (probe take-and-release) and keeps its exit code (D6). Verify
  with a dry-run test while A holds the claim.

## 5. Test-run limit and keep-awake

- [x] 5.1 `python -m radark test-slot [--] <command...>` (D8): waits for `slots/test-<n>.lock` with the waiting lines,
  runs the command with `HARNESS_TEST_SLOT_HELD=1`, passes the exit code (127 when it cannot start), nested call runs
  at once. `<run_dir>/bin/radark-test-slot(.cmd)` written at start when changed; `session_env` adds
  `RADARK_MACHINE_DIR`, `HARNESS_TEST_SLOT` and `PATH`. `prompts.TEST_SLOT_NOTE` (exact text of D8) in work prompts
  when `parallel_sessions > 1` or another instance runs. Verify: two `test-slot` processes with limit 1 run one after
  the other (timestamps from the commands), with limit 2 at once; exit code 1 passed through; nested call does not
  wait; a killed `test-slot` frees its slot; `session_env` test; prompt tests (alone with 1 → no note; 2 → note;
  another instance running → note).
- [x] 5.2 Keep-awake with two instances (D10): no code change expected. Verify on Windows with a check script run in
  this session (not committed as a test if it needs admin rights): two processes each holding a
  `SetThreadExecutionState` request, one ends, `powercfg /requests` (when it can run) still lists the other; record
  the result, or that `powercfg /requests` needed rights it did not have and the documented Windows behaviour was
  relied on, under "Apply results". Add a unit test that two `Keeper`s with fake `set_state` clear only their own
  request.

## 6. Visibility and documentation

- [x] 6.1 `status` command (D9): machine directory, limits or error, other instances, slots in use, shared usage and
  hold, this configuration's conflicts; read-only, not blocked by the run lock; removes stale records. Start lines of
  `run` / `once` and the `dry-run` lines (D9). Verify with tests: `status` while a fake instance A runs one session
  lists A's configuration path and `1 session running`, limits, usage; a killed A is not listed; start line names A;
  dry-run prints the machine slot line; no handover / team / title of A appears in B's output.
- [x] 6.2 Docs: `machine.toml.example` (repository root); `radark/README.md` (machine directory, limits, shared usage,
  session and test-run limits, repository ownership, `status`, `test-slot`, keep-awake note, team `CLAUDE.md` rule
  for `radark-test-slot`); root `README.md` short mention; `harness.toml.example` comment at `parallel_sessions`
  pointing to the machine limit; `radark/sandbox/make_sandbox.py` sets a sandbox-local `RADARK_MACHINE_DIR` in what it
  prints / writes. Verify: names are neutral (`pipeline-a`, `pipeline-b`, `app`, `backend`); no private paths.
- [x] 6.3 Sandbox check (manual end-to-end, D9): two sandboxes (or two configurations of one sandbox) on one
  `RADARK_MACHINE_DIR`; `run` of the second with a shared repository → refusal line; `dry-run` of the second while
  the first runs → conflict and machine lines; `status` lists the first. Record the observed lines (neutral names)
  under "Apply results".

## 7. Finish

- [x] 7.1 Full suite `python -m pytest radark/tests` passes; failing or flaky tests follow hub `AGENTS.md` §10 (no
  retries or skips to hide a flake). Record the test count under "Apply results".
- [ ] 7.2 Commit locally (no push, tag, release or reinstall), citing HO-20261114-cda3.
- [ ] 7.3 `ho done HO-20261114-cda3 -m "..."` listing: change name `machine-wide-instances`, commits, new settings
  with defaults (`machine.toml` `sessions = 2`, `test_runs = 1`; `RADARK_MACHINE_DIR`), new commands (`status`,
  `test-slot`), test count, any split or deviation. This is the last step of apply; `ho sync` before and after.

## Apply results

Apply session of 2026-11-14 (unattended). Not split: sections 1–6 are all done in this change.

- **Code:** new `radark/machine.py`; `radark/__main__.py` (start order, `effective_usage`, shared hold, machine
  session slot in both loops, `status`, `test-slot`, dry-run and start lines); `radark/runner.py` (`session_env`:
  `RADARK_MACHINE_DIR`, `HARNESS_TEST_SLOT`, `<run_dir>/bin` first on `PATH`); `radark/prompts.py`
  (`TEST_SLOT_NOTE`). Tests: `radark/tests/test_machine.py` (71 tests on Windows); `conftest.py` gives every test its
  own `RADARK_MACHINE_DIR` (autouse fixture), so no test touches the real machine directory.
- **Tests (7.1):** the full suite before `test_machine.py` existed had 3 real failures, fixed in this change:
  `test_goal.py::test_complete_run_waits_for_key_in_a_console`, `test_not_interactive`,
  `test_console_is_copied_to_console_log` replace `msvcrt` in `sys.modules` with a stand-in, and the machine lock
  imported it at call time; `machine.py` now imports `msvcrt` / `fcntl` once at load. Final run: 800 passed in
  7 min 08 s (Windows 11, Python 3.12), no flaky test seen.
- **Keep-awake (5.2):** a check script (two Python processes, each holding `SetThreadExecutionState(ES_CONTINUOUS |
  ES_SYSTEM_REQUIRED)`, the first ending after 8 s) ran in this session; `powercfg /requests` answered "This command
  requires administrator privileges", so the documented Windows behaviour (requests are per thread, the system stays
  awake while any thread holds one) is relied on. Unit test: two `Keeper`s with fake `set_state` clear only their own
  request.
- **Sandbox (6.3):** one sandbox, two configurations (`pipeline-a.toml`, `pipeline-b.toml` with `run_dir = "run-b"`,
  same `app` and `product` repositories), sandbox-local `RADARK_MACHINE_DIR`. The installed `ho` on this computer has
  no `--version` (older than contract 1), so both configurations used the fake `ho` / `claude` of
  `radark/tests/fakes` with an empty hub (the machine layer calls no `ho`); `pipeline-a` ran `run` idle (no session).
  Observed (paths shortened to `<sb>`):
  - `pipeline-a run`: `Machine: <sb>\machine - limits 2 sessions, 1 test run`
  - `pipeline-b run` → exit 2: `Repository <sb>\repos\product is in use by another running pipeline
    (<sb>\pipeline-a.toml, PID <pid>); not starting. Remove it from one of the configurations or stop that pipeline.`
  - `pipeline-b dry-run` → exit 0: `Other pipeline running: <sb>\pipeline-a.toml (0 sessions running)`, `! repository
    <sb>\repos\product is in use by another running pipeline (<sb>\pipeline-a.toml); run would refuse` (and the same
    for `app`), `Machine slot: free`, `Nothing to do: no selectable candidate.`
  - `status`: `Running pipelines:` / `<sb>\pipeline-a.toml (PID <pid>, started ..., 0 sessions running)`, `Session
    slots in use: 0/2`, `Test-run slots in use: 0/1`, `Usage: no shared reading yet`, both conflicts; after a STOP
    of `pipeline-a`: `Running pipelines: none`, `Repository conflicts of <sb>\pipeline-b.toml: none`, no instance
    record left.

Decisions and deviations taken by the apply session (no owner available):

- The instance id is `<pid>-<start of the instance in ms>` (the time the machine layer is created), not the OS
  process creation time: it stays unique for several instances in one process (tests); PID and start are still in
  the record for display. Liveness is decided by the lock alone, as designed.
- The machine layer is attached by `main` (`run`, `once`, `dry-run`); a `Dispatcher` built directly (most existing
  tests) has none and behaves exactly as before.
- The machine-slot nap is `min(max(poll_seconds, 1 s), 30 s)`: the 1 s floor avoids a busy loop with
  `poll_seconds = 0`.
- Usage readings written during the stream carry no `status` (the runner's callback passes window, share and reset
  only, and its signature is part of existing tests); the status reaches `usage.json` when the session's reading is
  recorded at its end.
- The `radark-test-slot` wrappers call `"<python>" -P -m radark test-slot`: `-P` keeps the session's working directory
  off `sys.path`, so a repository that contains a `radark` folder (this one, when dogfooded) never shadows the
  installed release. Sessions do not get an instance id for the test-slot record (it holds the PID only; an
  `RADARK_INSTANCE` variable is recorded when set).
- `dry-run` and `status` do not count a claim by the same configuration path as a conflict (that is the pipeline
  itself; its run lock refuses a second `run`).
- `status` also prints the shared hold with the configuration path of the pipeline that set it (allowed detail).
- `test-slot` with an invalid `machine.toml` prints the error and uses the last valid (or default) test-run limit
  instead of failing the agent's test command.
- The sandbox script writes `machine-env.ps1` / `machine-env.sh` and creates `<sandbox>/machine`, and prints the line
  to set `RADARK_MACHINE_DIR` first.
