# Proposal: sessions of different repositories run in parallel

Handover: **HO-20261114-wwqw** (backlog item RB-008, from `radark-product`). Based on the product team's draft
`harness-parallel-teams` (2026-11-10), updated to the current code (module `radark/`, the RB-003, RB-014, RB-015
and RB-005 changes since then); every deviation from the draft is listed in design.md ("Deviations from the draft").
The `ho` part (hub lock) is radark-handover's own change, requested with **HO-20261114-23cx**.

## Why

The dispatcher runs one Claude Code session at a time across all teams. A short task of one team waits behind
another team's long test run, and every long apply keeps every other team idle, although the work of different
repositories is often unrelated. The owner decided that sessions of different repositories for unrelated work may
run at the same time. Performance is watched, not treated as a blocker in advance, and no extra rules such as "no two
test runs at once" are wanted. What is needed is that parallel sessions do not interfere and stay independent of
each other.

Two isolation gaps also hurt with a single session: a background test run can outlive its session because its
parent shell had exited (ending a session ends only the process tree, and a detached process has left that tree),
and the hub's working copy is changed by `ho` without any lock, so an agent's `ho sync` and the dispatcher's own
hub writes can collide.

## What Changes

- **Parallel sessions:** new `[loop] parallel_sessions` (integer ≥ 1, default 1 = today's behaviour; 0 or a
  non-integer is refused at start). The dispatcher runs up to that many work sessions at once, at most one per
  repository and at most one per handover. A candidate for a busy repository waits; items held while they wait for
  another team's result stay held, so dependent work never runs in parallel. Owner-answer resumes go first as today
  and take a place like any session.
- **Run control with several sessions:** `PAUSE`, `STOP`, `--until`, the usage budget, the usage hold, a usage-limit
  back-off, `--max-sessions` and the goal run's limits stop *new* starts; running sessions finish and are processed,
  and the run ends after the last of them. Ctrl+C once finishes all running sessions; twice ends all of them
  (`interrupted`, cause owner). A goal run ends only after its running sessions are processed.
- **Per-session handling stays per session:** the limit check, the wrap-up at the last time limit (RB-015), the
  permission-denial handling and triage (RB-014), owner-decision notices and the after-session processing run in the
  session's own worker, each with its own limits and grace.
- **Whole-hub steps next to running work:** the idle ask and the goal check may run while other sessions run, when a
  place is free, no candidate can use it and the product repository is free. Their prompt names the work in
  progress and asks only for work that does not depend on it or touch a running change.
- **Console, state, recovery:** with more than one session allowed, start lines show `(N running)`; start and end
  lines always name team and handover (or step). The state keeps one running record per session (an old single
  record is read as one); recovery after a crash handles each.
- **Isolation provided by the dispatcher:** every process a session starts ends with the session, also detached
  background ones, and another session's processes are untouched (a Windows job object; a process group elsewhere).
  Each session keeps the temp directory it already has (`<run_dir>/tmp/<team>/`, unique because a repository runs
  one session at a time). With `parallel_sessions > 1`, the work prompt says another team may work on this computer
  now (stop only your own processes, no fixed shared ports or paths, slower runs), and every session gets
  `HARNESS_PARALLEL_SESSIONS` in its environment.
- **Hub safe for parallel use:** `ho` serialises hub writes and `sync` (radark-handover's change, HO-20261114-23cx).
  With `parallel_sessions > 1` the start check of `ho` (RB-003) also requires the installed `ho` to report the lock;
  otherwise the dispatcher stops at start with exit code 2.
- **dry-run** shows what would start in parallel; **plan** stays a sequential prediction.

Not in this change (product records them): the request to a pipeline's teams to remove what makes two sessions on
one computer interfere, setting `parallel_sessions = 2` in a pipeline's configuration, and the integration run with
the owner present.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: "One Claude Code session at a time" becomes "Claude Code sessions per repository"; new
  requirements for the number of parallel sessions, run control, whole-hub steps, the console, recovery, a session's
  processes, the parallel note and the hub lock requirement.
- `orchestration-harness`: "One agent at a time" becomes "One agent per repository at a time".

## Impact

- `radark/__main__.py`: the loop starts up to N sessions, one worker thread per session; shared state, run log,
  console and goal record under one lock; a runner and limit-check runner per session; signal handling in the main
  thread; idle ask and goal check next to running work; recovery of several records; dry-run parallel line.
- `radark/runner.py`: session in a job object (Windows) / process group (elsewhere), ended with the session;
  `HARNESS_PARALLEL_SESSIONS`.
- `radark/select.py`: `pick_free` (one per repository and handover). `radark/state.py`: running records per session.
- `radark/config.py`: `parallel_sessions`. `radark/prompts.py`: parallel note; work-in-progress list for the idle ask
  and the goal check. `radark/hub.py`: hub-lock signal in the `ho` start check.
- Tests in `radark/tests` (fakes: a runner that can run two sessions at once; the fake `ho` reports the lock signal).
- `radark/README.md`, `harness.toml.example`, `README.md`.
- radark-handover (its own change): the hub lock.
- With `parallel_sessions = 1` the behaviour is as today, except that a session's processes now also end when the
  session ends normally.
