## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Self-contained cockpit page
The page SHALL be one HTML document with its CSS and JavaScript inline, served by the cockpit, using no CDN, external font, external script or build step. It SHALL have tabs: the owner items as the active tab on load, the History of finished work, and a placeholder for a later view (state of running pipelines).

#### Scenario: No external resources
- **WHEN** the page is served
- **THEN** it references no resource outside the cockpit's own origin

#### Scenario: History tab
- **WHEN** the owner opens the History tab
- **THEN** the page shows the summary line, the filters and the rows of the history, and the running-pipelines tab is still a placeholder

### Requirement: Cockpit documentation
The README SHALL have a "Cockpit" section describing what the page shows (the owner items and the History of finished work, and where the History reads from: each pipeline's run log and its hub through `ho`), how to start it (`npm run cockpit`, `radark cockpit`, `python -m radark cockpit`), the port and `[cockpit] port`, the one-line script a pipeline repository adds to its own `package.json` to get `npm run cockpit`, and the security note (local only, no login, writes only through `ho`). The engine's `package.json` SHALL have a `cockpit` script. Examples and screenshots SHALL use only neutral names.

#### Scenario: npm script
- **WHEN** the owner runs `npm run cockpit` in the engine repository
- **THEN** the cockpit starts as with `python -m radark cockpit`

#### Scenario: History documented
- **WHEN** the owner reads the README "Cockpit" section
- **THEN** it says what the History tab shows and that it reads each pipeline's `runs.jsonl` and the hub through `ho`
