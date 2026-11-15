# Design: cockpit, part 3 — current state of running pipelines (Now tab)

Handover HO-20261115-xspc (RB-023). The product decisions of the handover (2026-11-15) are taken as given; the
decisions below fill in what it leaves open. Assumptions taken without asking (the session runs unattended) are
marked **Assumption**.

## Context

- Parts 1 and 2 (`radark/cockpit.py`, `radark/cockpit_history.py`, `radark/cockpit_page.html`) give: the server
  with its request checks; `Cockpit._load()` (each shown pipeline: entry, hub group, run directory); the History
  `LogCache` (tolerant `runs.jsonl` parsing, cached by size + `st_mtime_ns`); `build_sessions()` (FIFO pairing,
  open sessions closed as `interrupted` by a later `dispatcher_start`, sessions still open at the end of the log
  marked `running`); `Cockpit._list_all(group)` (`ho list --status all --json` once per hub); and a page whose third
  tab is a disabled placeholder.
- The machine layer (`radark/machine.py`, change `machine-wide-instances`): each dispatcher instance holds an OS lock
  on `instances/<pid>-<ms>.lock` and writes `instances/<pid>-<ms>.json` = `{id, config, run_dir, pid, started,
  sessions}`; `config` and `run_dir` are the paths the dispatcher was started with, `started` is **local time
  without a zone** (`local_now()`), `sessions` the number of session slots it holds. Session slots are
  `slots/session-<n>.lock` (+ `.json`), the limit is `[limits] sessions` in `machine.toml` (`load_limits`).
  `machine.probe(lock)` takes the lock for an instant and, when it is free, **deletes** the record (and with
  `remove_lock` the lock file): that is the dispatcher's cleanup and must not run from the cockpit.
