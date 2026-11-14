# Design: parallel sessions

## Context

Today `Dispatcher.loop` (radark/__main__.py) picks one candidate (`sel.pick`) and calls `run_candidate` or
`resume_with_answer`, which blocks in `Runner.run` until the session ends, then triage, `after_session` and the
`running` record are processed in the same thread. Single-session assumptions in the code:

- one `self.runner` (one `proc`, one `kill`) and one `self.check_runner` (the limit check next to the session);
- one `self._running` (for the `suspend` log event) and one `state.meta["running"]` record (recovery, design D6 of
  sleep-aware);
- `_on_interrupt` sets `stop_after_session` and, on the second press, kills the one runner and the one check runner;
- `self.goal.sessions` and the goal's step list are counted from the one thread; state (`state.json`), run log
  (`runs.jsonl`) and console (`Tee` to `console.log`) are written from the one thread;
- the idle ask (`idle_ask`, with `idle_due`, `did_regular` streak, `idle_reask_minutes`, `idle_escalation`) and the
  goal check (`goal_check`) run only when nothing is selectable, so they never run next to work.

What already isolates a session: its own temp directory `<run_dir>/tmp/<team>/` with `TEMP`/`TMP`/`TMPDIR`
(fewer-owner-waits D5), hooks that deny writing to the system temp directory, stopping processes by name or outside
the session's process tree, and whole-tree `git restore`. What does not: a process that detached from the session's
tree survives the session (`taskkill /T` follows parent links only), and processes still running when `claude`
exits normally are never ended. The hub (`ho`) is a git working copy; `ho sync` is `git pull --rebase`, commit and
push with no lock, and agents and the dispatcher call it independently.

What sessions of different teams share on one computer, in general: the machine (slower runs; timing-sensitive tests
may turn flaky), fixed ports of test servers and emulators, fixed temp file names, stopping processes by name, one
Docker daemon where two stacks may use the same compose project name, Claude usage limits, the hub and the
dispatcher itself. The dispatcher removes what it controls (processes, temp, hub, its own state); the rest is each
team's tooling, which the product team handles per pipeline (not this change).

## Goals / Non-Goals

**Goals:** run unrelated work of different repositories at the same time; no interference between sessions from what
the dispatcher and the hub control; `parallel_sessions = 1` behaves as today; room for RB-001 (several pipeline
instances on one PC) later.

**Non-Goals:** no resource rules (no "one test run at a time", no machine-wide e2e lock, no CPU/memory limits); no
parallelism inside one repository (one git working tree, one change in progress); no change to selection order,
holds, triage, escalation or limits beyond what parallel running needs; `plan` stays a sequential prediction;
nothing for several dispatcher instances (RB-001): the run lock stays per run directory, and nothing here assumes
the dispatcher is the only user of the computer.

## Decisions

### D1. Worker threads in one dispatcher process

The main thread keeps the loop: checks (STOP, PAUSE, `--until`, budget, usage hold, back-off, goal limits), hub scan,
holds, owner answers, selection, starts. For each started session it starts a worker thread that runs today's path to
its end: `run_candidate` / `resume_with_answer` → `session` (with its limit check and wrap-up) → triage → `finish` /
`after_session`. The main thread then waits on a condition (a worker ended, or the poll interval) instead of blocking
in the session.

- **Shared lock:** one `threading.RLock` (`self.lock`) guards every shared write: state edits and `state.save`,
  `log.write`, `out`/`problem` (whole lines, never half a line), the goal record (`goal.sessions`, steps,
  `goal_save`), usage readings (`on_usage` already runs in the stream thread), `idle_*` meta. Hub calls are separate
  `ho` processes; their order is the hub lock's job (D6), so they run outside `self.lock`. Long work (sessions, hub
  calls, git snapshots) never runs while the lock is held.
- **Runner per session:** a small pool: `self.runners: dict[str, Runner]` keyed by a worker key (team), each with its
  own limit-check runner. `get_runner()` keeps working for the single-session path and tests; tests can inject a
  runner factory (`runner_factory(cfg) -> Runner`) so two fake runners can run at once.
