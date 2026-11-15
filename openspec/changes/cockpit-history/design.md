# Design: cockpit, part 2 — history of finished work

Handover HO-20261115-u25v (RB-022). The product decisions of the handover (2026-11-15) are taken as given; the
decisions below fill in what it leaves open. Assumptions taken without asking (the session runs unattended) are
marked **Assumption**.

## Context

- Part 1 (`radark/cockpit.py`, `radark/cockpit_page.html`) has the server, the request checks (Host / Origin /
  content type, D6 of `owner-cockpit`), the pipeline list from the registry plus `--config` (`Cockpit.pipelines()`,
  which loads each configuration and groups pipelines by hub and owner team), the `ho` contract check once per `ho`
  and hub (`Cockpit._hub`), and a page with tabs where History is a disabled placeholder.
- The dispatcher writes `runs.jsonl` with `RunLog.write`: one JSON object per line, `time` in UTC
  `YYYY-MM-DDTHH:MM:SS.mmmZ`, `event`, then fields. Relevant events:
  - `dispatcher_start` (`once`, `pid`, `goal`);
  - `session_start` (`team`, `repo`, `handover`, `phase`, `prompt`, `resume`) — **no session ID**;
  - `session_end` (`team`, `handover`, `phase`, `session`, `exit_code`, `outcome`, `duration_s`, `denials`,
    `escalations`, `timed_out`, `timeout_reason`, `interrupt_cause`, ...);
  - `interrupted` (`team`, `handover`, `phase`, `session`, `cause`) for a session found running when a dispatcher
    starts again;
  - `escalation` / `escalation_sent` (`team`, `handover`, ...) when a session stops for the owner.
  Sessions without a handover have `handover` null (`idle`, goal check); consult and limit-check sessions carry the
  handover they are about.
- `ho list --status all --json` (contract 1) lists every handover of a hub with `id`, `title`, `status` (`open`,
  `resolved`, `closed`), `archived`, `to` and `recipients` (team → `pending`, `acknowledged`, `done`, `responded`,
  `declined`, `returned`). This is enough for every result kind without `ho show`.

## Goals / Non-Goals

**Goals:** a read-only History tab and `GET /api/history`, cheap on a 30 s refresh with logs of a few thousand
lines, correct with partial and old logs, testable without a browser, standard library only.

**Non-Goals:** the state of running pipelines (RB-023; only the third tab keeps its place); any change to what the
dispatcher writes; reading session stream files or the dispatcher's `state.json`; editing anything; per-session
cost or token figures.

## Decisions

### H1. Module layout

New module `radark/cockpit_history.py` with pure functions (log parsing, session pairing, rows, filters, summary,
results) and a small `LogCache`; `radark/cockpit.py` only adds the route and a `Cockpit.history(pipeline, period)`
method that gathers the inputs (pipelines, run directories, hub lists) and calls it. Rationale: the pairing and
filter rules are the bulk of the tests; pure functions test without a server. Alternative — everything in
`cockpit.py` — rejected: it is already ~500 lines.

`Cockpit.pipelines()` gains the configuration's `run_dir` in its internal data (not in the page's pipeline JSON
beyond what part 1 already sends), so the history knows where each `runs.jsonl` is.

### H2. Reading the run log

`LogCache.records(path)` stats the file; when `(st_size, st_mtime_ns)` equals the cached key it returns the cached
parsed list, otherwise it re-reads the whole file. **Assumption** — full re-read on change rather than incremental
tail reading: a few thousand lines parse in milliseconds, and full reads cannot go wrong on rotation or truncation.
The cache is keyed by `machine.norm(path)` and guarded by a lock (the server is threaded).

