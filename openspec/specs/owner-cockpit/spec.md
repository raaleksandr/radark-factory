# owner-cockpit Specification

## Purpose

A local web page, started by the engine, that lists what the owner team is asked for across all known pipelines (escalations and requests) and lets the owner answer short ones through `ho`.

## Requirements

### Requirement: Cockpit command
The engine SHALL provide a command `cockpit` (`radark cockpit`, `python -m radark cockpit`) that starts a local HTTP server bound to `127.0.0.1` only and, unless `--no-browser` is given, opens the default browser on its main page. It SHALL accept `--port N`, a repeatable `--config PATH` and `--forget PATH`, and SHALL NOT need a configuration file in the current directory. It SHALL use the Python standard library only and run until interrupted.

#### Scenario: Start without a browser
- **WHEN** the owner runs `radark cockpit --no-browser` and port 7391 is free
- **THEN** the server listens on `127.0.0.1:7391`, prints `Cockpit running at http://127.0.0.1:7391/`, and no browser is opened

#### Scenario: Start with the browser
- **WHEN** the owner runs `radark cockpit` and port 7391 is free
- **THEN** the default browser is opened on `http://127.0.0.1:7391/`

### Requirement: Cockpit port
The cockpit port SHALL be `--port N` when given, else `[cockpit] port` of `machine.toml` in the machine directory, else 7391. A `[cockpit] port` that is not an integer from 1 to 65535 MUST make `cockpit` exit with code 2 naming the file and key.

#### Scenario: Port from the machine configuration
- **WHEN** `machine.toml` sets `[cockpit] port = 7400` and no `--port` is given
- **THEN** the cockpit listens on port 7400; with `--port 7500` it listens on 7500

#### Scenario: Invalid port setting
- **WHEN** `machine.toml` sets `[cockpit] port = 70000`
- **THEN** `cockpit` exits with code 2 naming `machine.toml` and `cockpit.port`

### Requirement: Busy cockpit port
When the port cannot be bound, the cockpit SHALL request `/api/health` on it. If a cockpit answers, it SHALL print `Cockpit already running at http://127.0.0.1:<port>/`, open the browser on it (unless `--no-browser`) and exit 0; otherwise it SHALL exit 2 with one line saying the port is busy and naming `--port N` and `[cockpit] port`. It MUST NOT switch to another port on its own.

#### Scenario: Cockpit already running
- **WHEN** a cockpit runs on port 7391 and the owner runs `radark cockpit --no-browser` again
- **THEN** the second command prints `Cockpit already running at http://127.0.0.1:7391/` and exits 0 without starting a server

#### Scenario: Port used by another program
- **WHEN** another program listens on port 7391 and does not answer as a cockpit
- **THEN** `radark cockpit` exits with code 2 and one line naming `--port N` and `[cockpit] port`

### Requirement: Pipelines shown by the cockpit
The cockpit SHALL show every pipeline of the machine-wide pipeline registry plus each `--config PATH` it was given, deduplicated by resolved path, and SHALL record each given `--config` in the registry. Pipelines that share one hub and owner team SHALL be read from that hub once, and each item SHALL name every such pipeline.

#### Scenario: Two pipelines on one hub
- **WHEN** pipelines `alpha` and `beta` both use the same hub and owner team
- **THEN** the hub is listed once per refresh, and each of its owner items shows both names

#### Scenario: Configuration given on the command line
- **WHEN** the owner runs `radark cockpit --config PATH` for a configuration not yet registered
- **THEN** its pipeline is shown and the registry has an entry for it

### Requirement: Missing and forgotten pipelines
A registered configuration that no longer exists SHALL be listed as missing, and a configuration that cannot be loaded as an error with its message. The owner SHALL be able to forget a registered configuration with `radark cockpit --forget PATH` or with a button in the page; both MUST change only the registry, never the hub.

#### Scenario: Missing configuration
- **WHEN** the registry lists a configuration file that was deleted
- **THEN** the page lists that pipeline as missing with a "Forget" button, and the other pipelines' items still show

#### Scenario: Forget from the command line
- **WHEN** the owner runs `radark cockpit --forget PATH` for a registered configuration
- **THEN** the entry is removed from the registry, one line confirms it, no server starts and the command exits 0

