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
The configuration SHALL set how many sessions may run at once (`[loop] parallel_sessions`, an integer of at least 1, default 1); limit checks and triage consultations do not count. With 1 it SHALL run one session at a time. With more, while a place is free, it SHALL start the next owner-answer resume or candidate (by *Selecting the next work item*) whose repository and handover have no running session. A value below 1 or not an integer MUST be refused at start.

#### Scenario: App and backend at once
- **WHEN** `parallel_sessions` is 2, `app` has an `apply` candidate and `backend` has an unrelated `propose` candidate
- **THEN** both sessions run at the same time

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


### Requirement: Number of parallel sessions in the environment
Every session SHALL get the configured number of parallel sessions in its environment as `HARNESS_PARALLEL_SESSIONS`, also when it is 1.

#### Scenario: Environment of a session
- **WHEN** `parallel_sessions` is 2 and a session of `backend` starts
- **THEN** its environment has `HARNESS_PARALLEL_SESSIONS=2`

### Requirement: Run control with parallel sessions
`PAUSE`, `STOP`, the end time, the usage budget, the usage hold, a usage-limit back-off, the maximum number of sessions and a goal run's limits SHALL stop the dispatcher from starting new sessions, while running sessions finish and are processed as usual (triage, wrap-up, escalation, review hand-off); the run SHALL end only after the last of them. Keeping the computer awake, the usage readings and the usage budget SHALL be shared by all sessions of the run.

#### Scenario: End time with two sessions running
- **WHEN** the end time 12:00 passes while a `app` and a `backend` session run
- **THEN** no new session starts, both sessions finish, and the run ends after the later of them

#### Scenario: Usage limit hit by one session
- **WHEN** one of two running sessions ends with a usage-limit hit
- **THEN** the other session goes on, and no new session starts until the back-off or the known reset is over

#### Scenario: STOP with two sessions running
- **WHEN** the owner creates the `STOP` file while a `app` and a `backend` session run
- **THEN** no new session starts, both sessions finish and are processed, and the dispatcher exits

#### Scenario: Wrap-up of one session
- **WHEN** a `backend` session reaches its last time limit while a `app` session runs
- **THEN** only the `backend` session is stopped and resumed for its wrap-up with its own grace period, and the `app` session goes on

### Requirement: Ctrl+C with parallel sessions
On the first Ctrl+C every running session SHALL finish and be processed and no new one start; on the second every running session and its consultation SHALL be ended with outcome `interrupted` (cause owner).

#### Scenario: Owner finishes everything
- **WHEN** the owner presses Ctrl+C once while two sessions run
- **THEN** both sessions finish and are processed, no new session starts, and the dispatcher exits

#### Scenario: Owner ends everything
- **WHEN** the owner presses Ctrl+C twice while two sessions run
- **THEN** both sessions end with outcome `interrupted` and cause owner, and the dispatcher exits

### Requirement: Whole-hub steps while sessions run
When a place is free, no owner answer or candidate can use it and the product team's repository has no running session, the idle ask and, in a goal run, the goal check MAY run while other sessions run, each when it is due by its own rule. Their prompt SHALL name the work in progress (team, handover, title, phase) and ask to hand over or start only work that does not depend on it and does not touch those handovers or their changes.

#### Scenario: Idle ask next to a long apply
- **WHEN** `app` runs an `apply` session, `parallel_sessions` is 2, the idle ask is due and no other candidate exists
- **THEN** the idle ask runs in the product team's repository, and its prompt names the running `app` handover as work in progress

#### Scenario: Nothing running
- **WHEN** no session runs and the idle ask is due
- **THEN** its prompt has no work-in-progress section, as before

### Requirement: Goal check while sessions run
In a goal run, a goal check SHALL NOT be repeated while sessions run and the hub has not changed since the last goal check. A goal verdict `complete` or `blocked` SHALL stop new starts and end the run only after the running sessions are processed.

#### Scenario: Goal complete while a session runs
- **WHEN** a goal check returns `complete` while a `backend` session still runs
- **THEN** no new session starts and the goal run ends with status `complete` after the `backend` session is processed

#### Scenario: No repeated goal check while waiting
- **WHEN** in a goal run a goal check found nothing new to start while a `backend` session runs, and the hub has not changed since
- **THEN** no further goal check starts until the hub changes or the `backend` session has been processed

