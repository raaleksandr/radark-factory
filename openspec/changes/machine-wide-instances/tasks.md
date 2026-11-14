# Tasks

Change for HO-20261114-cda3 (RB-001). Builds on the archived `parallel-sessions`. Tests use fake `ho` / `claude`
and a temporary `RADARK_MACHINE_DIR`, never the real machine directory. Sections 1–4 are the handover's suggested
first part; 5–6 the second (design, Assumptions).

## 1. Machine layer basics

- [ ] 1.1 New `radark/machine.py`: `machine_dir()` (D1: override, Windows / POSIX defaults, creation),
  `FileLock` (D4: non-blocking OS lock on byte 0 with `msvcrt` / `fcntl`, release, records written after lock and
  removed before release, stale-record cleanup), `load_limits()` (D2: `machine.toml`, defaults 2 / 1, integer ≥ 1,
  `bool` refused, last valid kept on a later invalid read). Verify with `radark/tests/test_machine.py`: override
  used; default path per platform (patched env); limits default, valid, `0` / `"two"` / `true` refused naming the key;
  a lock held by a child process (`subprocess` holding it) is not acquirable, and is acquirable at once after the
  child is killed; a stale record is ignored and removed.
- [ ] 1.2 Start checks in `radark/__main__.py` (D1, D2, D5): `run`, `once`, `dry-run` exit 2 for an unusable machine
  directory, one inside the run directory or a team repository, or invalid limits, before any session. Verify with
  CLI tests for each refusal (message names the directory / file and key).
- [ ] 1.3 Instance record (D1, D4, D5): taken after the run lock, released at exit; `sessions` count field. Verify:
  record present while a fake run runs, gone after it; a killed instance's record is reported stale.

## 2. Shared usage

- [ ] 2.1 `usage.json` read / merge / write under `usage.lock` with the 10 s bound and own-reading fallback (D3).
  `on_usage` writes changed readings; `effective_usage()` used by `usage_hold`, `budget_reached`, `exhausted_window`,
  `start_budget`, `usage_report` and the goal-limit check. Verify with tests: two dispatchers (two run directories,
  one machine directory) — a reading from instance A's fake session holds instance B's next start; B's
  `--budget-5h` ends B on A's reading; newest `seen_ts` wins per window; lock timeout falls back and logs
  `machine_usage_unavailable` once.
- [ ] 2.2 Shared hold after `usage_limit` (D3): written with `by`, waited for by every instance, wait line says
  `(hit in another pipeline)` for another instance's hold; own back-off doubling unchanged. Verify: A's
  `usage_limit` with a known reset → B starts nothing before it and starts after; with an unknown reset → B waits
  A's back-off end; a single instance's back-off tests unchanged.

## 3. Machine session limit

- [ ] 3.1 `Machine.try_session_slot` / release with records and the instance's `sessions` count (D7). Taken in the
  sequential loop before a candidate, owner-answer resume, idle ask and goal check, and in the parallel loop before a
  worker starts; released in the step's `finally` after processing. Limit checks and triage consultations take
  none. Verify with dispatcher tests on fake runners: limit 2 with A running 2 → B waits and starts after one of A's
  ends, in both end orders; limit 2 with A `parallel_sessions = 2` running 1 and B running 1 → A waits; a slot is
  released after an error, an interruption and a usage-limit outcome.
- [ ] 3.2 Waiting (D7): console lines (`machine limit: <k> sessions running in other pipelines`, own / other
  variant, `machine slot free - starting`), `machine_wait` / `machine_wait_end` events, nap ≤ 30 s through the
  existing wait path; STOP, PAUSE, `--until`, Ctrl+C honoured; the wait is not counted toward `empty_continues`,
  `no_progress` or the idle streak; `once` waits. Verify with tests for the line text, STOP during the wait, a goal
  run whose check waits (no `stalled`), and `once` starting after the slot frees.
- [ ] 3.3 Single instance with defaults = old behaviour. Verify: the full existing suite passes unchanged, and a test
  that a lone instance with `parallel_sessions = 1` never logs `machine_wait`.

## 4. One repository, one instance

