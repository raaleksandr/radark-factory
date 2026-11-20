# Design: wrap up on demand (HO-20261120-z32m)

## Context

See proposal.md (Why). Existing pieces this builds on:

- `STOP` / `PAUSE` files in the run directory, checked by `Dispatcher.ending()` / `end_run()` and the one-session
  loop between sessions; waits end early for them.
- The strict end time (`strict-end-time`): `Runner.run(end_at=, on_end_at=)` stops a session (process tree and job
  object) with cause `end_time`; `Dispatcher.end_time_wrap_up()` resumes it with
  `prompts.end_time_wrap_up_message()`, limited to `wrap_up_minutes`; the outcome rule keeps a completed phase and
  otherwise makes the step `interrupted` / `end_time`; the next run resumes it with `INTERRUPT_LABELS["end_time"]`.
- Hooks are installed into every session through `--settings` (`session-settings.json`): `SessionStart`,
  `PreToolUse` (questions, guard), `Stop` (nudge once), `StopFailure`. Hooks write markers
  (`<run_dir>/markers/...` per session run ID, `hookcommon.write_marker` / `read_markers`) that the dispatcher reads.
- The fake `claude` (`radark/tests/fakes/fake_claude.py`) runs the real hooks from the settings file, so hooks and
  dispatcher are tested together.

## Goals / Non-Goals

**Goals:** a request at any moment; the running command (also a background one the session waits for) is never
killed by the request itself; the session does its own wrap-up in its own context, with a bounded time; reuse of the
end-time wrap-up text, outcome and resume.

**Non-Goals:** changing `STOP`, `PAUSE`, `--until`, `--until-strict` or Ctrl+C; a wrap-up of one chosen session
only (every running work session of the run follows the request); a request across pipelines (one configuration per
command).

## Decisions

### D1 Request: command and file

