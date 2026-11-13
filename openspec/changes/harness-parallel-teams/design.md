# Design

## Context

See proposal.md - Why. Today `Dispatcher.loop` picks one candidate (`sel.pick`) and calls `run_candidate`, which
blocks in `Runner.run` until the session ends. One `Runner` (one `proc`, one `kill`), one `self._running`, one
`state.meta["running"]`, SIGINT handler set around each session, `limit_watch` and the limit-check runner are per
session but held in single fields. State (`state.json`), run log (`runs.jsonl`) and console (`Tee` to `console.log`)
are written from the one thread. The hub (`ho`) is a git working copy; `ho sync` is `git pull --rebase`, commit, push,
with no locking; agents call `ho` themselves, and the dispatcher calls it through `Hub`.

What the two technical teams share on the owner's computer (checked 2026-11-09, from the owner's idea note
`docs/ideas/parallel-teams-mode.md`, which this change replaces):
- *Not shared by design:* ports and databases (backend e2e 8081 + Postgres 5433; extension e2e backend test mode 8082 +
  Postgres 5434, test site 4310, LLM emulator 4320; backend dev 8080 / 5432); backend code (the extension's e2e runs on
  its own clone of the backend, `app/tests/e2e/.backend/backend`, not on the backend team's working tree);
  browsers (each Playwright run starts its own Chrome).
- *Shared:* the machine (16 GB RAM, i5-1235U: slower runs, timing-sensitive tests such as the backend's grace-period
  test BL-101 may turn flaky); **Docker** - one daemon, and both stacks use the compose project name `backend`
  (same folder name), so a `down` of one may touch the other's containers or network; Claude usage limits; agents
  that stop processes before e2e (a broad "kill all node" would end the other team's run); the dispatcher itself.

## Goals / Non-Goals

**Goals:** run unrelated work of different repositories at the same time; no interference between the sessions from
what the dispatcher and the hub control; the teams remove what only they control.

**Non-Goals:** no resource rules (no "one test run at a time", no machine-wide e2e lock as the idea note sketched,
no CPU/memory limits) - the owner's decision of 2026-11-10 replaces the note's "not before BL-117" and its e2e lock; no
parallelism inside one repository (git working tree, one change in progress); no change to selection order, holds,
triage, escalation or limits beyond what parallel running needs; the prediction (`plan`) stays a sequential
prediction.

## Decisions

### D1. Worker threads in one dispatcher process

The main thread keeps the loop: checks (STOP, PAUSE, until, budget, usage hold, back-off), hub scan, holds, owner
answers, selection. For each session it starts a worker thread that runs today's `run_candidate` / `resume_with_answer`
path (session, triage, `after_session`) to its end. Shared objects get one `threading.RLock` (state edits and
`state.save`, `log.write`, `out`/`problem`, goal record); `Hub` calls are already separate processes, and the hub lock
(D6) orders them. Each worker has its own `Runner` and limit-check runner (a pool keyed by session), so `kill`
reaches the right process. SIGINT is handled only in the main thread (Python delivers signals there): first press sets
`stop_after_session` (no new starts), second kills every runner.

Alternatives: *a dispatcher process per team* (shared state and lock would need inter-process locking, and the hub
selection would be split; rejected). *asyncio* (Runner and hub are blocking subprocess code; a rewrite for the same
result; rejected).

### D2. Selection of several candidates

`sel.pick` stays the rule for "next"; a new `sel.pick_free(cands, busy_repos, busy_handovers)` returns the first
candidate whose team repository and handover have no running session. The main thread calls it while
`running < parallel_sessions`. "Unrelated" needs no new rule: dependent work is already held (*Waiting for a
handover's result*), a handover has one record and one team, and one repository runs one session. Owner-answer resumes
go first as today and take a place like any session.

### D3. Whole-hub steps

Idle ask and goal check run in the product team's repository and take a place. They may start while other sessions
run when there is a free place, no candidate, and the product repository is free. Their prompt gets a "work in
progress" list (team, handover, title, phase) and the sentence to hand over only work that does not depend on it or
touch a running change. The idle ask's "not again until new hub activity" rule is unchanged. A goal verdict `complete`
/ `blocked` sets "ending": no new starts, the run ends when the workers are done. A goal run with nothing selectable,
a running session and a goal check already done for the current hub state waits (poll) instead of asking again.

### D4. State, recovery, console

`state.meta["running"]` becomes `state.meta["running"]: {session_id: {...}}`; an old single record is read as one
entry. `recover()` loops over the entries. `self._running` becomes a dict. Start lines get `(2 running)` when more
than one runs; end lines already carry team and phase and get the handover ID (today only in the goal steps). The
goal's `sessions` counter and `steps` list are updated under the lock; `--max-sessions` counts started sessions and
stops new starts at the maximum.

### D5. Isolation the dispatcher provides

- **Job object (Windows):** `Runner` starts `claude` suspended-free in a new job object with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assigned right after `Popen`; ending a session closes the job, which ends every
  process in it, also ones whose parent has exited (the `nohup` e2e run of 06:16 survived `taskkill /T` because its
  parent shell had exited). The existing `kill_pid_tree` stays as a fallback. Assigning right after `Popen` leaves a
  tiny window before the first child; acceptable (claude starts children only after start-up).
- **Temp directory:** `session_env` sets `TEMP` and `TMP` to `<run_dir>/tmp/<session_id>`; Git Bash maps `/tmp` to
  `TEMP`, so fixed names such as `/tmp/e2e.log` no longer collide. Removed after `after_session`; leftovers (crash)
  are removed at the next start for sessions not running. A resumed session keeps its directory (same session ID).
- **Prompt note** (only with `parallel_sessions > 1`): another team may work on this computer now; stop only processes
  you started (never by name, e.g. not `taskkill /IM node.exe`, not "is any playwright running"); no fixed shared
  ports or paths outside the repository and your temp directory; runs may be slower.
- **Environment:** `HARNESS_PARALLEL` = the configured number, for team scripts that want to adapt.

Alternative for temp: only the prompt note (relies on every agent; rejected as the only measure).

### D6. Hub lock in `ho`

`ho` (the `ho` tool) takes an exclusive lock file in the hub directory
(`<hub>/.ho.lock`, `msvcrt.locking` on Windows, `fcntl.flock` elsewhere) around every command that writes and around
`sync`; read commands do not lock. Waiting is bounded (e.g. 5 min) with a clear error; the lock is released by the OS
when the process dies, so a crash cannot leave it stuck. The lock file is ignored by git (`.gitignore` in the hub).

Alternative: a dispatcher-provided `ho` wrapper on the sessions' `PATH` (protects only sessions run by the
dispatcher, not the owner's own `ho` use or the dispatcher's own calls; rejected). The change to `ho` is made in its
own repository with its own commit; it is a small change to the owner's tool, not a team's work.

### D7. Teams' part: handover to the product team

What only the teams control (fixed ports of test servers and emulators, fixed temp names, stopping processes by name,
shared test-mode backends, global caches written during tests) goes to `product` as one handover from
`owner`, framed as a pipeline speed-up: find in each repository what makes two sessions on one computer interfere,
and hand the fixes to the teams as backlog items. Draft (sent after the owner confirms the text, before the first
parallel run):

> Title: Pipeline speed-up: sessions of different teams run in parallel — make each team's tooling independent
>
> The dispatcher will run sessions of different repositories at the same time (first `app` and `backend`).
> Please have each team check what in its tooling breaks when another team's session runs on the same computer at
> the same time, and plan the fixes as backlog items: fixed ports (test servers, LLM emulator, test-mode backend,
> debugging ports), fixed file names outside the repository, stopping or detecting processes by name, shared
> browser profiles or caches written during tests, and Docker: both the backend's stack and the extension's e2e
> backend clone use the compose project name `backend`, so one team's `docker compose down` may hit the other's
> containers - each needs its own project name (`-p`). The dispatcher already gives each session its own `TEMP`, ends all
> of a session's processes with it and serialises `ho`. No rule against parallel test runs is wanted; slower runs
> are accepted. Expected: done (the items are in the teams' backlogs, with any found conflicts).

## Risks / Trade-offs

- [A shared resource neither D5 nor the teams found (e.g. a port) makes a test fail only in parallel] → it shows as an
  e2e or infra failure (now marked `infra` in both repositories); the stable-tests rule sends it to the backlog; the
  owner can set `parallel_sessions = 1` at once.
- [Slower sessions hit the inactivity or maximum limits more often] → limits count awake time and limit checks extend
  progressing sessions; watched in the first parallel runs, not changed in advance (owner).
- [Usage windows drain twice as fast] → the usage hold already stops new starts at the threshold; running sessions may
  overshoot by one session each.
- [Thread-safety bugs in the dispatcher] → one lock around all shared writes; tests with two fake runners that end in
  both orders; `parallel_sessions = 1` keeps today's path.
- [Job object breaks something claude needs (e.g. a process that must outlive a session)] → nothing should outlive a
  session by design; if a team relies on it, it shows at once and is a team fix.

## Migration Plan

Default `parallel_sessions = 1` keeps today's behaviour; `harness.toml` sets 2 after the tasks pass. The hub lock is
compatible with older `ho` (an old `ho` simply does not lock). Rollback: set `parallel_sessions = 1`.

## Open Questions

- Whether `parallel_sessions` should later be 3 (product sessions next to both technical ones) - decided by the first
  parallel runs, without changing this design.
