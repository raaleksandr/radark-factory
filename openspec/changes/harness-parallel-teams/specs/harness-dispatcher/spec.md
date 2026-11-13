## RENAMED Requirements

- FROM: `### Requirement: One Claude Code session at a time`
- TO: `### Requirement: Claude Code sessions per repository`

## MODIFIED Requirements

### Requirement: Claude Code sessions per repository
The dispatcher SHALL run each phase as a new non-interactive Claude Code session (`claude -p`) with the team repository as working directory, using the owner's own installation and login, so the repository's CLAUDE.md, skills, settings and hooks load. It MUST NOT pass any API key of its own to the session and MUST NOT use a mode that skips the repository's settings or the login. At most one session SHALL run in a repository and for a handover at any moment, and at most the configured number of sessions in all (see *Number of parallel sessions*), except that a read-only consultation (a limit check, a triage consultation) runs next to the session it serves and does not count; when the dispatcher is stopped or the owner ends a session, its consultation is ended with it. A lock in the run-time directory MUST prevent a second dispatcher instance from starting. A handover MAY be marked in the state to continue its previous session, in which case the next phase resumes that session instead of starting a new one.

#### Scenario: Session in the right repository
- **WHEN** the dispatcher selects a `app` candidate
- **THEN** a `claude -p` session runs with `D:\work\app` (from the configuration) as working directory and receives the phase prompt

#### Scenario: Second instance refused
- **WHEN** the owner starts the dispatcher while another instance holds the lock
- **THEN** the new instance exits with a message and starts no session

#### Scenario: Kept session resumed
- **WHEN** a handover is marked to continue in one session and its propose phase has ended
- **THEN** the apply phase resumes the propose session by its session ID

#### Scenario: Owner ends the run during a limit check
- **WHEN** the owner presses Ctrl+C twice while a limit check runs next to a work session
- **THEN** both process trees are ended and the work session's outcome is `interrupted` with cause owner

#### Scenario: Two candidates for one repository
- **WHEN** two sessions may run in parallel and the two newest candidates are both for `app`
- **THEN** one `app` session runs, and the other candidate waits until it has ended, while a candidate of another team may start

## ADDED Requirements

### Requirement: Number of parallel sessions
The configuration SHALL set how many work sessions may run at once (`[loop] parallel_sessions`, an integer of at least 1, default 1). With 1 the dispatcher SHALL behave as one session at a time. With more, whenever fewer sessions run than allowed, it SHALL start the next candidate by the rule of *Selecting the next work item* whose repository and handover have no running session. A value below 1 or not an integer MUST be refused at start.

#### Scenario: App and backend at once
- **WHEN** `parallel_sessions` is 2, `app` has an `apply` candidate and `backend` has an unrelated `propose` candidate
- **THEN** both sessions run at the same time

#### Scenario: Default keeps one session
- **WHEN** the configuration does not set `parallel_sessions` and two teams have candidates
- **THEN** the dispatcher runs one of them and starts the other only after the first has ended

#### Scenario: Dependent work does not run in parallel
- **WHEN** `app`'s item is held while it waits for `backend`'s result on a handover that references it
- **THEN** only the `backend` session runs, and `app`'s item is selected after the hold ends

#### Scenario: Invalid value
- **WHEN** the configuration sets `parallel_sessions = 0`
- **THEN** the dispatcher exits with a non-zero code naming the key, and starts no session

### Requirement: Run control with parallel sessions
`PAUSE`, `STOP`, the end time, the usage budget, the usage hold and a usage-limit back-off SHALL stop the dispatcher from starting new sessions, while running sessions finish and are processed as usual; the run SHALL end only after the last of them. On the first Ctrl+C every running session SHALL finish and no new one start; on the second every running session SHALL be ended with outcome `interrupted` (cause owner).

#### Scenario: End time with two sessions running
- **WHEN** the end time 12:00 passes while a `app` and a `backend` session run
- **THEN** no new session starts, both sessions finish, and the run ends after the later of them

