# Tasks

Change for HO-20261114-wwqw (RB-008). The `ho` side (hub lock) is HO-20261114-23cx to `radark-handover` (sent in
propose).

## 0. Hub lock from radark-handover

- [ ] 0.1 Read HO-20261114-23cx (`ho show HO-20261114-23cx --json`): take radark-handover's `ho done` result — lock
  file, wait bound, timeout error code / exit code, and the exact `ho --version --json` with the signal that the lock
  is there. If the signal differs from design D6 (`"hub_lock": true`), update D6, the spec requirement *Hub lock
  required for parallel sessions* and task 4.1 to match before coding it. If it is not done yet, do not guess: work
  on sections 1–3 (they do not depend on it) and leave 4.1 until it is; comment on HO-20261114-23cx if something is
  unclear. Verify: the signal and the radark-handover change name and commit(s) are recorded under "Apply results".

## 1. Session isolation (useful with one session too)

- [ ] 1.1 In `radark/runner.py`, run every session (work, consultation, limit check) in its own Windows job object
  with kill-on-close, assigned right after `Popen`, terminated and closed when the session ends in any way; off
  Windows `start_new_session=True` and `os.killpg` at the end; `kill_tree` / `kill_pid_tree` as fallback when the job
  cannot be created or assigned, logged once (`job_object_unavailable`) (design D5). Verify with tests in
  `radark/tests/test_runner.py` using a fake `claude` that starts a detached background child whose parent exits:
  the child is gone after the session ends normally and after a kill; a second, unrelated process (standing in for
  another session's) is still alive; the fallback path is taken when job creation is made to fail.
- [ ] 1.2 `HARNESS_PARALLEL_SESSIONS` in `session_env` (design D7). Verify with a `session_env` test for 1 and 2.
- [ ] 1.3 Parallel note in work prompts (phase prompts, timeout / interruption resumes, owner-answer resumes) when
  `parallel_sessions > 1`, exact text of design D7, in `radark/prompts.py`. Verify with prompt tests: 1 → no note,
  2 → note, for a phase prompt and a resume prompt.

## 2. Configuration and selection

- [ ] 2.1 `[loop] parallel_sessions` (integer ≥ 1, default 1) in `radark/config.py`, shown in the start summary when
  above 1. Verify with config tests: default 1, 2, 0 refused, `"two"` refused, `true` refused; each refusal names
  the key.
- [ ] 2.2 `sel.pick_free(cands, busy_repos, busy_handovers)` in `radark/select.py` (design D2). Verify with
  selection tests: two teams → both picked in two calls; same repository (also two teams sharing one repository
  path) → one; same handover for two teams → one; held item → not picked; order follows `sel.ordered`.

## 3. Parallel sessions in the dispatcher

- [ ] 3.1 Running records per session in the state (`state.meta["running"]` keyed by session ID), old single record
  read as one; `recover()` over all entries (design D4). Verify with recovery tests for zero, one (old format), one
  (new format) and two records.
- [ ] 3.2 Worker threads, shared `RLock`, runner and limit-check runner per session (with an injectable runner
  factory for tests), per-worker context instead of `_running` / `check_runner` / `_cleanup_pending`, SIGINT in the
  main thread (design D1). Add to `radark/tests/fakes/` (or the test helpers) a fake runner that can run two
  sessions at once and end them in a chosen order. Verify with dispatcher tests: two fake sessions of `app` and
  `backend` run at once, end in either order, each `after_session` updates its own record, the run log has complete
  JSON lines and `console.log` complete lines; with `parallel_sessions = 1` only one runs at a time.
- [ ] 3.3 Per-session handling in the worker (design D1, D9): limit check and wrap-up (RB-015) of one session while
  another runs; a permission denial (RB-014) and a triage consultation of one session; a team-decision notice; a
  usage-limit hit of one session sets the back-off and the other goes on. Verify with one test each.
- [ ] 3.4 Run control (spec *Run control with parallel sessions*): STOP, PAUSE, `--until`, usage budget, usage hold,
  back-off, `--max-sessions`, goal `max_sessions` / `max_hours` stop new starts and the run ends after the last
  worker; Ctrl+C once / twice. Verify with a test per control, each with two running sessions.
- [ ] 3.5 Idle ask and goal check next to running work (design D3): start rule (free place, no candidate or answer,
  product repository free, due by its own rule), work-in-progress section in their prompts (absent when nothing
  runs), no repeated goal check for an unchanged hub while sessions run, `complete` / `blocked` end the run after
  the running sessions. Verify with tests for each, including `did_regular` next to a running session and the
  `stalled` counter not moving while the goal check waits.
- [ ] 3.6 Console (design D4): end lines with handover or step kind; `(N running)` on start lines when N > 1; whole
  lines under the lock. Verify with console tests (`radark/tests/test_console.py`), including interleaved ends.
- [ ] 3.7 dry-run parallel line (design D8); `plan` unchanged. Verify with dry-run tests for 1 (output as before) and
  2 (parallel line naming the second team, or the reason nothing else can start).

## 4. Hub lock requirement

- [ ] 4.1 In `radark/hub.py` let `check_ho` return the hub-lock signal (shape from task 0.1); in `main()`, for `run`,
  `once` and `dry-run` with `parallel_sessions > 1`, stop with exit code 2 and the message of design D6 when it is
  missing; `plan` and `parallel_sessions = 1` unchanged. Teach the fake `ho` (`radark/tests/fakes/fake_ho.py`) to
  report the signal (default: reported) and document the key. Verify with tests in
  `radark/tests/test_ho_check.py`: N = 2 without the signal → exit 2, message, no run lock, no `claude` call;
  N = 2 with it → normal start; N = 1 without it → normal start; `plan` with N = 2 without it → works.

## 5. Documentation and configuration

- [ ] 5.1 `radark/README.md`: parallel sessions (setting, what runs at once, what waits), run control, whole-hub
  steps, console, isolation (processes end with the session, temp directory, parallel note, environment variable),
  the hub lock and the `ho` it needs, how to go back to one session. `harness.toml.example`: `parallel_sessions` with
  its default and a comment. `README.md`: one line in the feature list. Verify: the texts match the delta specs and
  contain no private data (neutral team names only).

## 6. Checks

- [ ] 6.1 Run the full suite `python -m pytest radark/tests`; all pass, with `parallel_sessions` 1 and 2 paths
  covered. Record the count, and any failing or flaky tests per hub `AGENTS.md` §10, under "Apply results".
- [ ] 6.2 Make a sandbox (`python radark/sandbox/make_sandbox.py <temp dir>`, outside the repository, not committed)
  and run `python -m radark --config <dir>/harness.toml dry-run` with `parallel_sessions` 1 and 2: with the installed
  `ho` (expected: N = 2 stops with the hub-lock message if it lacks the lock) and with radark-handover's working-tree
  `ho` (expected: the parallel line). Record the exact lines under "Apply results".

## 7. Hand back

- [ ] 7.1 Commit locally (no push, tag, release or reinstall) with messages citing HO-20261114-wwqw; verify
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

(filled in during apply)