### Requirement: Owner items list
The main page SHALL list every handover addressed to the pipeline's owner team (`owner_team`, default `owner`), read with `ho list --to <owner team> --status all` and `ho show <ID>` as that team, in two sections: Pending (the owner's state is pending or returned, or acknowledged on a handover that expects `done` or `response`, and the handover is not closed) and Done (all others, including an acknowledged handover that expects `ack`), each sorted by last activity, newest first.

#### Scenario: Pending and done
- **WHEN** a hub has an open escalation to `owner` and a resolved request answered by `owner`
- **THEN** the escalation is under Pending and the request under Done, each with its pipeline name

#### Scenario: Acknowledged note
- **WHEN** the owner acknowledges a handover that expects `ack`
- **THEN** it is listed under Done

#### Scenario: Newest first
- **WHEN** two pending items have last activity at 10:00 and 11:00
- **THEN** the 11:00 item is listed first

### Requirement: Refresh and failing hubs
The page SHALL reload its data about every 30 seconds and on a "Refresh" button. A hub whose read fails SHALL be shown as an error for its pipelines while the other hubs' items still show.

#### Scenario: Refresh button
- **WHEN** an item is answered in a console with `ho` and the owner presses "Refresh"
- **THEN** the page shows the item under Done

#### Scenario: One hub fails
- **WHEN** the `ho` of one pipeline fails and another pipeline's hub is readable
- **THEN** the page shows an error for the first pipeline and the items of the second

### Requirement: Owner item details
Each item SHALL show the pipeline name(s), the sender, the created and last-activity times, the title, the tags with a distinct `escalation` badge, `expects`, the body and the history of events, and the note "Answer here only if a short answer is enough; files to place or code to change must be handled outside the cockpit." The sender, `expects`, the times, the tags, the body, the history, the note and the answer controls SHALL be shown only while the item's line is open.

#### Scenario: Item card
- **WHEN** a pending item from `product` tagged `escalation` is listed and the owner opens its line
- **THEN** its details show the pipeline name, `product`, both times, the title, the `escalation` badge, `expects`, the body, the events and the note

#### Scenario: Details hidden until opened
- **WHEN** the Owner tab is loaded with a pending item that has a body, events and answer actions
- **THEN** its body, events and answer controls are not visible until the owner opens its line

### Requirement: Owner inbox line
In both the Pending and the Done section each owner item SHALL be shown as one compact line with its title (its ID when it has none), its arrival time (the handover's created time as date and time in the browser's local time zone) and its pipeline name(s). The order of the lines SHALL stay that of "Owner items list".

#### Scenario: Line per owner handover
- **WHEN** a hub has two pending handovers to `owner` for pipeline `alpha`, created at 09:05 and 10:40 UTC
- **THEN** the Pending section shows two lines, each with its title, its created date and time in local time and `alpha`

#### Scenario: Order kept
- **WHEN** an escalation's last activity is at 10:00 and a normal item's at 11:00
- **THEN** the normal item's line is listed first

### Requirement: Escalation marked in the list
A line whose item is tagged `escalation` SHALL carry the escalation mark on the line itself (the red left border and the `escalation` badge), visible without opening it. Lines of other items MUST NOT carry it.

#### Scenario: Escalation line marked
- **WHEN** the Owner tab lists one escalation and two normal owner handovers
- **THEN** only the escalation's line shows the red mark and the `escalation` badge

### Requirement: Opening and closing an owner line
Clicking a line, or pressing Enter or Space while it has keyboard focus, SHALL open the item's details in place below the line; doing it again SHALL close them. At most one item SHALL be open at a time: opening a line closes the one open before. Each line SHALL be reachable with the keyboard and SHALL expose whether it is open.

#### Scenario: Open shows the details
- **WHEN** the owner clicks the line of a pending item that expects `response`
- **THEN** its body, its history of events and its answer controls (text field and the allowed actions) are shown

#### Scenario: Keyboard
- **WHEN** a line has keyboard focus and the owner presses Enter, then Space
- **THEN** the details open, then close

#### Scenario: One open at a time
- **WHEN** one item is open and the owner opens another line
- **THEN** the second item's details are shown and the first item's are hidden

### Requirement: Owner list state kept across refresh
A refresh (periodic or the "Refresh" button) SHALL keep the open item open when it is still listed, and MUST NOT lose or clear an answer being typed, whether its item is open or closed. After an answer is sent successfully the list SHALL be reloaded as today.