- **Per-worker context:** what is per session today in single fields (`_running`, `check_runner`,
  `_cleanup_pending`) moves to a per-worker context object passed down (or a `threading.local`); `self._running`
  becomes `dict[key, info]` and the `suspend` event's `during` lists all running sessions.
- **Signals:** SIGINT is handled only in the main thread (Python delivers it there). First press: `stop_after_session`
  (no new starts; a line names how many sessions finish). Second press: every runner and every check runner is
  killed; each worker processes its `interrupted` (cause owner) result as today.
- **N = 1:** the same code with at most one worker; with `parallel_sessions = 1` the main thread may still run the
  worker inline (implementation choice); the observable behaviour and the existing tests stay as they are.

Alternatives: a dispatcher process per team (state and selection would need inter-process locking; rejected);
asyncio (runner and hub are blocking subprocess code; a rewrite for the same result; rejected).

### D2. Selection of several candidates

`sel.pick` stays the rule for "next". New `sel.pick_free(cands, busy_repos, busy_handovers)` returns the first
candidate (in `sel.ordered` order) whose team repository (resolved path, so two teams sharing a repository count as
one) and handover have no running session. The main thread calls it while `running < parallel_sessions`. A review
candidate's worker team (`_worker`) is the session's team. "Unrelated" needs no new rule: dependent work is already
held (*Waiting for a handover's result*), a handover has one record, one repository runs one session. Owner-answer
resumes go first and take a place; an answer for a busy repository or handover waits like a candidate.

### D3. Whole-hub steps next to running work

The idle ask and the goal check run in the product team's repository and take a place. They may start while other
sessions run when: a place is free, no candidate and no owner answer can use it, the product repository is free, and
the step is due by its own rule (`idle_due` for the idle ask: hub activity, retry, `did_regular` streak, re-ask time;
for the goal check: G3 of goal-run). Their prompt gets a "work in progress" section listing each running session
(team, handover, title, phase) and this text:

> Work in progress right now (other sessions are working on it): <list>. Hand over or start only work that does not
> depend on these results and does not touch these handovers or the changes they work on; do not report them as
> stalled.

With nothing running the section is absent (prompt as today).

- `did_regular` and the streak: unchanged; a `did_regular` makes the next ask due at once, which can again run next
  to the running work.
- `idle_escalation` / `idle_escalation_skipped`: unchanged (one escalation per set of owner-waiting items).
- `idle_reask_minutes`: the awake mark `_idle_mark` is set at the end of the last session of any kind (as today, per
  ended session).
- Goal run: a goal check that finds nothing selectable while a session runs is not repeated for the same hub state
  (`hub_latest` unchanged since the last check): the main thread waits for a worker to end or for hub activity
  (poll) instead of asking again. This keeps `empty_continues` / the `stalled` rule from counting checks that only
  waited for running work. A verdict `complete` or `blocked` sets "ending": no new starts, the run ends with that
  status after all workers are processed. A goal check is never started while the run is "ending".

### D4. State, recovery, console

- `state.meta["running"]` becomes `{session_id: {...}}` (same record fields as today). Reading an old single record
  (has a `session` key at the top level) treats it as one entry. Each worker adds its entry in `on_start` and removes
  it in `finish` (under the lock).
- `recover()` loops over the entries; each is handled as *Recovery of an interrupted session* says today (leftover
  process ended, `!` line, `interrupted` event, resume or run again when due).
- Console: with `parallel_sessions > 1`, a start line gets `(N running)` when N, counting the new one, is more than 1;
  end lines always carry the handover ID (or the step kind) in addition to team and phase, also with N = 1 (end lines
  that already carry them in goal steps are unchanged). Lines are written whole under the lock.
- `--max-sessions` and the goal's `max_sessions` count started sessions; at the maximum, no new starts; the run ends
  after the running ones.

### D5. A session's processes end with it

- **Windows:** right after `Popen`, `Runner` creates a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and
  assigns the `claude` process to it (ctypes, `kernel32`: `CreateJobObjectW`, `SetInformationJobObject`,
  `AssignProcessToJobObject`, `TerminateJobObject`, `CloseHandle`). Children inherit the job, also detached ones
  whose parent has exited. When the session ends in any way (normal exit, time limit, wrap-up stop, sleep, owner,
  kill), the runner terminates and closes the job, which ends every process left in it. `kill_tree` / `kill_pid_tree`
  stay as the fallback when the job cannot be created or assigned (logged once as `job_object_unavailable`). Nested
  jobs (Windows 8+) let this work when the dispatcher itself runs inside a job. Assigning right after `Popen` leaves a
  tiny window before the first child; acceptable, `claude` starts children only after start-up. If the dispatcher
  process dies, the OS closes the job handle and the session's processes end with it; recovery still treats the
  session as interrupted.
- **Elsewhere:** `start_new_session=True` on `Popen` and, at the session's end, `os.killpg` of that group (SIGKILL).
  A process that starts its own session leaves the group; accepted as a limit off Windows (the owner's pipelines run
  on Windows). `kill_pid_tree` stays as the fallback.
- Limit-check and triage consultations run through a `Runner` too and get the same treatment.
- Each session's job / group is its own, so ending one never touches another session's processes.

### D6. Hub lock: radark-handover's change, required for N > 1

`ho` serialises its hub writes and `sync`: an exclusive OS lock on `<hub>/.ho.lock`, bounded wait with a clear
error, released by the OS on a crash, ignored by git, read commands do not wait. This is radark-handover's work in
its own repository (code, tests, JSON contract), requested with HO-20261114-23cx; radark-handover may choose a better
variant, and this change adopts its result before it is finished (task 0.1).

**How the engine knows the installed `ho` has the lock:** proposed to radark-handover: an additive field in
`ho --version --json` (`"hub_lock": true`, or a feature list), contract staying 1 so older engines are not broken.
The RB-003 start check (`check_ho`) returns it with the version; when `parallel_sessions > 1` and the `ho` does not
report the lock, `run`, `once` and `dry-run` stop with exit code 2 before any session, with one message naming the
`ho` version found, that the hub lock is needed for `parallel_sessions > 1`, and the two ways out (install a
radark-handover with the lock, or set `parallel_sessions = 1`). `plan` (sequential) does not require it. With
`parallel_sessions = 1` nothing changes. If radark-handover answers with another signal (a contract bump or a version
minimum), D6 and task 4.1 follow its answer.

The dispatcher's own hub writes (escalations, team-decision notices, `ho sync`) from several workers are separate
`ho` processes and need no extra lock in the engine.

### D7. Environment variable and prompt note

- `HARNESS_PARALLEL_SESSIONS` = the configured `parallel_sessions`, set for every session (also with 1), next to the
  `HARNESS_*` variables the engine already exports (`HARNESS_RUN_DIR`, `HARNESS_SESSION`, `HARNESS_TEAM`,
  `HARNESS_TEMP`, ...). Teams' scripts may adapt (e.g. pick free ports). The draft's `HARNESS_PARALLEL` was renamed
  to match the configuration key; the prefix stays `HARNESS_` like every variable the engine exports (the rename to
  `radark` kept configuration and run file names).
- Parallel note, added to work prompts (phase prompts, resumes after a time limit or an owner answer) only when
  `parallel_sessions > 1`:

> Another team may be working on this computer at the same time. Stop only processes you started yourself, by
> their ID (never by name or image, never "all node" or "any playwright"); use no fixed shared ports or paths outside
> your repository and your temp directory; expect runs to be slower than usual.

### D8. dry-run

dry-run prints, after "Would start: …", one line `In parallel (parallel_sessions = N): <team> <phase> <handover>; …`
with the further candidates `pick_free` would start in the same loop, or `In parallel: nothing else can start
(<reason>)`; with N = 1 the output is as today. `plan` is unchanged.

### Deviations from the draft (`harness-parallel-teams`, 2026-11-10)

1. Paths: `radark/` instead of `harness/`, `python -m radark`, tests in `radark/tests`.
2. Environment variable `HARNESS_PARALLEL_SESSIONS` instead of `HARNESS_PARALLEL` (D7).
3. Temp directory: the draft's per-session `<run_dir>/tmp/<session_id>` (removed after processing) is dropped. Since
   2026-11-10 every session already has `<run_dir>/tmp/<team>/` (fewer-owner-waits D5) and the dispatcher must not
   delete files in it; one repository runs one session at a time, so it is already per session. The existing
   requirement *Session temp directory* is unchanged.
4. Hub lock (draft task 1, D6): radark-handover's change (HO-20261114-23cx); the engine only requires the lock signal
   for N > 1 (D6). The draft's "manual check in the real hub" is radark-handover's and product's check.
5. Dropped: the handover to a pipeline's product team asking teams to remove interference (draft D7, task 4.2),
   `parallel_sessions = 2` in a pipeline's `harness.toml` (task 4.3; only documented in `harness.toml.example` and
   the README), the integration run with the owner (task 5.1), deleting the owner's idea note.
