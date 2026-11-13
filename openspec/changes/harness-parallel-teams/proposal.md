# Proposal

## Why

The dispatcher runs one Claude Code session at a time across all teams. In the run of 2026-11-10 the backend's work
(HO-20261110-yeti, 16 min) waited behind app's, and every long apply (40–97 min, mostly a full e2e run) kept
every other team idle. The owner's decision (2026-11-10): sessions of different repositories for unrelated work may
run at the same time, for now the app (`app`) and the backend (`backend`). Performance is watched, not treated
as a blocker in advance (the owner has rendered a film next to the pipeline without trouble), and no extra rules such
as "no two test runs at once" are wanted. What is needed is that parallel sessions do not interfere and stay
independent of each other.

## What Changes

- **Parallel sessions:** the dispatcher may run up to `[loop] parallel_sessions` work sessions at once (default 1, the
  current behaviour; the project's `harness.toml` sets 2), at most one per repository and at most one per handover.
  A candidate for a repository that already has a running session waits; items held while they wait for another
  team's result stay held as today, so dependent work never runs in parallel.
- **Run control with several sessions:** `PAUSE`, `STOP`, `--until`, the usage budget, the usage hold and a usage-limit
  back-off stop *new* sessions; running ones finish. Ctrl+C: first press finishes all running sessions, second ends
  all of them. A goal run ends only after its running sessions are processed.
- **Whole-hub steps:** the idle ask and the goal check may run while other sessions run; their prompt names the work
  in progress and asks only for work that does not touch it.
- **Console and state:** start and end lines of interleaved sessions always carry the team and the handover; the
  state keeps a record per running session, and recovery after a crash handles each of them.
- **Isolation provided by the dispatcher:** each session gets its own temporary directory (`TEMP`/`TMP`), every
  process a session starts ends with the session (also background ones, which today can outlive it, as the orphaned
  e2e run of 06:16 did), and the session prompt says another team may be working on the same computer at the same
  time (do not stop processes you did not start, no fixed shared paths or ports).
- **Hub safe for parallel use:** `ho` takes a hub lock for commands that write and for `sync`, so two agents (or an
  agent and the dispatcher) cannot run `git pull --rebase`/commit/push in the hub working copy at the same time.
- **Teams make their own tooling independent:** a handover from the owner to the product team (`product`)
  asks it to have the teams find and remove what makes two sessions on one computer interfere (fixed ports, fixed
  temp file names, stopping processes by name, shared test servers), framed as a pipeline speed-up.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "One Claude Code session at a time" becomes "Claude Code sessions per repository"; new
  requirements for the number of parallel sessions, run control, whole-hub steps, the console, recovery, session
  isolation and parallel hub use.
- `orchestration-harness`: "One agent at a time" becomes "One agent per repository at a time".

## Impact

- `harness/__main__.py` (loop: start up to N sessions, one worker thread per session, shared state/log/console under a
  lock, per-session runner, signal handling in the main thread, idle ask and goal check with running work), `harness/
  runner.py` (session in a Windows job object, per-session temp directory), `harness/select.py` (pick several
  candidates: one per repository and handover), `harness/state.py` (running records per session), `harness/
  config.py` (`parallel_sessions`), `harness/prompts.py` (parallel note; idle ask and goal check name running work),
  `harness/forecast.py` / `dry-run` (show what would start in parallel), tests, `harness/README.md`, `harness.toml`.
- `ho.py` (the `ho` tool, owner's repository): hub lock.
- Hub: one handover from `owner` to `product`.
- With `parallel_sessions = 1` the behaviour is as today.
