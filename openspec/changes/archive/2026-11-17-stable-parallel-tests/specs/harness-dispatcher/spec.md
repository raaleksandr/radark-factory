## MODIFIED Requirements

### Requirement: Number of parallel sessions
The configuration SHALL set how many sessions may run at once (`[loop] parallel_sessions`, an integer of at least 1, default 1); limit checks and triage consultations do not count. With 1 it SHALL run one session at a time. With more, while a place is free, it SHALL start the next owner-answer resume or candidate (by *Selecting the next work item*) whose repository and handover have no running session. A value below 1 or not an integer MUST be refused at start.

#### Scenario: App and backend at once
- **WHEN** `parallel_sessions` is 2, `app` has an `apply` candidate and `backend` has an unrelated `propose` candidate
- **THEN** both sessions run at the same time

#### Scenario: Start records of sessions started together
- **WHEN** `parallel_sessions` is 2 and the `app` and `backend` sessions are started at the same time
- **THEN** both `session_start` records are written before either session's `session_end`, in either order

#### Scenario: Default keeps one session
- **WHEN** the configuration does not set `parallel_sessions` and two teams have candidates
- **THEN** the dispatcher runs one of them and starts the other only after the first has ended

#### Scenario: Dependent work does not run in parallel
- **WHEN** `app`'s item is held while it waits for `backend`'s result on a handover that references it
- **THEN** only the `backend` session runs, and `app`'s item is selected after the hold ends

#### Scenario: Same handover
- **WHEN** `parallel_sessions` is 2 and one handover addressed to both `app` and `backend` is the only candidate of each team
- **THEN** only one of them runs, and the other starts after it has ended

#### Scenario: Invalid value
- **WHEN** the configuration sets `parallel_sessions = 0` or `parallel_sessions = "two"`
- **THEN** the dispatcher exits with a non-zero code naming the key, and starts no session
