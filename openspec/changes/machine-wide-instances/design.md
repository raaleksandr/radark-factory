# Design: machine-wide layer for several dispatcher instances

Handover HO-20261114-cda3 (RB-001). Builds on `parallel-sessions` (archived 2026-11-14), which made one dispatcher
run several sessions with worker threads, one `BigLock`, per-session job objects and the `ho` hub lock, and left
several instances out (its Non-Goals and D9).

## Context

Per instance today (`radark/__main__.py`): the run lock `Lock` (`<run_dir>/lock`, PID file, stale when the PID is not
running); usage readings in `state.meta["usage"]` (`record_usage` after a session, `on_usage` from the stream thread
only announces a crossing), the threshold hold `usage_hold` → `held_windows`, the budget `budget_reached`, the
back-off after `usage_limit` (`exhausted_window`, `usage_wait` meta); the session count `len(self.workers)` against
`parallel_sessions`; `awake.Keeper`, a thread calling `SetThreadExecutionState`. Nothing is shared between two
instances, and nothing prevents two configurations from listing the same repository.

## Goals / Non-Goals

**Goals:** several instances (different `harness.toml` and run directories, possibly different hubs and `ho`
installs) on one PC of one OS user, sharing one Claude account's usage, a cap on concurrent sessions and full test
runs, safe keep-awake, one instance per repository, nothing blocking after a crash, visible in `status`; a single
instance with today's configuration behaves as today (apart from the shared usage record and the locks).

**Non-Goals:** no coordination across OS users or computers; no scheduling fairness between instances (first come,
first served on a free slot); no CPU / memory measuring; no change to `ho`; nothing about the hub (instances may use
different hubs); `plan` stays a sequential per-instance prediction.

## Decisions

### D1. Machine directory