#### Scenario: Usage limit hit by one session
- **WHEN** one of two running sessions ends with a usage-limit hit
- **THEN** the other session goes on, and no new session starts until the back-off or the known reset is over

#### Scenario: Owner ends everything
- **WHEN** the owner presses Ctrl+C twice while two sessions run
- **THEN** both sessions end with outcome `interrupted` and cause owner, and the dispatcher exits

### Requirement: Whole-hub steps while sessions run
When a free place exists and no candidate can use it, the idle ask and, in a goal run, the goal check MAY run while other sessions run. Their prompt SHALL name the work in progress (team, handover, title) and ask to hand over only work that does not depend on it or touch the same repository's running change. A goal verdict `complete` or `blocked` SHALL end the run only after the running sessions are processed.

#### Scenario: Idle ask next to a long apply
- **WHEN** `app` runs an `apply` session, `parallel_sessions` is 2 and no other candidate exists
- **THEN** the idle ask may run, and its prompt names the running `app` handover

#### Scenario: Goal complete while a session runs
- **WHEN** a goal check returns `complete` while a `backend` session still runs
- **THEN** no new session starts and the goal run ends after the `backend` session is processed

### Requirement: Console with parallel sessions
With more than one session allowed, every start and end line SHALL name the team and the handover (or the step without a handover), so that interleaved lines can be told apart, and the start line SHALL show how many sessions run, including the new one, when that is more than one.

#### Scenario: Interleaved end lines
- **WHEN** a `backend` session ends while a `app` session still runs
- **THEN** the end line names `backend` and its handover ID, and the next line from `app` names `app` and its own

### Requirement: Recovery of parallel sessions
The state SHALL keep one record per running session. When `run` or `once` starts and finds such records left by a dispatcher that is no longer running, it SHALL handle each of them as *Recovery of an interrupted session* says.

#### Scenario: Window closed with two sessions
- **WHEN** the owner closes the dispatcher's window while a `app` and a `backend` session run, and starts `run` again
- **THEN** both sessions are reported and logged as `interrupted`, and each item's next session resumes its own session

### Requirement: A session's processes end with it
When a session ends in any way, every process it started SHALL end with it, including processes started in the background or detached from their parent, and MUST NOT outlive the session. Processes of another session MUST NOT be affected.

#### Scenario: Background e2e run after a time limit
- **WHEN** a session started a full e2e run in the background and the dispatcher ends the session at the inactivity limit
- **THEN** the e2e run and its browser and server processes end too, and the resumed session starts with no run of the old one left

#### Scenario: The other session is untouched
- **WHEN** a `backend` session is ended while a `app` session runs its tests
- **THEN** the `app` session's processes go on

### Requirement: Isolation of a session on a shared computer
Each session SHALL get a temporary directory of its own (`TEMP` and `TMP` point into the run directory, one directory per session), removed once the session is processed. With more than one session allowed, the session prompt SHALL say that another team may work on the same computer at the same time: stop only processes the session started itself, use no fixed shared paths or ports, and expect slower runs.

#### Scenario: Same temp file name in two repositories
- **WHEN** a `app` and a `backend` session both write `/tmp/e2e.log`
- **THEN** each writes its own file and neither reads the other's

#### Scenario: Parallel note in the prompt
- **WHEN** `parallel_sessions` is 2 and a work session starts
- **THEN** its prompt includes the note about another team on the same computer

### Requirement: Hub use from parallel sessions
Hub commands that change the hub (creating, answering, commenting, closing, `sync`) SHALL run one at a time across all users of the hub on the computer: agents of parallel sessions, the dispatcher and the owner. A command that waits for another one SHALL go on after it, and MUST NOT fail or leave the hub's working copy half-changed because of it.

#### Scenario: Two agents sync at once
- **WHEN** the `app` and `backend` agents run `ho sync` at the same moment
- **THEN** one sync runs after the other, both succeed, and both teams' changes are in the hub