- [ ] 4.1 Repository claims (D6): keys from `normcase(realpath)`, claimed after the instance record, released at
  exit; refusal message and exit 2 releasing everything taken; two teams of one configuration sharing a repository
  are fine. Verify: B refused naming the repository and A's configuration path (and B's run lock is released);
  different letter case / relative path refused on Windows (skipped elsewhere with a reason only for the case
  check); after A is killed, B starts.
- [ ] 4.2 `dry-run` shows conflicts without claiming (probe take-and-release) and keeps its exit code (D6). Verify
  with a dry-run test while A holds the claim.

## 5. Test-run limit and keep-awake

- [ ] 5.1 `python -m radark test-slot [--] <command...>` (D8): waits for `slots/test-<n>.lock` with the waiting lines,
  runs the command with `HARNESS_TEST_SLOT_HELD=1`, passes the exit code (127 when it cannot start), nested call runs
  at once. `<run_dir>/bin/radark-test-slot(.cmd)` written at start when changed; `session_env` adds
  `RADARK_MACHINE_DIR`, `HARNESS_TEST_SLOT` and `PATH`. `prompts.TEST_SLOT_NOTE` (exact text of D8) in work prompts
  when `parallel_sessions > 1` or another instance runs. Verify: two `test-slot` processes with limit 1 run one after
  the other (timestamps from the commands), with limit 2 at once; exit code 1 passed through; nested call does not
  wait; a killed `test-slot` frees its slot; `session_env` test; prompt tests (alone with 1 → no note; 2 → note;
  another instance running → note).
- [ ] 5.2 Keep-awake with two instances (D10): no code change expected. Verify on Windows with a check script run in
  this session (not committed as a test if it needs admin rights): two processes each holding a
  `SetThreadExecutionState` request, one ends, `powercfg /requests` (when it can run) still lists the other; record
  the result, or that `powercfg /requests` needed rights it did not have and the documented Windows behaviour was
  relied on, under "Apply results". Add a unit test that two `Keeper`s with fake `set_state` clear only their own
  request.

## 6. Visibility and documentation

- [ ] 6.1 `status` command (D9): machine directory, limits or error, other instances, slots in use, shared usage and
  hold, this configuration's conflicts; read-only, not blocked by the run lock; removes stale records. Start lines of
  `run` / `once` and the `dry-run` lines (D9). Verify with tests: `status` while a fake instance A runs one session
  lists A's configuration path and `1 session running`, limits, usage; a killed A is not listed; start line names A;
  dry-run prints the machine slot line; no handover / team / title of A appears in B's output.
- [ ] 6.2 Docs: `machine.toml.example` (repository root); `radark/README.md` (machine directory, limits, shared usage,
  session and test-run limits, repository ownership, `status`, `test-slot`, keep-awake note, team `CLAUDE.md` rule
  for `radark-test-slot`); root `README.md` short mention; `harness.toml.example` comment at `parallel_sessions`
  pointing to the machine limit; `radark/sandbox/make_sandbox.py` sets a sandbox-local `RADARK_MACHINE_DIR` in what it
  prints / writes. Verify: names are neutral (`pipeline-a`, `pipeline-b`, `app`, `backend`); no private paths.
- [ ] 6.3 Sandbox check (manual end-to-end, D9): two sandboxes (or two configurations of one sandbox) on one
  `RADARK_MACHINE_DIR`; `run` of the second with a shared repository → refusal line; `dry-run` of the second while
  the first runs → conflict and machine lines; `status` lists the first. Record the observed lines (neutral names)
  under "Apply results".

## 7. Finish

- [ ] 7.1 Full suite `python -m pytest radark/tests` passes; failing or flaky tests follow hub `AGENTS.md` §10 (no
  retries or skips to hide a flake). Record the test count under "Apply results".
- [ ] 7.2 Commit locally (no push, tag, release or reinstall), citing HO-20261114-cda3.
- [ ] 7.3 `ho done HO-20261114-cda3 -m "..."` listing: change name `machine-wide-instances`, commits, new settings
  with defaults (`machine.toml` `sessions = 2`, `test_runs = 1`; `RADARK_MACHINE_DIR`), new commands (`status`,
  `test-slot`), test count, any split or deviation. This is the last step of apply; `ho sync` before and after.

## Apply results

(filled in by the apply session)