- The run directory's `goal.json` (`GoalRun.to_json`): `path`, `started` (UTC `…Z`), `status` (`running` while the
  goal run lasts, then `complete` / `stopped` / `blocked` / `stalled` / `limit`), `ended`, `pid` (the dispatcher's).
- Run-log records relevant here: `dispatcher_start` (`pid`, `goal`), `session_start` / `session_end` /
  `interrupted`, `stop` (written when a `STOP` file ends the run), `goal_result`.

## Goals / Non-Goals

**Goals:** a read-only Now tab and `GET /api/now`, cheap on a 10 s refresh, correct with stale records, partial
logs and two pipelines, testable without a browser, standard library only.

**Non-Goals:** starting, stopping or pausing a pipeline from the cockpit; cleaning stale records; reading session
stream files or `state.json`; per-session cost or token figures; any change to what the dispatcher writes.

## Decisions

### N1. Module layout

New module `radark/cockpit_now.py`: the read-only instance scan, the goal record read and pure functions that build
the cards from (pipeline, live instances, log records, goal record, hub items, now). `radark/cockpit.py` adds
`Cockpit.now(now=None)` (gathers the inputs with `_load()`, the shared `LogCache` and `_list_all`) and the route.
Rationale as in part 2: the rules are the bulk of the tests and test best as pure functions.

### N2. Liveness without changing files

A new helper `machine.probe_readonly(lock_path) -> bool | None` next to `probe` (which keeps its behaviour):

- the lock file does not exist → `False`;
- open it **without `O_CREAT`** (`os.open(path, os.O_RDWR)`); an error opening it → `None` (unknown);
- try the non-blocking OS lock on byte 0 (`_os_lock`); it fails → `True` (another process holds it: live);
- it succeeds → release and close at once → `False` (stale). **Nothing is unlinked or written** in either case.

**Assumption** — lock probe rather than PID check: the PID in a record can be reused by an unrelated process after
a crash, and the standard library has no portable "is this PID alive" (on Windows `os.kill(pid, 0)` would *terminate*
the process). The probe holds the instance lock for an instant only; instance lock names are unique per instance and
only their owner takes them, so no dispatcher claim can collide with it. One side effect is accepted and recorded:
on Windows, if a dispatcher exits during that instant, its `close()` cannot unlink the lock file (it is open), and
the stale lock file is left for the next dispatcher's own probe to remove — that is the normal stale-record path.

Slots are **not** lock-probed (a probe there could make a dispatcher see a slot busy for an instant and wait):
slots in use = the sum of `sessions` of the live instance records (N7).

Instance scan (`live_instances(machine_dir)`): for every `instances/*.lock`, `probe_readonly`; live → read the
`.json` record (`machine.read_record`, read only; missing or unreadable record → `{id: <stem>}` with no config);
`None` → kept as `{id, unknown: true}`; stale → ignored. Records without a lock file are ignored. No directory is
created when `instances/` does not exist.

### N3. Matching instances to pipelines

A live instance belongs to a shown pipeline when `machine.norm(record.config)` equals the pipeline's normalized
configuration path, or else `machine.norm(record.run_dir)` equals its normalized run directory. **Assumption** —
config first, run directory second (both are absolute paths written by the dispatcher; a config moved but pointing
at the same run directory still matches). Several matching live instances → all are listed on the card (state
`running`, `instances` list with start and PID each, oldest first), no error. Live instances that match no shown
pipeline (or are `unknown`) are counted as "other instances" on the machine line.

`started` of an instance is local time without a zone: it is parsed as local time (`datetime.fromisoformat` then
`.astimezone()`) and sent as UTC like every other time. A missing or bad `started` → `null`.

### N4. Card state

| condition | state |
|---|---|
| configuration missing or invalid (part 1's `missing` / `error`) | `unknown` (message from part 1) |
| `runs.jsonl` cannot be read (`LogCache` → `error`), or the run directory exists but cannot be listed | `unknown` |
| a matching live instance | `running` |
| otherwise (no record, or only stale records) | `not running` |

A missing `runs.jsonl` is **not** unknown: the card says "no run log yet". **Assumption** — `unknown` wins over a
live instance (the handover defines `unknown` as "the run directory cannot be read"); the card still lists the live
instance's PID and start so the owner sees why. An instance whose probe gave `None` makes no card `unknown`
(it cannot be matched without its record); it counts on the machine line as unknown.

### N5. Goal run or regular run

`goal.json` in the run directory is read (read only, `machine.read_record`). The card shows **goal run** with the goal
file's **name only** (`Path(path).name`, never the full path) and `started`, when: the card is `running`, the
record's `status` is `running`, and the record's `pid` (when present) equals the PID of one of the card's live
instances. Otherwise **regular run**. **Assumption** — the PID match guards against a `goal.json` left `running` by
a dispatcher that was killed: a new regular run of the same pipeline would otherwise show the old goal. For a card
that is not running, the last goal record is shown as a fact ("last goal run: <name>, <status>, ended <time>") when
present.

### N6. Sessions running now, last event, last run facts

`build_sessions(log.records)` from part 2 is reused unchanged; the sessions with `running` true are exactly those
with a `session_start` and no end after the latest `dispatcher_start`.

- Card `running`: they are listed as **running** with team, handover ID, title, phase, start and elapsed seconds
  (`now − start`, the page formats it). Sessions without a handover (idle ask, goal check) are listed with ID
  "—" and their phase/kind as recorded.
- Card `not running`: the same sessions are listed as **interrupted** (no elapsed time, the start only).
- Card `unknown`: none (the log is not readable, or not trusted when the configuration is broken).

Title: from the hub's `ho list --status all` items (`_list_all`, part 2); not listed or hub failed → `unknown`
(a hub error is shown as a small note on the card). **Assumption** — on the Now tab the hub list is reused for up
to **30 s** per hub (a small cache in `Cockpit`, keyed by normalized hub path, guarded by a lock), so the 10 s
refresh calls `ho list` at most once per hub per 30 s; titles change rarely. History keeps calling it per request.

Last event: the last record of the log in file order (`time`, `event`). Last session: the ended session with the
latest end (end, outcome as History shows it). Last `dispatcher_start`: its time. Last stop: the latest `stop`
record **after** the last `dispatcher_start`, else none. **Assumption** — the dispatcher writes `stop` only for a
`STOP` file; an end by Ctrl+C, a crash or `--once` writes no stop record, so the card says "stop: not recorded"
rather than guessing. These facts are sent for every card; the page shows last session / start / stop on cards
that are not running and the last event on all cards.

### N7. Machine line

`load_limits(machine_dir)`; an invalid `machine.toml` → defaults and a note "machine.toml invalid, defaults shown"
(as `status` does). In use = sum of `sessions` (integer ≥ 0, else 0) over all live instance records. Line: "Session
slots 2 / 3 · 2 pipelines running · 1 other instance". **Assumption** — counting from instance records instead of
probing `slots/` (N2); a record is rewritten by its dispatcher at every slot change, so it is current.

### N8. API

`GET /api/now` → `200`:

```json
{"now": "<UTC ISO>",
 "machine": {"slots_used": 2, "slots_limit": 3, "running": 2, "other_instances": 0, "unknown_instances": 0,
             "note": null},
 "pipelines": [{"name": "alpha", "state": "running", "message": null, "log": "ok|missing|error",
   "instances": [{"pid": 4242, "started": "<UTC ISO|null>", "sessions": 1}],
   "goal": {"name": "goal.md", "started": "<UTC ISO>"} ,
   "last_goal": null,
   "running": [{"team": "app", "handover": "HO-…", "title": "…", "phase": "apply", "start": "<UTC ISO>",
                "elapsed_s": 1260, "state": "running"}],
   "last_event": {"time": "<UTC ISO>", "event": "session_start"},
   "last_session": {"end": "<UTC ISO>", "outcome": "finished", "team": "app", "handover": "HO-…"},
   "last_start": "<UTC ISO|null>", "last_stop": "<UTC ISO|null>", "hub_error": null}]}
```

`goal` is `null` for a regular run. Same Host check and response headers as every other route; no run-directory,
hub, goal-file or instance-record path is sent (part 1 already sends the configuration path in `/api/items`; Now
does not repeat it). Prompts and result texts from the log are never sent. Cards are in the order of part 1's
pipeline list.

### N9. The page

The third tab button becomes **Now** (enabled). It shows the machine line, then one card per pipeline: name and a
state badge (running green, not running grey, unknown muted/orange), instance(s) "since <local time> · PID n",
"Goal run: <name> since <time>" or "Regular run", a small table of running (or interrupted) sessions (Team, ID,
Title, Phase, Since, For), the last event line, and for not-running cards the last session / start / stop. Times
with `toLocaleString`; durations `H h MM min` (part 2's formatter, under an hour `MM min`, under a minute
`< 1 min`). Text via `textContent` only. The tab is fetched when shown and every **10 s while active**
(`NOW_REFRESH_MS = 10000`); other tabs keep their 30 s refresh; "Refresh" refreshes the active tab.

### N10. Tests

- `radark/tests/test_cockpit_now.py`, on a temp `RADARK_MACHINE_DIR`, invented records (IDs `HO-20990101-…`, teams
  `product`, `app`, pipelines `alpha` / `beta`):
  - `probe_readonly`: held lock (held by a helper subprocess, as the machine tests do) → `True`; free lock → `False`
    and the lock file **and** its record still exist; no lock file → `False` and nothing created.
  - running vs. not running: live instance (subprocess holding the lock) vs. stale record (lock file not held) vs.
    no record; two live instances for one pipeline → both listed; a live instance of an unshown config → other
    instances; match by run directory when the config path differs.
  - goal vs. regular: `goal.json` running with matching PID → goal run (file name only); status `complete` → regular;
    running but PID of no live instance → regular; not running → `last_goal`.
  - sessions: running only after the latest `dispatcher_start` and only with a live instance; the same log with no
    live instance → interrupted; unknown title; hub failure → `unknown` titles and `hub_error`.
  - unreadable run log (`LogCache` stubbed to `error`, or a directory named `runs.jsonl`) → `unknown`; missing log →
    not unknown; broken configuration → `unknown`.
  - last event / last session / last start / last stop (stop before the last start not shown); instance `started`
    as local time converted to UTC.
  - machine line: slots used from records, limit from `machine.toml`, invalid `machine.toml` → defaults + note.
  - **read only**: a snapshot of every file (path, size, mtime) in the machine directory and run directories before
    and after `/api/now` (with live, stale and orphan records present) is identical.
- Server: `GET /api/now` through the part-1 harness (fake `ho`): 200 shape, 403 on a foreign Host, no write `ho`
  call, two pipelines on one hub → one `list` call, a second request within 30 s → no new `list` call.
- End-to-end with the installed `ho` (like `test_cockpit_history_ho.py`): `ho init --teams
  product=Product,app=App,owner=Owner` in `tmp_path`, an invented handover, two configurations `alpha` / `beta`,
  invented `runs.jsonl` and instance records, one live instance held by a subprocess; check titles, running and
  not-running cards through `/api/now`. Fails with a clear message when `ho` is not on `PATH` (no skip).
- The page: the Now tab button is enabled, no placeholder text remains, no external resource reference, the Now
  render code uses no `innerHTML`.

## Risks / Trade-offs

- [The read-only probe holds an instance lock for an instant] → only the owner ever takes its own instance lock;
  the one effect (an unlink skipped on Windows at the owner's exit) is the normal stale path (N2).
- [Slot count from records lags a crash] → a crashed instance's record is stale and not live, so its slots are not
  counted; a live instance rewrites its record on every slot change.
- [A killed dispatcher leaves `goal.json` `running`] → the PID match (N5) shows a regular run.
- [`stop` is not written for every kind of end] → the card says "not recorded" (N6).
- [10 s refresh cost] → log cache by size + mtime; hub list reused for 30 s; the instance scan is a few file opens.

## Migration

None. Old instance records without `sessions` or `started` are shown as far as they go; no configuration or `ho`
change.
