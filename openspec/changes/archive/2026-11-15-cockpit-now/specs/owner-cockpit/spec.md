## ADDED Requirements

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

## MODIFIED Requirements

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