#### Scenario: Open item and typed answer survive a refresh
- **WHEN** the owner opens a pending item, types part of an answer and the page refreshes
- **THEN** the item is still open and the text field still holds the typed text

#### Scenario: Open item no longer listed
- **WHEN** the open item has disappeared from the hub's list at the next refresh
- **THEN** the page shows the remaining lines, all closed, without an error

### Requirement: Answering through ho
A pending item SHALL offer only the actions among `respond` (text), `done` (optional note), `ack` and `decline` (reason) that `ho show --json` lists in `allowed_actions` for the owner team. An answer (a `POST` with a JSON body) SHALL be checked against a fresh `ho show`, run as `ho <action> <ID> --body -` with the owner team, followed by `ho sync` on that hub; the `ho` result or error SHALL be shown. `respond` and `decline` MUST have a non-empty text.

#### Scenario: Respond to an escalation
- **WHEN** the owner types an answer to a pending `expects response` item and presses "Respond"
- **THEN** the server runs `ho respond <ID> --body -` with the owner team and the text, then `ho sync`, and after the reload the item is under Done

#### Scenario: Action not allowed any more
- **WHEN** the page offers "Done" but the item was answered meanwhile and `ho show` no longer lists `done` for the owner
- **THEN** the server refuses with the allowed actions, runs no write command, and the page shows the refusal

#### Scenario: ho error shown
- **WHEN** `ho decline` fails with exit code 3
- **THEN** the page shows `ho`'s message and the item stays pending

### Requirement: Hub written only through ho
The cockpit MUST NOT create, edit or delete any file in a hub; every hub change SHALL go through the `ho` command of the pipeline's configuration, after the same `ho` contract check the engine uses.

#### Scenario: Incompatible ho
- **WHEN** a pipeline's `ho` reports a contract the engine does not support
- **THEN** that pipeline's hub is shown as an error with the check's message and nothing is read from or written to it

### Requirement: Cockpit request checks
The server SHALL refuse with status 403 every request whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>`, and every `POST` whose `Origin` header, when present, is not `http://127.0.0.1:<port>` or `http://localhost:<port>`, or whose content type is not `application/json`. Requests that change anything MUST be `POST`; `GET` requests MUST NOT change the hub or the registry. The server MUST NOT send CORS headers and MUST NOT send anything to another host.

#### Scenario: Foreign origin
- **WHEN** a `POST /api/action` arrives with `Origin: http://example.invalid`
- **THEN** the server answers 403 and runs no `ho` command

#### Scenario: DNS rebinding
- **WHEN** a request arrives with `Host: attacker.invalid:7391`
- **THEN** the server answers 403

### Requirement: Escaped hub text
All hub text SHALL be escaped in the page. Markdown SHALL be rendered only as a minimal subset applied after escaping, with links only to `http://` and `https://` targets.

#### Scenario: Script in a body
- **WHEN** a handover body contains `<script>alert(1)</script>`
- **THEN** the page shows the text literally and runs no script

### Requirement: Self-contained cockpit page
The page SHALL be one HTML document with its CSS and JavaScript inline, served by the cockpit, using no CDN, external font, external script or build step. It SHALL have three tabs: the owner items as the active tab on load, the History of finished work, and Now (the current state of the pipelines).

#### Scenario: No external resources
- **WHEN** the page is served
- **THEN** it references no resource outside the cockpit's own origin

#### Scenario: History tab
- **WHEN** the owner opens the History tab
- **THEN** the page shows the summary line, the filters and the rows of the history

#### Scenario: Now tab
- **WHEN** the owner opens the Now tab
- **THEN** the page shows the machine line and one card per pipeline, and no tab is a placeholder

### Requirement: Cockpit documentation
The README SHALL have a "Cockpit" section describing what the page shows (the owner items, the History of finished work and the Now tab, and where they read from: the History from each pipeline's run log and its hub through `ho`; Now from the machine directory's instance records, each run directory's `runs.jsonl` and `goal.json`, and the hub's handover list through `ho`), how to start it (`npm run cockpit`, `radark cockpit`, `python -m radark cockpit`), the port and `[cockpit] port`, the one-line script a pipeline repository adds to its own `package.json` to get `npm run cockpit`, and the security note (local only, no login, writes only through `ho`). The engine's `package.json` SHALL have a `cockpit` script. Examples and screenshots SHALL use only neutral names.

#### Scenario: npm script
- **WHEN** the owner runs `npm run cockpit` in the engine repository
- **THEN** the cockpit starts as with `python -m radark cockpit`