### Requirement: Console with parallel sessions
Every end line SHALL name the team, the phase or step and the handover (or the kind of step without a handover). With more than one session allowed, the start line SHALL show how many sessions run, including the new one, when that is more than one. Lines of different sessions SHALL never be mixed within one line.

#### Scenario: Interleaved end lines
- **WHEN** a `backend` session ends while a `app` session still runs
- **THEN** the end line names `backend` and its handover ID, and the next line from `app` names `app` and its own

#### Scenario: Running count
- **WHEN** `parallel_sessions` is 2 and a `backend` session starts while a `app` session runs
- **THEN** the `backend` start line shows `(2 running)`

### Requirement: Recovery of parallel sessions
The state SHALL keep one record per running session; a single record written by an earlier version SHALL be read as one. When `run` or `once` starts and finds such records left by a dispatcher that is no longer running, it SHALL handle each of them as *Recovery of an interrupted session* says.

#### Scenario: Window closed with two sessions
- **WHEN** the owner closes the dispatcher's window while a `app` and a `backend` session run, and starts `run` again
- **THEN** both sessions are reported and logged as `interrupted`, and each item's next session resumes its own session

#### Scenario: State of an earlier version
- **WHEN** `run` starts with a state that has one running record in the earlier format
- **THEN** that session is recovered as before

### Requirement: A session's processes end with it
When a session ends in any way (normal end, time limit, wrap-up stop, sleep, owner, dispatcher stop), every process it started SHALL end with it, including processes started in the background or detached from their parent; they MUST NOT outlive the session. Processes of another session and of the dispatcher MUST NOT be affected. When this cannot be ensured on the computer, the dispatcher SHALL fall back to ending the session's process tree and log it once.

#### Scenario: Background test run after a time limit
- **WHEN** a session started a full test run in the background, its parent shell exited, and the dispatcher ends the session at the inactivity limit
- **THEN** the test run and its browser and server processes end too, and the resumed session starts with no process of the old one left

#### Scenario: Leftover after a normal end
- **WHEN** a session ends normally while a server it started in the background still runs
- **THEN** the server ends with the session

#### Scenario: The other session is untouched
- **WHEN** a `backend` session is ended while a `app` session runs its tests
- **THEN** the `app` session's processes go on

### Requirement: Parallel note in the work prompt
With more than one session allowed, every work prompt (phase prompt, resume after a time limit or an interruption, resume with the owner's answer) SHALL say that another team may work on the same computer at the same time: stop only processes the session started itself, by their ID; use no fixed shared ports or paths outside the repository and the session temp directory; expect slower runs. With one session allowed the prompts SHALL be as before.

#### Scenario: Parallel note in the prompt
- **WHEN** `parallel_sessions` is 2 and a work session starts
- **THEN** its prompt includes the note about another team on the same computer

#### Scenario: No note with one session
- **WHEN** `parallel_sessions` is 1 and a work session starts
- **THEN** its prompt has no such note

### Requirement: Hub lock required for parallel sessions
With `parallel_sessions` above 1, the start check of `ho` (see *Compatibility of ho*) for `run`, `once` and `dry-run` SHALL also require the installed `ho` to report that it serialises hub writes and `sync`. When it does not, the dispatcher MUST stop as *Stopping on an incompatible ho* says, with a message that names the `ho` version and says to install a radark-handover with the hub lock or to set `parallel_sessions = 1`. Otherwise the check is as before.

#### Scenario: ho without the lock
- **WHEN** `parallel_sessions` is 2 and `ho --version --json` reports a supported contract but no hub lock
- **THEN** `run` exits with code 2 with that message, takes no run lock and starts no session

#### Scenario: ho with the lock
- **WHEN** `parallel_sessions` is 2 and `ho --version --json` reports the hub lock
- **THEN** the run starts as usual

#### Scenario: One session needs no lock
- **WHEN** `parallel_sessions` is 1 and `ho` reports no hub lock
- **THEN** the run starts as before

### Requirement: Dry run with parallel sessions
With more than one session allowed, dry-run SHALL print, after the session it would start, the further sessions it would start at the same time by *Number of parallel sessions*, or that nothing else could start and why. With one session allowed its output SHALL be as before. The plan mode SHALL stay a sequential prediction.

#### Scenario: Two teams in a dry run
- **WHEN** `parallel_sessions` is 2 and `app` and `backend` have unrelated candidates
- **THEN** dry-run names the `app` session it would start and a line naming the `backend` session it would start in parallel