6. Privacy: the draft's run times, handover and item IDs, ports, compose project names and folder layouts are
   replaced by neutral text (Context).
7. Integration with later changes: RB-015 wrap-up, RB-014 denial handling / triage / team-decision notices, RB-005
   idle ask and goal check, RB-003 `ho` check, keep-awake and usage hold / budget (D1, D3, D6, D9).
8. Processes are also ended when a session ends normally, not only when it is killed (D5); a process group fallback
   off Windows.
9. Goal check next to running work is not repeated for the same hub state (D3), so the `stalled` rule is not
   triggered by waiting.

### D9. Run-wide things shared by all sessions

- **Keep-awake:** one keeper for the whole run, as today (it does not depend on the number of sessions).
- **Usage hold / budget / back-off:** checked by the main thread before every new start; a usage-limit hit of one
  session sets the back-off for new starts and does not end the other sessions. Usage readings from all sessions
  update the same per-window record (under the lock); running sessions may overshoot the threshold by one session
  each.
- **`--until`, STOP, PAUSE, goal limits:** stop new starts; the run ends after the last worker (D1, spec "Run
  control with parallel sessions").
- **Sleep:** the sleep watch is checked by the main thread and each runner as today; the `suspend` event lists all
  running sessions; each runner applies its own wake grace.

## Risks / Trade-offs

- [A shared resource the dispatcher does not control (a port, a compose project name) makes a test fail only in
  parallel] → it shows as an infra failure; the stable-tests rule sends it to the backlog; the owner can set
  `parallel_sessions = 1` at once.
- [Slower sessions hit the inactivity or maximum limits more often] → limits count awake time; limit checks extend
  progressing sessions; watched in the first parallel runs, not changed in advance.
- [Usage windows drain faster] → the usage hold stops new starts at the threshold; running sessions may overshoot by
  one session each.
- [Thread-safety bugs] → one lock around all shared writes; tests with two fake runners ending in both orders;
  `parallel_sessions = 1` keeps one worker.
- [Ending a session's processes at a normal end stops something a team expected to outlive the session] → nothing
  should outlive a session by design; if a team relies on it, it shows at once and is a team fix.
- [Job object creation fails (rights, policy)] → fallback to `kill_tree`, logged once; isolation is then as today.
- [An old `ho` without the lock with N > 1] → stopped at start (D6), never run unlocked.

## Migration Plan

Default `parallel_sessions = 1` keeps today's behaviour (plus processes ending with their session). The owner sets
2 in a pipeline's `harness.toml` after this change and radark-handover's lock are installed. Rollback: set
`parallel_sessions = 1`. An old `state.json` with a single `running` record is read as one entry.

## Open Questions

- Whether `parallel_sessions` should later be 3 (product sessions next to both technical ones) — decided by the
  first parallel runs, without changing this design.

## Assumptions (unattended propose session)

- One change, not split: the per-session temp directory already exists, so the isolation part is small (job object,
  prompt note, environment variable); tasks are ordered so isolation lands first and helps with one session.
- The hub-lock signal shape (`"hub_lock": true` in `ho --version --json`) is our proposal; radark-handover decides.
- Stop at start (exit 2) rather than falling back to one session when the `ho` has no lock and N > 1: a silent
  fallback would hide a configuration the owner asked for.
- `parallel_sessions` counts work sessions and whole-hub steps; limit checks and triage consultations do not count.