#### Scenario: History documented
- **WHEN** the owner reads the README "Cockpit" section
- **THEN** it says what the History tab shows and that it reads each pipeline's `runs.jsonl` and the hub through `ho`

#### Scenario: Now documented
- **WHEN** the owner reads the README "Cockpit" section
- **THEN** it says what the Now tab shows and that it reads the machine directory's instance records, each run directory's `runs.jsonl` and `goal.json`, and the hub through `ho`, without changing any of them

### Requirement: History of finished work
The cockpit SHALL have a History tab that lists, for every pipeline it shows, the work recorded in that pipeline's run log (`runs.jsonl` in its run directory) as **one row per handover per pipeline**. A row SHALL show the pipeline name, the handover ID, its title, the team(s) of its sessions, the first session start, the last session end, the totals and the result. Rows of two pipelines MUST NOT be merged, even when the pipelines share one hub.

#### Scenario: One row per handover and pipeline
- **WHEN** pipeline `alpha` has sessions for `HO-20990101-aaaa` and `HO-20990101-bbbb`, and pipeline `beta` on the same hub has a session for `HO-20990101-aaaa`
- **THEN** the History lists three rows: two named `alpha` and one named `beta`

### Requirement: History order
History rows SHALL be sorted newest first by their latest session activity (the last end, or the start of a running session).

#### Scenario: Newest first
- **WHEN** one handover's last session ended at 10:00 and another's at 11:00
- **THEN** the 11:00 row is listed first

### Requirement: History sessions of a row
Expanding a row SHALL show its sessions in time order, each with its phase (as recorded, whatever the workflow profile used), start, end, duration and outcome (`finished`, `waiting_for_owner`, `error`, `interrupted`, `usage_limit`, timed out, or another recorded outcome), and the denial and escalation counts when they are not zero. A session with a start record and no end record SHALL be shown as "running" with its start time.

#### Scenario: Phases in order
- **WHEN** a handover has a `propose` session at 09:00, an `apply` session at 10:00 and an `archive` session at 12:00
- **THEN** its expanded row lists propose, apply, archive in that order with their durations and outcomes

#### Scenario: Running session
- **WHEN** the run log has a `session_start` for a handover and no matching `session_end`
- **THEN** that session is shown as "running" with its start time, and the row has no last end

#### Scenario: Timed-out session
- **WHEN** a `session_end` records a time-out
- **THEN** the session's outcome shows that it timed out

### Requirement: History totals
Each row SHALL show two labelled totals: working time, the sum of its sessions' durations, and wall time, the span from its first session start to its last session end. Durations SHALL be shown as hours and minutes (for example `1 h 05 min`) and times in the browser's local time zone.

#### Scenario: Working and wall time
- **WHEN** a handover has a 30-minute session from 09:00 and a 35-minute session from 11:00
- **THEN** its working time is `1 h 05 min` and its wall time `2 h 35 min`

### Requirement: History result
Each History row's result SHALL come from the hub's current state, read through `ho` only, as one of: accepted, in review, returned, open, declined or unknown. Unknown SHALL be shown when the handover is not in the hub or the hub cannot be read, never as an error of the row.

#### Scenario: Result meanings
- **WHEN** a handover is closed after the team's answer, or the team is done or has responded and it is not closed, or the sender returned the team's part after its last answer, or the team has not answered yet, or the team declined
- **THEN** its result is accepted, in review, returned, open or declined respectively

#### Scenario: Every result kind
- **WHEN** the hub has one handover closed after `done`, one done and not closed, one returned after `done`, one acknowledged only, one declined, and the run log has a sixth handover the hub does not know
- **THEN** their rows show accepted, in review, returned, open, declined and unknown

#### Scenario: Hub cannot be read
- **WHEN** the pipeline's `ho` fails
- **THEN** its rows are still listed from the run log, with result "unknown"

### Requirement: History escalated badge
A History row SHALL carry an **escalated** badge when the pipeline's run log has an escalation for its handover.

#### Scenario: Escalated badge
- **WHEN** the run log has an escalation for `HO-20990101-aaaa`
- **THEN** that handover's row has the escalated badge and the others do not

### Requirement: History filters and summary
The History SHALL be filtered by pipeline (all or one) and by period: **last run** (for each pipeline, since its latest `dispatcher_start`), **last 24 h**, **last 7 days** and **all**. A handover SHALL belong to a period when at least one of its sessions overlaps it; a running session overlaps every period that includes now.