`RADARK_MACHINE_DIR` when set; otherwise `%LOCALAPPDATA%\radark\machine` on Windows (per user, not roaming: locks
and PIDs are per machine) and `${XDG_STATE_HOME:-~/.local/state}/radark/machine` elsewhere. Created on first use.
`run`, `once` and `dry-run` refuse (exit 2) a directory that cannot be created / written or that lies inside the run
directory or a team repository (resolved paths). The environment variable is the override for tests, the sandbox
(`make_sandbox.py` writes it into the sandbox's start script / README line) and an owner who wants two pipelines
deliberately separated (for example two Claude accounts — then they share nothing).

Layout (all under the machine directory):

| path | holder | content |
|---|---|---|
| `machine.toml` | owner | limits (D2) |
| `usage.json`, `usage.lock` | any instance, briefly | shared readings and hold (D3) |
| `instances/<id>.lock`, `<id>.json` | the instance for its whole run | config path, run dir, PID, process start, started, sessions running |
| `repos/<key>.lock`, `<key>.json` | the instance owning the repository | repository path, config path, instance id |
| `slots/session-<n>.lock`, `.json` | the instance for one session / step | instance id, kind (`session` / `step`) |
| `slots/test-<n>.lock`, `.json` | the `test-slot` process for one command | PID, instance id from the environment when set |

`<id>` = `<pid>-<process start in ms>`; `<key>` = SHA-256 (first 16 hex) of `os.path.normcase(os.path.realpath(repo))`
(normcase lowercases and unifies separators on Windows). Slot numbers run 1..limit.

### D2. Machine limits in `machine.toml`

One file in the machine directory rather than `[machine]` in every `harness.toml`: one copy cannot drift between
instances, and an instance needs no rule for conflicting values. `[machine] sessions = 2`, `test_runs = 1`
(defaults, product decision). Read with `tomllib` at start (invalid → exit 2 naming file and key; `bool` is not an
integer) and again at each slot request (cheap); an invalid value read later keeps the last valid limits, with one
`!` line and a `machine_config_invalid` log event. A lowered limit takes no slot away; slots above the limit are not
handed out. `machine.toml.example` in the repository root documents it; no file means defaults.

### D3. Shared usage record

`usage.json`: `{"windows": {"five_hour": {utilization, resets_at, status, seen_ts}, ...}, "hold": {"until", "window",
"cause", "by"} | null}`. Reads and writes take `usage.lock` (OS lock, blocking with a 10 s bound; on timeout the
instance uses its own reading and logs `machine_usage_unavailable` once — never fails a run) and replace the file
atomically (`write_json_atomic`).

- **Write:** `on_usage` (stream thread, under `BigLock` as today) also merges the reading into `usage.json` when it
  differs from the last one written by this session (utilization, status or reset changed), so another instance
  sees it during the session, not only after it. `record_usage` still writes `state.meta["usage"]` as today.
- **Read:** one helper `effective_usage()` = per window the reading with the newest `seen_ts` from
  `state.meta["usage"]` and `usage.json`; `usage_hold`, `budget_reached`, `exhausted_window`, `start_budget`,
  `usage_report` (dry-run), the goal-limit check and `status` use it instead of `state.meta.get("usage")`.
- **Hold after a hit:** where `usage_limit` sets the wait today (reset known → reset + `USAGE_MARGIN_S`; unknown →
  back-off), the instance also writes `hold = {until, window, cause: "limit_hit", by: <instance id>}` when `until`
  is later than the stored one. Before every new step each instance waits for `max(own wait, shared hold.until)`;
  the existing `usage_wait` meta / lines are reused, with `(hit in another pipeline)` when `by` is another instance.
  An instance's own exponential back-off stays per instance; another instance's hold is waited out without doubling
  anything locally.
- Budgets stay per run (`self.budget`), measured against `effective_usage()`.

### D4. OS locks and crash safety

One small class `FileLock(path)` in `radark/machine.py`: opens the file, `try_acquire()` locks byte 0 without
waiting (`msvcrt.locking(fd, LK_NBLCK, 1)` on Windows, `fcntl.flock(LOCK_EX | LOCK_NB)` elsewhere), `release()`
unlocks and closes. The OS releases it when the process ends, also when it is killed (job object, Task Manager,
crash). Distinct files per claim, so two threads of one instance never contend for the same file handle. Records
(`*.json`) are written after the lock is taken and removed before it is released; a record whose lock can be taken
is stale: ignored, and removed by whoever took the lock. PID and process start time (`process_started`) are kept for
display only; liveness is decided by the lock alone, which is immune to PID reuse. The run lock (`<run_dir>/lock`)
stays as it is (same run directory twice), it is not part of the machine layer.

### D5. Start order of `run` / `once`

config → `ho` check (RB-003) → machine directory and `machine.toml` (D1, D2) → run lock → instance record → claim
every team repository (D6) → start lines (D9) → loop. Any refusal after the run lock releases what was taken and
exits 2. `dry-run` and `status` take neither the run lock nor claims; they read records and probe locks (take and at
once release), which shows conflicts without holding anything.

### D6. One repository, one instance

`run` / `once` take `repos/<key>.lock` for each configured team repository (two teams of one configuration sharing a
repository → one key, no conflict). A lock held by another live instance → read its record → message:

`Repository <path> is in use by another running pipeline (<config path>, PID <pid>); not starting. Remove it from
one of the configurations or stop that pipeline.` — exit 2.

`dry-run` prints `! repository <path> is in use by another running pipeline (<config path>); run would refuse` and
otherwise its usual output (exit code as today). Claims are held for the whole run and released at exit (and by the
OS on a crash).

### D7. Machine session slot

`Machine.try_session_slot(kind)` takes the first free `slots/session-<n>.lock`, n ≤ `sessions`, or returns None.
Where the loop is about to start a step — sequential loop (`parallel_sessions = 1`) before `run_candidate`,
`resume_with_answer`, idle ask, goal check; parallel loop before starting a worker — the instance takes a slot first
(the handover's "machine slot before the instance's own slot"); the slot is passed to the worker / step and released
in its `finally` after the step has been processed (triage and `after_session` included, so a consultation never
needs one). Limit checks and triage consultations take none, as for `parallel_sessions`. Wrap-up (RB-015) happens
inside the session that already holds a slot.

No slot → the step is not started; one console line when the waiting starts or its numbers change:
`machine limit: <k> sessions running in other pipelines` (or `... (<own> in this pipeline, <other> in other
pipelines)` when this instance holds some), a `machine_wait` event (`limit`, `own`, `other`), then a nap of
`min(poll, 30 s)` through the existing wait path (STOP, PAUSE, `--until`, Ctrl+C, sleep watch keep working), and the
loop runs again from its checks (the candidate may have changed). When a slot is taken after a wait:
`machine slot free - starting` and `machine_wait_end`. The wait counts like other waits: toward `--until` and
`max_hours`, never toward `empty_continues`, `no_progress` or the idle streak; `once` waits as well (it must not fail
or loop). With one instance alone and `parallel_sessions ≤ sessions` the slot is always free, so nothing changes.

Whole-hub steps (RB-005 idle ask, goal check) take a slot like work sessions: they are Claude sessions that use the
machine and the account the same way. RB-015 wrap-up, RB-014 triage, RB-003 `ho` check: per instance, unchanged.
The "work in progress" section of idle ask / goal check prompts does **not** mention other pipelines: they usually
have another hub, and their sessions are not this hub's work; saying "another pipeline is running" would add text
without a decision it changes (the handover allows but does not require it).

The instance record's `sessions` count is updated when a slot is taken / released (for `status`).

### D8. Test-run slot: a wrapper command

Choice: an explicit wrapper, `python -m radark test-slot [--] <command...>`, rather than detecting test commands.
Detecting (a hook matching command lines, or a per-team `test_commands` pattern in `harness.toml` with a hook that
rewrites the Bash command) would spare teams one word, but it guesses what a "full test run" is, breaks on scripts
that call the suite indirectly, and needs hook input rewriting; the wrapper is visible in the transcript, works the
same in any shell and outside a pipeline, and the team decides what is heavy.

- Waits for the first free `slots/test-<n>.lock`, n ≤ `test_runs` (re-read each poll); prints
  `radark-test-slot: waiting - <k> test run(s) in progress on this computer` at once and every 60 s to stderr; polls
  every 2 s. Then runs the command (`subprocess.run`, no shell, inherited stdio, environment plus
  `HARNESS_TEST_SLOT_HELD=1`), releases the slot, exits with the command's code (or 127 when it cannot start).
- `HARNESS_TEST_SLOT_HELD` set → runs the command at once (a suite that calls the wrapper again does not deadlock).
- Sessions get `RADARK_MACHINE_DIR` (the resolved directory, so `test-slot` uses the instance's one),
  `HARNESS_TEST_SLOT` (wrapper path) and `<run_dir>/bin` in front of `PATH`. The dispatcher writes
  `<run_dir>/bin/radark-test-slot.cmd` (`@"<sys.executable>" -m radark test-slot %*`) and a POSIX
  `radark-test-slot` script at start, only when the content changed. `sys.executable` is the installed
  dispatcher's Python, so the installed release runs, never a working tree.
- A killed session kills the wrapper (job object, parallel-sessions D5) and the OS frees the slot.
- Prompt note (`prompts.TEST_SLOT_NOTE`), added to work prompts when `parallel_sessions > 1` or another instance is
  running at session start (D7 of the spec), so a lone instance's prompts stay as today:

> Several sessions may run on this computer now. Run a full test suite as `radark-test-slot <command>` (for example
> `radark-test-slot python -m pytest`); it waits while another session's full test run is in progress, then runs your
> command and returns its exit code. Single quick tests do not need it.

- The team `CLAUDE.md` guidance in `radark/README.md` gets the same rule, so teams can make it standing practice.
- Risk: the wait counts toward the agent's Bash tool timeout; the waiting lines show why, and agents already run long
  suites in the background. Accepted.

### D9. Visibility

- `status` (new, read-only, `--config` optional: without a readable configuration it skips the conflict part): machine
  directory; limits (or the `machine.toml` error, exit 2 at the end); other running instances (config path, PID,
  started, sessions running) — stale records are removed; slots in use (sessions `k/limit`, test runs `k/limit`);
  shared usage per window (used share, reset, `seen`), and the shared hold if any; this configuration's repository
  conflicts. Exit 0 otherwise.
- Start lines of `run` / `once`: `Machine: <dir> - limits 2 sessions, 1 test run` and per other instance
  `Other pipeline running: <config path> (<n> sessions running)`.
- `dry-run`: the same lines, repository conflicts (D6), and `Machine slot: free` / `Machine slot: none free (<k>
  running in other pipelines) - would wait`.
- Another instance's details are limited to configuration path, PID, start time and session count (no handovers,
  teams or titles).

### D10. Keep-awake with several instances

No new machinery. `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` is a per-thread request; the Windows
power manager keeps the system awake while any thread of any process has such a request (`powercfg /requests` lists
them per process), and a request ends when its thread clears it or ends. So `pipeline-a` ending or leaving its range
clears only its own keeper thread's request. The sleep watch (awake-clock gaps) and wake grace are per instance and
only observe; they stay correct. Verified in apply with a two-process check on Windows (task 5.2), recorded in the
README.

### D11. Integration

- RB-008 `parallel-sessions`: machine slot before the instance's own place (D7); `parallel_sessions` unchanged; the
  hub-lock requirement is per instance's `ho`.
- RB-015 wrap-up, RB-014 triage / team-decision notices, RB-005 idle ask / goal check, RB-003 `ho` check: per
  instance, unchanged; whole-hub steps take a machine slot (D7).
- Different hubs / `ho` installs: the machine layer stores no hub path and calls no `ho`.

## Risks / Trade-offs

- [`msvcrt.locking` on a network or synced directory may not behave] → the default is local app data; an override is
  the owner's choice; documented.
- [Shared usage record unavailable (lock timeout, disk)] → the instance falls back to its own reading, logged once;
  never fails a run.
- [Two instances wait for each other's slots forever] → impossible: a slot is held only while a session runs; waits
  have no cycles (a session never waits for a session slot).
- [Test-slot wait hits the Bash tool timeout] → visible lines, background runs; accepted (D8).
- [Starvation: one instance always grabs a freed slot first] → polling at ≤ 30 s by all; acceptable for two or three
  pipelines; fairness is a Non-Goal.
- [The machine directory grows] → records are removed on release and stale ones on sight; locks are tiny files.

## Migration Plan

Nothing to migrate. On first start the machine directory is created; without `machine.toml` defaults apply. An
instance alone with `parallel_sessions = 1` never waits. Rollback: install the previous release; the machine
directory is ignored by it and may be deleted.

## Open Questions

None blocking. Whether `sessions` should default to 3 later is decided by the first two-pipeline runs.

## Assumptions (unattended propose session)

- One change, not split: the test slot is a small command on the same lock primitive, and `status` reads the same
  records; tasks are ordered so the handover's suggested first part (shared usage, session limit, repository
  ownership) lands first (sections 1–4) and the test-run limit and visibility second (5–6). If apply finds the
  change too big, it stops after section 4, records the rest under "Apply results" and reports the split in
  `ho done`.
- `status` is a new command (the dispatcher had none); it is per configuration only for the conflict part.
- Machine limits live in `machine.toml` (cannot drift), not in `harness.toml`.
- Instances of one OS user share one Claude account; an owner with two accounts separates them with
  `RADARK_MACHINE_DIR`.
- `once` waits for a machine slot instead of exiting (the handover: an instance at the limit waits, does not fail).
- The idle ask / goal check prompts do not mention other pipelines (D7).
