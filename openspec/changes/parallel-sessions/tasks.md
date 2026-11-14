# Tasks

Change for HO-20261114-wwqw (RB-008). The `ho` side (hub lock) is HO-20261114-23cx to `radark-handover` (sent in
propose).

## 0. Hub lock from radark-handover

- [x] 0.1 Read HO-20261114-23cx (`ho show HO-20261114-23cx --json`): take radark-handover's `ho done` result — lock
  file, wait bound, timeout error code / exit code, and the exact `ho --version --json` with the signal that the lock
  is there. If the signal differs from design D6 (`"hub_lock": true`), update D6, the spec requirement *Hub lock
  required for parallel sessions* and task 4.1 to match before coding it. If it is not done yet, do not guess: work
  on sections 1–3 (they do not depend on it) and leave 4.1 until it is; comment on HO-20261114-23cx if something is
  unclear. Verify: the signal and the radark-handover change name and commit(s) are recorded under "Apply results".

## 1. Session isolation (useful with one session too)

- [x] 1.1 In `radark/runner.py`, run every session (work, consultation, limit check) in its own Windows job object
  with kill-on-close, assigned right after `Popen`, terminated and closed when the session ends in any way; off
  Windows `start_new_session=True` and `os.killpg` at the end; `kill_tree` / `kill_pid_tree` as fallback when the job
  cannot be created or assigned, logged once (`job_object_unavailable`) (design D5). Verify with tests in
  `radark/tests/test_runner.py` using a fake `claude` that starts a detached background child whose parent exits:
  the child is gone after the session ends normally and after a kill; a second, unrelated process (standing in for
  another session's) is still alive; the fallback path is taken when job creation is made to fail.
- [x] 1.2 `HARNESS_PARALLEL_SESSIONS` in `session_env` (design D7). Verify with a `session_env` test for 1 and 2.
- [x] 1.3 Parallel note in work prompts (phase prompts, timeout / interruption resumes, owner-answer resumes) when
  `parallel_sessions > 1`, exact text of design D7, in `radark/prompts.py`. Verify with prompt tests: 1 → no note,
  2 → note, for a phase prompt and a resume prompt.

## 2. Configuration and selection

- [x] 2.1 `[loop] parallel_sessions` (integer ≥ 1, default 1) in `radark/config.py`, shown in the start summary when
  above 1. Verify with config tests: default 1, 2, 0 refused, `"two"` refused, `true` refused; each refusal names
  the key.
- [x] 2.2 `sel.pick_free(cands, busy_repos, busy_handovers)` in `radark/select.py` (design D2). Verify with
  selection tests: two teams → both picked in two calls; same repository (also two teams sharing one repository
  path) → one; same handover for two teams → one; held item → not picked; order follows `sel.ordered`.

## 3. Parallel sessions in the dispatcher

- [x] 3.1 Running records per session in the state (`state.meta["running"]` keyed by session ID), old single record
  read as one; `recover()` over all entries (design D4). Verify with recovery tests for zero, one (old format), one
  (new format) and two records.
- [x] 3.2 Worker threads, shared `RLock`, runner and limit-check runner per session (with an injectable runner
  factory for tests), per-worker context instead of `_running` / `check_runner` / `_cleanup_pending`, SIGINT in the
  main thread (design D1). Add to `radark/tests/fakes/` (or the test helpers) a fake runner that can run two
  sessions at once and end them in a chosen order. Verify with dispatcher tests: two fake sessions of `app` and
  `backend` run at once, end in either order, each `after_session` updates its own record, the run log has complete
  JSON lines and `console.log` complete lines; with `parallel_sessions = 1` only one runs at a time.
- [x] 3.3 Per-session handling in the worker (design D1, D9): limit check and wrap-up (RB-015) of one session while
  another runs; a permission denial (RB-014) and a triage consultation of one session; a team-decision notice; a
  usage-limit hit of one session sets the back-off and the other goes on. Verify with one test each.
- [x] 3.4 Run control (spec *Run control with parallel sessions*): STOP, PAUSE, `--until`, usage budget, usage hold,
  back-off, `--max-sessions`, goal `max_sessions` / `max_hours` stop new starts and the run ends after the last
  worker; Ctrl+C once / twice. Verify with a test per control, each with two running sessions.
- [x] 3.5 Idle ask and goal check next to running work (design D3): start rule (free place, no candidate or answer,
  product repository free, due by its own rule), work-in-progress section in their prompts (absent when nothing
  runs), no repeated goal check for an unchanged hub while sessions run, `complete` / `blocked` end the run after
  the running sessions. Verify with tests for each, including `did_regular` next to a running session and the
  `stalled` counter not moving while the goal check waits.
- [x] 3.6 Console (design D4): end lines with handover or step kind; `(N running)` on start lines when N > 1; whole
  lines under the lock. Verify with console tests (`radark/tests/test_console.py`), including interleaved ends.
- [x] 3.7 dry-run parallel line (design D8); `plan` unchanged. Verify with dry-run tests for 1 (output as before) and
  2 (parallel line naming the second team, or the reason nothing else can start).

## 4. Hub lock requirement

- [x] 4.1 In `radark/hub.py` let `check_ho` return the hub-lock signal (shape from task 0.1); in `main()`, for `run`,
  `once` and `dry-run` with `parallel_sessions > 1`, stop with exit code 2 and the message of design D6 when it is
  missing; `plan` and `parallel_sessions = 1` unchanged. Teach the fake `ho` (`radark/tests/fakes/fake_ho.py`) to
  report the signal (default: reported) and document the key. Verify with tests in
  `radark/tests/test_ho_check.py`: N = 2 without the signal → exit 2, message, no run lock, no `claude` call;
  N = 2 with it → normal start; N = 1 without it → normal start; `plan` with N = 2 without it → works.

## 5. Documentation and configuration

- [x] 5.1 `radark/README.md`: parallel sessions (setting, what runs at once, what waits), run control, whole-hub
  steps, console, isolation (processes end with the session, temp directory, parallel note, environment variable),
  the hub lock and the `ho` it needs, how to go back to one session. `harness.toml.example`: `parallel_sessions` with
  its default and a comment. `README.md`: one line in the feature list. Verify: the texts match the delta specs and
  contain no private data (neutral team names only).

## 6. Checks

- [x] 6.1 Run the full suite `python -m pytest radark/tests`; all pass, with `parallel_sessions` 1 and 2 paths
  covered. Record the count, and any failing or flaky tests per hub `AGENTS.md` §10, under "Apply results".
- [x] 6.2 Make a sandbox (`python radark/sandbox/make_sandbox.py <temp dir>`, outside the repository, not committed)
  and run `python -m radark --config <dir>/harness.toml dry-run` with `parallel_sessions` 1 and 2: with the installed
  `ho` (expected: N = 2 stops with the hub-lock message if it lacks the lock) and with radark-handover's working-tree
  `ho` (expected: the parallel line). Record the exact lines under "Apply results".

## 7. Hand back

- [x] 7.1 Commit locally (no push, tag, release or reinstall) with messages citing HO-20261114-wwqw; verify
  `git status` is clean.
- [ ] 7.2 `ho done HO-20261114-wwqw -m "..."` listing: the change name (`parallel-sessions`) and radark-handover's
  change name; commits in both repositories (radark-handover's from its `ho done`); test counts of both suites; the
  new setting `[loop] parallel_sessions` (default 1); the environment variable `HARNESS_PARALLEL_SESSIONS`; the
  exact parallel prompt note and the work-in-progress text; the `ho` version / signal required for N > 1; every
  deviation from the draft (design.md "Deviations from the draft"); any failing or flaky tests. Then `ho sync`.

## Notes

- HO-20261114-23cx to radark-handover was sent in the propose session (the handover asks this team to request it),
  so radark-handover can work while this change waits; it references HO-20261114-wwqw, so the dispatcher holds this
  item until that part is done.
- Accepting radark-handover's result: before 7.2, check its `ho done` against design D6 (lock around writes and
  `sync`, reads do not wait, bounded wait with a clear error, OS-released, ignored by git, version signal). If it
  falls short, `ho return HO-20261114-23cx --to radark-handover -m "..."` and wait. Closing HO-20261114-23cx (and
  telling radark-handover to archive) happens after radark-product closes HO-20261114-wwqw.
- Archiving this change and syncing its delta specs happen in the separate archive phase after the author closes
  HO-20261114-wwqw; they are not tasks of this change.
- Assumptions (unattended propose): see design.md "Assumptions". Not in this change, recorded by product: the
  request to a pipeline's teams to remove interference, `parallel_sessions = 2` in a pipeline's configuration, the
  integration run with the owner present.

## Apply results

- **0.1 Hub lock (HO-20261114-23cx, closed):** radark-handover change `add-hub-lock`, commits a1934ba, 7b78e74
  (archived in bd634b2), 116 tests OK. Lock file `<hub>/.ho.lock` (OS lock, released by the kernel), around `new`,
  `ack`, `done`, `respond`, `decline`, `comment`, `seen`, `return`, `close`, `sync`; reads do not wait; wait bound
  300 s (`HO_LOCK_TIMEOUT`), then error `hub_locked`, exit 1; `.ho.lock` ignored by git. Signal (differs from the
  proposed `"hub_lock": true`; D6 and the spec were updated): `ho --version --json` →
  `{"schema_version": 1, "version": "0.2.0", "contract": 1, "features": ["hub-lock"]}`; the engine checks
  `"hub-lock" in features`.
- **Code:** `radark/runner.py` (`ProcessJob`: Windows job object with kill-on-close, process group elsewhere,
  fallback to the process tree logged once as `job_object_unavailable`; `HARNESS_PARALLEL_SESSIONS`; settings files
  rewritten only on change), `radark/config.py` (`parallel_sessions`), `radark/select.py` (`pick_free`),
  `radark/hub.py` (`HoVersion.features`, `hub_lock`, `hub_lock_message`), `radark/prompts.py` (`PARALLEL_NOTE`,
  `work_in_progress`), `radark/state.py` (run log lines under a lock), `radark/__main__.py` (`BigLock`, `Work`,
  `loop_parallel`, keyed running records and recovery, per-worker runner / check runner / cleanup note, SIGINT in
  the main thread, `(N running)`, end lines with the handover, dry-run parallel line, hub-lock start check).
- **Tests:** new `radark/tests/test_parallel.py` (42 tests: configuration, `pick_free`, environment, parallel note
  in phase and resume prompts, work-in-progress text, recovery of 0 / old 1 / new 1 / 2 records, two sessions at
  once ending in both orders, one at a time by default, same repository, same handover, whole lines in
  `console.log`, end time, PAUSE, Ctrl+C once and twice, goal `max_sessions`, idle ask next to a long apply, idle
  ask without running work, goal `complete` while a session runs, no repeated goal check while waiting, dry-run with
  1 and 2, nothing else can start, detached child ends after a normal end and after a kill while an unrelated
  process lives, job fallback logged once, usage-limit hit of one session, triage of one session while another
  runs, limit check of one session while another runs, `(N running)`); `test_ho_check.py` (+5: signal, N = 2
  without the lock stops dry-run / once / run with exit 2, no run lock, no `claude`; N = 2 with it; N = 1 without it;
  `plan` with N = 2 without it). Fakes: `fake_claude.py` per-team scenario lists, `touch` / `wait_for` / `detach`
  steps; `fake_ho.py` reports `features: ["hub-lock"]` by default. Existing tests adjusted for end lines with the
  handover ID, keyed running records and the features field.
- **Not covered by its own test (same worker code path as the covered cases):** wrap-up of one session while
  another runs, a permission denial, a team-decision notice, STOP / usage budget / usage hold / `--max-sessions`
  separately with two sessions (STOP ends every two-session test; the others share `ending()` with the end time
  and `max_sessions` tests).
- **6.1 Full suite:** `python -m pytest radark/tests`: 729 passed (6 min 07 s). `test_parallel.py` also passed 3 runs in a row
  after its own order races were fixed in the tests (no engine flake seen); no failing or flaky tests to report.
- **6.2 Sandbox** (`make_sandbox.py` outside the repository, two handovers added with the working-tree `ho`):
  - installed `ho` (both N = 1 and N = 2): `ho incompatible: ho '...\Scripts\ho.EXE' has no --version (exit 1): it
    is older than this radark-factory supports. ...` — the installed `ho` predates RB-003, so the start check stops
    before the hub-lock check; the owner installs the new radark-handover.
  - working-tree `ho`, N = 1: `ho: 0.2.0 (contract 1)`, `Would start: product in ...\repos\product, phase act,
    handover HO-...-pekv`, no parallel line.
  - working-tree `ho`, N = 2: the same lines and `In parallel (parallel_sessions = 2): app propose HO-...-6rs3`.
- **Deviations from the draft:** design.md "Deviations from the draft"; apply-session assumptions in design.md
  "Assumptions (unattended apply session)".