#### Scenario: Last run per pipeline
- **WHEN** pipeline `alpha` last started at 08:00 today and pipeline `beta` at 08:00 yesterday, and the filter is "last run" for all pipelines
- **THEN** the list has `alpha`'s handovers with sessions since today 08:00 and `beta`'s with sessions since yesterday 08:00

#### Scenario: Session overlapping the period start
- **WHEN** the filter is "last 24 h" and a handover's only session started 25 hours ago and ended 23 hours ago
- **THEN** the handover is listed

### Requirement: History summary
Above the History list a one-line summary SHALL give, for the current filter, the number of handovers, the number of sessions, the working time and the number accepted. Sessions without a handover (goal checks, idle asks) SHALL NOT be rows; their count and total time SHALL be shown in the summary line.

#### Scenario: Sessions without a handover
- **WHEN** the run log has two goal-check sessions of 2 minutes each
- **THEN** no row is listed for them and the summary line counts 2 sessions without a handover, 4 min

### Requirement: History API
The cockpit SHALL serve the history as JSON on `GET /api/history` with the optional query parameters `pipeline` (a pipeline name; absent means all) and `period` (`last-run`, `24h`, `7d`, `all`; default `last-run`), under the same request checks as the other cockpit requests. An unknown `period` SHALL be refused with status 400. The history MUST NOT write to any hub, run log, registry or other file.

#### Scenario: Filtered request
- **WHEN** the page requests `/api/history?pipeline=alpha&period=7d`
- **THEN** the answer lists only `alpha`'s rows with a session in the last 7 days, and the summary for that filter

#### Scenario: Foreign host
- **WHEN** `GET /api/history` arrives with `Host: attacker.invalid:7391`
- **THEN** the server answers 403

#### Scenario: Read only
- **WHEN** the history is requested
- **THEN** no `ho` write command runs and no file changes

### Requirement: Tolerant and cached run log reading
The history SHALL skip run log lines that are not valid JSON objects (including a partial last line being written) and SHALL accept records without some fields, showing what is known. Parsed run logs SHALL be reused while a file's size and modification time are unchanged and read again when they change. Each hub SHALL be read at most once per history request, even when several pipelines share it.

#### Scenario: Bad lines skipped
- **WHEN** `runs.jsonl` has a line that is not JSON and a half-written last line
- **THEN** the other records are shown and no error is reported for the pipeline

#### Scenario: Log grows
- **WHEN** a new `session_end` is appended to a run log after a history request
- **THEN** the next history request shows it

#### Scenario: Shared hub read once
- **WHEN** pipelines `alpha` and `beta` use one hub
- **THEN** one history request lists that hub once

### Requirement: Now tab
The cockpit SHALL have a Now tab that shows **one card per pipeline the cockpit shows** (registered pipelines and those given with `--config`), whether it is running or not, with the pipeline's name on every card, and a machine line above the cards.

#### Scenario: Two pipelines, one running
- **WHEN** pipelines `alpha` and `beta` are registered and only `alpha` has a live dispatcher instance
- **THEN** the Now tab shows a card `alpha` with state `running` and a card `beta` with state `not running`

### Requirement: Now pipeline state
A card's state SHALL be `running` when a live dispatcher instance on this computer belongs to the pipeline (its instance record names the pipeline's configuration, or else its run directory), `not running` when there is none (no record, or only records whose instance is gone), and `unknown` when the pipeline's configuration or its run log cannot be read. A missing run log SHALL NOT make a card `unknown`.

#### Scenario: Live instance
- **WHEN** the machine directory has an instance record for `alpha`'s configuration whose instance lock is held by a running process
- **THEN** `alpha`'s card is `running` with that instance's start and PID

#### Scenario: Stale record
- **WHEN** the machine directory has an instance record for `alpha` whose lock is not held by any process
- **THEN** `alpha`'s card is `not running`

#### Scenario: Unreadable run log
- **WHEN** `alpha`'s `runs.jsonl` cannot be read
- **THEN** `alpha`'s card is `unknown` and the other cards are shown as usual

### Requirement: Now instances of a pipeline
A running card SHALL show each live instance's start time and PID. When the records show two live instances for one pipeline, the card SHALL list both and the cockpit MUST NOT fail.