`python -m radark [--config C] wrap-up [--within MIN]` writes `<run_dir>/WRAP_UP` as JSON
`{"requested": "<UTC ISO>", "within_minutes": MIN | null}` and prints
`Wrap-up requested at HH:MM: running sessions finish their current tool call, save their work and stop; no new step
starts.` (plus `Sessions not reached within MIN min are stopped and wrapped up.` with `--within`). The file may also
be created by hand with any content (unreadable JSON = requested at the file's modification time, no `--within`).

- Running check: the command looks for a live dispatcher of the configuration (the run lock's PID alive, as
  `Lock.acquire` checks it). None: `No run is running for this configuration; nothing to wrap up.`, exit 1, no file.
- `--within` must be a number > 0 (argparse error, exit 2).
- A request already pending (file exists): the command prints `A wrap-up was already requested at HH:MM.` and
  leaves the file as it is (exit 0). Assumption: the first request wins; to change `--within` the owner removes the
  file first (documented).
- A `WRAP_UP` file found when a run starts is left from an earlier run (the dispatcher removes it at a wrap-up's end,
  so only a crash or a hand-made file leaves one): it is removed with the console note
  `Removed a WRAP_UP file left from an earlier run.` and logged `owner_wrap_up_stale`. Assumption: a stale request
  must not end a new run unseen.

Alternative considered: only a file (no command). Rejected: the handover asks for a command and the `--within`
argument is easier to give through a command; the file stays for owners used to `PAUSE` / `STOP`.

### D2 Detection

`Dispatcher.owner_wrap_up()` returns the parsed request or None from a stat of `<run_dir>/WRAP_UP`, cached; the first
time it returns a request the dispatcher *acts* (D3). It is called:

- in `ending()` (parallel loop, a new reason `wrap-up requested`) and before each start of the one-session loop;
- in every wait where `STOP` ends the wait today (poll wait, `PAUSE` wait, usage wait, back-off): the wait ends;
- from each running session's runner loop through a new per-tick callback (D5), at most once a second.

With nothing running, a request therefore ends the run at its next check (within about a second of a wait's tick,
at most the wait's poll step).

### D3 Acting on the request

Once per run, under the dispatcher lock:

1. remember the request (`self._wrap_req`: requested time, within, seen time);
2. write `<run_dir>/wrap-up-request.json`:
   `{"run": <dispatcher run id>, "requested": ..., "sessions": {<session run id>: <wrap-up text>}}`
   for every running work session that is not a wrap-up (from `self._sessions` and the running records); the text is
   `prompts.owner_wrap_up_message(cand, grace, goal, profile)` (D7). Written atomically (temp file + replace);
3. log `owner_wrap_up_requested` with `requested`, `within_min`, `sessions` (team, handover, phase, session id) and
   print `Wrap-up requested (HH:MM): no new step starts; asking N running session(s) to wrap up after their current
   tool call: <team> <HO>, ...` (or `nothing is running; the run ends.`).

A session that starts later in the same step (a resume inside the step, e.g. a triage answer) is a resume of an item
already asked: it is not started; the step ends `interrupted` / `owner_wrap_up` (as the end-time rule does for a
question after the end time).

### D4 Delivery through hooks (between tool calls)

- New hook `radark/hooks/post_tool_use.py`, installed as `PostToolUse` without a matcher (every tool). It exits at
  once when `<run_dir>/wrap-up-request.json` does not exist (one `stat`; the cost on every tool call is the Python
  start, accepted). Otherwise, if this session run ID has no `owner_wrap_up` marker and the call is the main
  agent's (the hook input has no `agent_id`; subagent calls are skipped), it writes the marker
  `owner_wrap_up` (`source: "tool"`, `tool_name`) and prints
  `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": <text>}}` with the text listed for
  this session's run ID (`HARNESS_RUN_ID`); a run ID not listed gets nothing.
- `radark/hooks/stop.py`: with a request file present, a session without the marker is blocked once with the text as
  `reason` (marker `source: "stop"`) instead of the nudge; a session with the marker is let stop (no nudge), so the
  wrap-up ends with the session's own final message.
- Non-work sessions (triage consultation, limit check, goal check, idle ask) are not in `sessions`: the hooks do
  nothing for them; they end on their own (they are short and bounded by their own limits).

A `PostToolUse` hook runs only after the tool returned, so the running command is never interrupted; a command the
session started in the background keeps running and the text tells the session to wait for it.

Alternative considered: the dispatcher watches the stream (`tool_use` without its `tool_result`), stops the process
between two tool calls and resumes it with the prompt (the end-time path). Rejected: stopping the session ends its
job object and with it a background test run the session is waiting for (the common case of a long e2e run, as the
standing rule asks for background commands), and it costs a resume. Hooks keep the session alive.

### D5 Per-session watch and safety limits

`Runner.run` gets `on_tick(r) -> None | OWNER_STOP | OWNER_HARD`, called at most once a second in the loop. Both
answers end the session (process tree and job object, as the strict end time) with
`interrupt_cause = "owner_wrap_up"`; `OWNER_HARD` also sets `r.owner_hard = True` so `session()` resumes it with the
wrap-up prompt, `OWNER_STOP` does not. The dispatcher's `owner_watch(team, handover, work)` for a work session that
is not a wrap-up:

- detection (D2) and, after the request, the session's markers (`read_markers` for its run ID) for `owner_wrap_up`;
  on delivery: log `owner_wrap_up_delivered` (`session`, `team`, `handover`, `source`, `tool_name`, `after_s` since
  the request) and print `<team> <HO>: wrap-up request delivered after <tool> (or: at the end of its turn); wrapping
  up within G min`;
- **grace after delivery:** `delivered + wrap_up_minutes`: `OWNER_STOP` (log `owner_wrap_up_stop`, `reason: grace`).
  With `wrap_up_minutes = 0`: `OWNER_STOP` right at delivery (between tool calls, nothing runs);
- **`--within MIN`:** at `requested + MIN` a session not yet delivered: `OWNER_HARD` (log `owner_wrap_up_stop`,
  `reason: within`); the dispatcher resumes it with the same text, limited to `wrap_up_minutes` (as
  `end_time_wrap_up`, a new `owner_hard_wrap_up()` sharing its code); with `wrap_up_minutes = 0` no resume;
- **no limit check, no extension after the request:** `limit_watch`'s `on_deadline` answers at once: not delivered →
  `WRAP_UP`-like hard wrap-up with the owner text (`OWNER_HARD` path, `reason: max_time`); delivered → stop with
  cause `owner_wrap_up`. A limit check already running when the request is seen is aborted when its answer comes
  (its extension is ignored).
- `session_idle_minutes` (no stream event; a hung command is still caught by its heartbeat rule) and a session's own
  `max_time` without limit checks apply unchanged: the run cannot hang forever even without `--within`.
- Wrap-up sessions (`wrap_up=True`: time-limit, end-time or hard owner wrap-up) already have a grace period and
  their own wrap-up text: they get no second text. They run under a new run ID that the request file does not list,
  so the hooks do nothing for them. A strict end time keeps working as
  today; whichever stop comes first applies.
- Non-work sessions: with `--within`, stopped at `requested + MIN` (`OWNER_STOP`), otherwise left to end.

### D6 Outcome and resume

As the end-time rule (`end_time_wrap_up`): a work session asked to wrap up keeps its outcome when it ended normally
(not `error`) with its phase complete, or as `usage_limit` / `waiting_for_owner`; otherwise the step is
`interrupted` with cause `owner_wrap_up` (the session record too). A `question` from it is not triaged. It does not
count as an error or as no progress (`interrupted` already does neither). The next run resumes it with
`INTERRUPT_LABELS["owner_wrap_up"]`: "The owner asked the previous run to wrap up, and this session ended (it may
have wrapped up already)". The interrupted-session recovery (`running` records) is unchanged.

### D7 Text

`prompts.owner_wrap_up_message(c, grace, goal, profile)`: "The owner asked this run to wrap up now (handover X,
phase P). Do not start new work. If a command you started (also in the background, e.g. a test run) is still
running, wait for it and use its result; do not start another one. You have G min after this message; then the
session is stopped." followed by the end-time text's common part (git status, commit what works, apply: check off
and `Left for a later run`, other phases: `Left:` line, no `ho done` unless the phase is complete, the next run
resumes). The common part moves into a shared helper so both texts stay in the same words. The hard variant
(`--within`, `max_time`) adds the end-time sentence that the step was cut off (partial edit, stale
`.git/index.lock`).