Parsing: read bytes, decode UTF-8 with `errors="replace"`, split lines; each non-empty line goes through
`json.loads`; a line that fails, or is not a JSON object, or has no string `time` / `event`, is skipped and counted
(`skipped` in the pipeline's history entry, shown only as a small note, never an error). A missing file → no
records, pipeline note "no run log yet". Unknown events are ignored.

### H3. Building sessions from records

Records are processed in file order (the log is append-only and written under a lock).

- `session_start` opens a session `{team, handover, phase, start}` on a per-pipeline list of open sessions.
- `session_end` closes the **oldest open session with the same `team`, `handover` and `phase`** (FIFO). Its `end`
  is the record time; `duration_s` from the record (if missing: end − start); `outcome` as recorded, shown as
  "timed out" (with `timeout_reason` when present) when `timed_out` is true; `denials` and `escalations` counts as
  recorded (missing → 0); `session` ID kept for the page. **Assumption** — FIFO by (team, handover, phase): the
  start record has no session ID, and the dispatcher never runs two sessions of the same team on the same
  handover and phase at once (parallel sessions are per team).
- A `session_end` with no matching open start (an old or cut log) becomes a session with
  `start = end − duration_s` (or start unknown when `duration_s` is missing).
- `interrupted` closes the oldest open session with the same team / handover / phase with outcome `interrupted`,
  end = the record time, duration = end − start.
- A `dispatcher_start` closes every session still open before it as `interrupted` with end unknown and duration 0
  (**Assumption** — the dispatcher that ran it is gone; counting the gap as working time would be wrong). The run
  boundary is kept for the "last run" filter.
- Sessions still open at the end of the log are **running**: no end, shown "running since <start>".
  **Assumption** — a running session adds nothing to working time or wall time until it ends; this keeps totals
  stable between refreshes.

### H4. Rows, totals, order

Sessions with a handover are grouped by (pipeline, handover). A row: pipeline name, handover ID, title (from the
hub, else the ID), teams (distinct, in first-seen order), first start (earliest known start), last end (latest
end; none while any session runs and no session has ended), working time (sum of `duration_s` of ended sessions),
wall time (last end − first start; none when either is missing), result, escalated, sessions sorted by start
(unknown start sorted by end). Sort rows by their latest activity (max of last end and running starts), newest
first; ties by ID.

Sessions without a handover are not rows; they are counted (number and summed duration) per pipeline for the
summary line.

### H5. Result from the hub

For each hub group (part 1's grouping by hub; **Assumption** — the history groups by hub path alone, since the
list is not per owner team) the server runs `ho list --status all --json` once per history request, as the
pipeline's owner team (any registered team may list), in parallel threads like part 1, after the same contract
check. The result of a row is derived from the listed item and the row's team(s):

| hub state | result |
|---|---|
| item not listed, or the hub read failed | `unknown` |
| any of the row's teams `declined`, and none answered | `declined` |
| `status` `closed` (and not declined) | `accepted` |
| any row team `returned` | `returned` |
| any row team `pending` or `acknowledged` (on `expects` `done` / `response`) | `open` |
| all row teams `done` / `responded` / `acknowledged` on `expects ack`, not closed | `in review` |

**Assumption** — the hub's recipient state `returned` is the "last return is newer than the last done" of the
handover (ho sets it on `return` and replaces it on the next `done`), so no `ho show` is needed; `ho show` is not
called at all. **Assumption** — when a row's teams differ, the first matching line of the table above wins (the
state needing attention). A row team that is not a recipient (e.g. a consult session's triage team) is ignored for
the result; if none of the row's teams is a recipient, the hub's `status` alone decides (`closed` → accepted,
else in review / open by any recipient's state).

Escalated: any `escalation` or `escalation_sent` record with that handover in the pipeline's log, or a
`session_end` with `escalations` > 0.

### H6. Periods and filters

`period` ∈ `last-run` (default), `24h`, `7d`, `all`. Window start: `last-run` → the time of the pipeline's latest
`dispatcher_start` (no such record → the whole log, **Assumption**); `24h` / `7d` → now − 24 h / 7 d; `all` → none.
Window end is now. A session overlaps when `(end or now) >= window start` and `start <= now` (unknown start →
use its end). A row is in the filter when any of its sessions overlaps; a listed row keeps **all** its sessions and
totals (**Assumption** — the row tells the whole story of the handover; the summary line counts only the sessions
that overlap the window, so it answers "what happened in this period"). `pipeline` selects one pipeline by name;
an unknown name → empty list (not an error). Sessions without a handover are counted when they overlap.

Summary: rows (handovers), overlapping sessions with a handover, their working time, rows with result `accepted`,
and "N sessions without a handover, T".

### H7. API

`GET /api/history?pipeline=<name>&period=<p>` → `200`:

```json
{"period": "last-run", "pipeline": null, "now": "<UTC ISO>",
 "pipelines": [{"name": "alpha", "state": "ok", "log": "ok|missing|error", "skipped": 0, "since": "<UTC ISO|null>", "hub_error": null}],
 "summary": {"handovers": 3, "sessions": 7, "working_s": 5400, "accepted": 1, "other_sessions": 2, "other_s": 240},
 "rows": [{"pipeline": "alpha", "id": "HO-…", "title": "…", "teams": ["app"], "first_start": "…", "last_end": "…",
           "working_s": 3900, "wall_s": 9300, "result": "accepted", "escalated": false, "running": false,
           "sessions": [{"phase": "propose", "team": "app", "start": "…", "end": "…", "duration_s": 1800,
                          "outcome": "finished", "running": false, "denials": 0, "escalations": 0, "session": "…"}]}]}
```

An invalid `period` → 400 `{"error": "unknown period", "allowed": [...]}`. Same Host check and response headers as
every part-1 route. No path of a run directory or hub is sent; prompts and session result texts from the log are
never sent (only the fields above). Times are UTC strings; the page converts them to local time.

### H8. The page

The History tab button is enabled; the third tab stays a disabled placeholder ("Pipelines status — coming later").
The History tab has: a pipeline select (All + names), period buttons (Last run, Last 24 h, Last 7 days, All), the
summary line, and a table: Pipeline, ID, Title, Team, First start, Last end, Total (working / wall, labelled),
Result (badge colours: accepted green, in review blue, returned orange, open grey, declined red, unknown muted) and
an `escalated` badge. A row is a `<details>`-like expandable row listing its sessions (phase, start, end,
duration, outcome, denials / escalations when non-zero; "running since …"). Durations `H h MM min` (under an hour
`MM min`, under a minute `< 1 min`); times with `toLocaleString`. All text set via `textContent` (no hub text in
`innerHTML`). The history is fetched when the tab is shown and on the part-1 30 s refresh / "Refresh" only while
the tab is active; expanded rows stay expanded across refreshes (kept by pipeline + ID).

### H9. Tests

- `radark/tests/test_cockpit_history.py`, pure functions on invented records (IDs `HO-20990101-…`, teams
  `product`, `app`, pipelines `alpha` / `beta`): pairing and phase order, totals (working and wall), unmatched end,
  `interrupted`, open sessions closed by `dispatcher_start`, running session, timed-out outcome, sessions without a
  handover in the summary, each period incl. last run per pipeline and overlap at the window start, bad and partial
  lines skipped, cache hit (no re-parse when size and mtime are unchanged) and invalidation after an append.
- Results: every kind (accepted, in review, returned, open, declined, unknown) from fake `ho list` items, and
  unknown for a failing hub; escalated badge.
- Server: `GET /api/history` through the part-1 test harness (fake `ho`, server in a thread): filters, 400 on a bad
  period, 403 on a foreign Host, two pipelines on one hub → one `list` call (`.calls` file), no write `ho` call.
- End-to-end with the installed `ho` (like part 1's `test_cockpit_ho.py`): a throw-away hub made by `ho init
  --teams product=Product,app=App,owner=Owner` in `tmp_path`, invented handovers moved to each state with `ho new`,
  `ack`, `done`, `return`, `decline`, `close`; two configurations (`alpha`, `beta`) on that hub with invented
  `runs.jsonl` files; check every result kind incl. returned and unknown through `/api/history`. Fails with a clear
  message when `ho` is not on `PATH` (no skip).
- The page: the History tab is enabled, no external resource reference, hub text set with `textContent` only.

## Risks / Trade-offs

- [FIFO pairing guesses wrong if two sessions of one team, handover and phase ever overlap] → the dispatcher does
  not do that today; if it ever does, add the session ID to `session_start` in a later change.
- [`ho list --status all` grows with the hub] → one call per hub per request, only while the History tab is open;
  archived items are included, so old work keeps its result.
- [A dispatcher killed without restart leaves sessions "running" forever] → shown as running until the next
  `dispatcher_start` closes them; acceptable, RB-023 will show live state.
- [Large logs] → mtime/size cache; a full re-read only after a change.

## Migration

None. Old logs without some fields are read as far as they go; no configuration or `ho` change.