#### Scenario: Two instances
- **WHEN** two live instance records name `alpha`'s configuration
- **THEN** `alpha`'s card lists both instances with their starts and PIDs

### Requirement: Now goal or regular run
A running card SHALL show "goal run" with the goal file's name (not its full path) and the goal run's start when the run directory's goal record says the goal run is running and was written by one of the card's live instances; otherwise it SHALL show "regular run". A card that is not running MAY show the last goal run's file name, status and end.

#### Scenario: Goal run
- **WHEN** `alpha` is running and its `goal.json` has status `running` and the PID of `alpha`'s live instance
- **THEN** the card shows "goal run", the goal file's name and its start

#### Scenario: Goal record left by an earlier run
- **WHEN** `alpha` is running and its `goal.json` has status `running` but the PID of no live instance
- **THEN** the card shows "regular run"

### Requirement: Now running sessions
A card SHALL list the sessions of its run log that have a `session_start` and no end after the latest `dispatcher_start`, each with team, handover ID, title (from the hub's handover list; "unknown" when the handover is not listed or the hub cannot be read), phase, start and elapsed time. They SHALL be shown as running only while the pipeline has a live instance; on a card that is not running they SHALL be shown as "interrupted".

#### Scenario: Running session
- **WHEN** `alpha` is running and its run log has, after its latest `dispatcher_start`, a `session_start` of team `app` on `HO-20990101-aaaa`, phase `apply`, and no matching end
- **THEN** the card lists that session as running with its title, phase, start and elapsed time

#### Scenario: Session before the latest start
- **WHEN** a `session_start` without an end comes before the latest `dispatcher_start`
- **THEN** it is not listed as running

#### Scenario: No live instance
- **WHEN** the run log ends with an open `session_start` and `alpha` has no live instance
- **THEN** the card lists that session as "interrupted", not running

#### Scenario: Unknown title
- **WHEN** a running session's handover is not in the hub's list
- **THEN** its title is shown as "unknown"

### Requirement: Now last event and last run
Every card SHALL show the time and kind of the newest run-log record. A card that is not running SHALL also show, when known, the end time and outcome of the last session, the time of the last `dispatcher_start` and the time of a stop record written after it; an end without a stop record SHALL be shown as not recorded.

#### Scenario: Pipeline alive
- **WHEN** the newest record of `alpha`'s run log is a `session_start` at 10:15
- **THEN** the card shows "last event: session_start" at 10:15 in local time

#### Scenario: Last run of a stopped pipeline
- **WHEN** `beta` is not running and its log ends with a `session_end` (outcome `finished`) and a `stop` record after its last `dispatcher_start`
- **THEN** the card shows the last session's end and outcome, the last start and the stop time

### Requirement: Now machine line
The Now tab SHALL show the session slots in use on this computer (summed over the live instances) and the machine limit from `machine.toml` (defaults with a note when it is invalid), the number of running pipelines, and the number of live instances that belong to no shown pipeline.

#### Scenario: Slots in use
- **WHEN** two live instances hold 1 and 2 session slots and `machine.toml` sets 3 sessions
- **THEN** the machine line shows 3 / 3 session slots in use

### Requirement: Now API
The cockpit SHALL serve the Now data as JSON on `GET /api/now` under the same request checks as the other cockpit requests. Times SHALL be sent in UTC and shown by the page in the local time zone, durations as `1 h 05 min`. The answer MUST NOT contain a run-directory, hub, goal-file or instance-record path, a prompt or a session result text. The page SHALL refresh the Now tab while it is active at least every 30 s.

#### Scenario: Foreign host
- **WHEN** `GET /api/now` arrives with `Host: attacker.invalid:7391`
- **THEN** the server answers 403

#### Scenario: Shared hub read once
- **WHEN** pipelines `alpha` and `beta` use one hub
- **THEN** one Now request lists that hub at most once

### Requirement: Now is read only
Producing the Now data MUST NOT write, create or remove any file in the machine directory, the run directories or the hubs, MUST NOT remove stale instance records (that is the dispatcher's job), MUST NOT run an `ho` write command, and MUST NOT hold any lock or slot beyond an instant's liveness probe.

#### Scenario: Stale records kept
- **WHEN** the machine directory has a live, a stale and an orphan instance record and `/api/now` is requested
- **THEN** every file in the machine directory and the run directories is unchanged afterwards (same names, sizes and modification times)