### D8 Run end

After the last worker / session: log `owner_wrap_up_done` (`sessions`: team, handover, outcome, cause; `duration_s`
since the request), print `Wrap-up done: N session(s) ended (<team> <HO> <outcome>, ...); exiting.`, remove `WRAP_UP`
and `wrap-up-request.json`, exit 0; a goal run ends with `end_goal("stopped", "wrap-up requested")`. `STOP` found at
the same time wins (its message as today), the files are removed anyway. Order in `end_run`: errors, `STOP`, wrap-up,
then the rest.

### D9 Console end line, status, cockpit

- The end line's cause map gets `owner_wrap_up: "owner wrap-up"`.
- `status` prints for the configuration, when `WRAP_UP` exists: `Wrap-up requested at HH:MM (within MIN min): the
  running sessions are wrapping up; the run ends after them.` or, without a live dispatcher, `A WRAP_UP file exists
  but no run is running; the next run removes it.`
- Cockpit Now: `cockpit_now` reads the last `owner_wrap_up_requested` after the last `dispatcher_start` without a
  later `owner_wrap_up_done`; a `running` card then shows `wrap-up pending since HH:MM`; the Now API gets
  `wrap_up_pending: <ISO> | null`. This is simple with the existing run-log scan (N6), so it is in scope.

### D10 Tests without real waits

The fake `claude` gets a step `{"hook": "PostToolUse", "input": {...}, "wait_for": path}` (a long tool call: the
step waits until the test creates the file, then runs the hook) and records the hook's `additionalContext` in its
stream as a `fake_hook` line, so a test sees the delivered text. Grace and `--within` limits are checked with the
runner's injected clock / wall (`Runner.clock`, `Runner.wall`) and with `wrap_up_minutes` / `within` small enough
that the test moves the clock instead of sleeping. Where an existing test pattern uses short real times, a test may
too, under one second each.

## Risks / Trade-offs

- [The `PostToolUse` hook runs a Python process after every tool call] → it exits after one `stat` when no request
  exists; measured in apply (note in tasks) and accepted if under ~100 ms per call.
- [Claude Code may not tell subagent calls apart (no `agent_id`)] → then the text may reach a subagent first; the
  marker is per session, so the main agent would not get it from a later call; mitigation: the `Stop` hook still
  delivers at the main turn's end only when no marker exists, so apply checks the input field in the real CLI docs
  and, if missing, delivers only on calls whose `tool_name` is not inside a subagent (best effort) and records it.
- [A session ignores the request and keeps working] → the grace after delivery stops it.
- [A tool call that never returns] → `session_idle_minutes` (heartbeats excluded) or `--within` ends it, as today.
- [A request between "session started" and its first tool call] → delivered after the first tool call or at the
  turn's end; listed because `on_start` registers the session before the request file is written.

## Migration Plan

New command, file and hook only; settings files are rewritten at each run start (`write_session_settings`), so
sessions of a new run get the hook. Rollback: remove the hook entry; old runs ignore `WRAP_UP`.

## Assumptions (no owner available)

- Command name `wrap-up`, file name `WRAP_UP`, cause `owner_wrap_up`, events `owner_wrap_up_*`.
- Safety rule: idle/max stay; grace `wrap_up_minutes` after delivery; optional `--within MIN` → hard wrap-up; no
  limit check or extension after the request.
- First request wins; a stale `WRAP_UP` at start is removed with a note, not acted on.
- Non-work sessions get no text; they end on their own (or at `--within`).
- A goal run ends with `stopped`.
