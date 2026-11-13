## MODIFIED Requirements

### Requirement: Configuration
The dispatcher SHALL read its settings from one TOML file: the hub path, each team (id, repository path, kind `technical` or `product`), the Claude Code launch options, the auto-answer rules (default answer and escalation keywords), the product triage settings (triage team, the teams whose questions are triaged — all teams when not given — and the triage limit per handover), the polling interval, the per-item session limit, the session inactivity limit and the session maximum duration (default 180 minutes), the limit check extension (default 60 minutes) and the number of limit checks per session (default 3; 0 turns limit checks off), the wrap-up grace period at the last time limit (default 15 minutes; 0 turns the wrap-up off), the grace period after a wake of the computer, and the run-time directory (logs, state, lock). The former single session timeout key SHALL be accepted as the maximum duration. It MUST refuse to start, with a message naming the problem, if the file is missing a required value, a repository path does not exist, or `ho` or `claude` cannot be found.

#### Scenario: Valid configuration
- **WHEN** the owner starts the dispatcher with a complete configuration
- **THEN** it prints the hub, the teams with their repositories and the Claude Code version, and begins its loop

#### Scenario: Broken configuration
- **WHEN** a team's repository path does not exist
- **THEN** the dispatcher exits with a non-zero code and names the team and the path, and starts no session

#### Scenario: Old timeout key
- **WHEN** the configuration sets only `session_timeout_minutes = 180`
- **THEN** the session maximum duration is 180 minutes and the inactivity limit has its default

#### Scenario: Default wake grace period
- **WHEN** the configuration does not set the grace period after a wake
- **THEN** it is 3 minutes

#### Scenario: Default limit check settings
- **WHEN** the configuration sets neither the maximum duration, the limit check extension nor the number of limit checks
- **THEN** the first limit check comes at 180 minutes and a progressing session is extended by 60 minutes at a time, at most 3 times

#### Scenario: Invalid limit check settings
- **WHEN** the configuration sets the limit check extension to 0 or the number of limit checks to a negative value
- **THEN** the dispatcher exits with a non-zero code naming the key, and starts no session

#### Scenario: Default wrap-up grace period
- **WHEN** the configuration does not set `wrap_up_minutes`
- **THEN** a session that runs out of time gets 15 minutes to wrap up

#### Scenario: Invalid wrap-up grace period
- **WHEN** the configuration sets `wrap_up_minutes` to a negative value
- **THEN** the dispatcher exits with a non-zero code naming the key, and starts no session

### Requirement: Session time limits
Both limits SHALL count only time while the computer is awake. The dispatcher SHALL end a running session (the whole process tree) when its event stream has produced no event other than a tool progress heartbeat for the configured inactivity limit (default 20 minutes), or when it has run for the configured maximum duration (default 180 minutes), whichever comes first. For a work session the maximum duration is a checkpoint: a limit check MAY extend it (see "Limit check at the maximum duration"), and when no extension is left the session is asked to wrap up instead of being cut (see "Wrap-up at the last time limit"). A session that is not checked and not wrapped up ends at the maximum duration. An active session MUST NOT be ended by the inactivity limit. When a session ended by a time limit made progress, the next session for that item SHALL resume it, with a message saying it was stopped by a time limit, that the working tree may hold a partial edit, and to check the state and continue the phase; a session ended by a time limit without progress SHALL start no resume and counts as no progress.

#### Scenario: Hung session cut early
- **WHEN** a session's stream has been silent for 20 minutes
- **THEN** the dispatcher ends it, logs `idle_timeout`, and does not wait for the maximum duration

#### Scenario: Hung tool call cut
- **WHEN** a tool call has run for 20 minutes and the stream has carried only tool progress heartbeats meanwhile
- **THEN** the dispatcher ends the session and logs `idle_timeout`

#### Scenario: Long productive session not cut
- **WHEN** a work session keeps producing stream events for 5 hours and each of its limit checks answers `progressing`
- **THEN** it is not ended (checkpoints at 3, 4 and 5 hours; with the defaults it is asked to wrap up after 6 hours)

#### Scenario: Unchecked session ends at the maximum duration
- **WHEN** a goal check session has run for 180 minutes with the default configuration
- **THEN** it is ended and logged with `max_time`, without a limit check and without a wrap-up

#### Scenario: Continue after a limit
- **WHEN** an apply session was ended by `max_time` after committing part of the change
- **THEN** the item's next session resumes that session with the "stopped by a time limit, check and continue" message

#### Scenario: Timeout without progress
- **WHEN** a session was ended by `idle_timeout` with no hub activity, no commits and no newly checked tasks
- **THEN** the next session for the item starts fresh and the no-progress counter increases

#### Scenario: Sleep does not end a session by a time limit
- **WHEN** a `review` session starts at 01:15, the computer sleeps from 01:17 to 03:17 and the session goes on producing events after the wake
- **THEN** the session is not ended by `max_time` or `idle_timeout`, and its awake time counts about 2 minutes before the sleep

#### Scenario: Extended session ends at its new deadline
- **WHEN** a session was extended once from 180 to 240 minutes and its next limit check answers `hung`
- **THEN** it is ended at about 240 minutes and logged with `max_time`

### Requirement: Verdict of a limit check
For `progressing`, the dispatcher SHALL move the session's deadline forward by the configured extension and check again at the new deadline. After the configured number of extensions the session MUST NOT be checked again at its deadline; it SHALL be asked to wrap up (see "Wrap-up at the last time limit"). For `hung`, a missing or malformed verdict, or a failed check, the session SHALL be ended by `max_time` as before, without a wrap-up; after `hung` the resume message SHALL carry the product team's reason. Every verdict SHALL be written to the run log.

#### Scenario: Progressing session extended
- **WHEN** the limit check of a session at 180 minutes answers `progressing` because the session runs its final test suite
- **THEN** the session goes on, its new deadline is 240 minutes, and the log and the console show the verdict, the reason and the extension

#### Scenario: Extensions used up
- **WHEN** a session has been extended 3 times (the default) and reaches its deadline again
- **THEN** it is not checked again and is asked to wrap up

#### Scenario: Hung session ended
- **WHEN** the limit check answers `hung` because the session has repeated the same failing command for an hour
- **THEN** the session is ended by `max_time` without a wrap-up, and if it made progress, the item's next session resumes it with the time-limit message and the product team's reason

#### Scenario: Check fails
- **WHEN** the limit check ends with an error or a verdict that does not fit the expected structure
- **THEN** the session is ended by `max_time` without a wrap-up, as if the check had answered `hung`, and the problem is shown on the console

#### Scenario: Session ends during the check
- **WHEN** the checked session finishes, or is ended by the inactivity limit, while its limit check runs
- **THEN** the check is ended, its verdict is ignored, and the session's outcome is classified as without the check

#### Scenario: Checks turned off
- **WHEN** the configuration sets the number of limit checks to 0
- **THEN** a work session at its maximum duration is not checked and is asked to wrap up at once

## ADDED Requirements

### Requirement: Wrap-up at the last time limit
When a work session for a handover reaches its deadline with no extension left (checks used up, checks off, or no product team) and the wrap-up grace period is not 0, the dispatcher SHALL NOT cut it by `max_time`. It SHALL end the process and at once resume the same session with a wrap-up prompt, limited to the grace period, without a limit check or a second wrap-up. Sessions judged `hung` or whose check failed, and non-work sessions, SHALL NOT be wrapped up.

#### Scenario: Checks turned off
- **WHEN** the configuration sets the number of limit checks to 0 and a work session reaches 180 minutes
- **THEN** it is asked to wrap up at 180 minutes, without a limit check

#### Scenario: Hung session gets no wrap-up
- **WHEN** the limit check of a session answers `hung`
- **THEN** the session is ended by `max_time` and no wrap-up session starts

#### Scenario: Wrap-up turned off
- **WHEN** the configuration sets `wrap_up_minutes = 0` and a work session's extensions are used up
- **THEN** it is ended by `max_time` at its deadline, as before

### Requirement: Wrap-up prompt
The wrap-up prompt SHALL give the grace period, say the running step was cut off, and ask the session to check `git status`, start no new work, commit what works, report what is done the way its phase reports it, and name what is left on a `Left:` line. For apply it SHALL ask to check off finished tasks and report with `ho done` starting `Wrapped up at the time limit.`.

#### Scenario: Apply wrap-up prompt
- **WHEN** an apply session for HO-20261028-xaai is asked to wrap up with the default grace period
- **THEN** the resumed session's prompt names the 15-minute grace period, asks to check `git status`, commit what works, check off finished tasks and report with `ho done HO-20261028-xaai` starting `Wrapped up at the time limit.` with a `Left:` line, and not to archive

### Requirement: Outcome of a wrap-up
The stopped first part SHALL be classified `interrupted` and MUST NOT count as an error. The step's outcome SHALL be the wrap-up session's outcome, and the item's progress SHALL be measured from the first part's start. A wrap-up session still running at the end of the grace period SHALL be ended by `max_time`, and the rules for a session ended by a time limit apply to it. The inactivity limit, the wake grace period and the owner's Ctrl+C SHALL apply to the wrap-up session as to any session.

#### Scenario: Progressing session wraps up after its last extension
- **WHEN** an apply session was extended 3 times, reaches its deadline again, and in its wrap-up session commits, checks off its finished tasks and reports with `ho done` within 15 minutes
- **THEN** the step's outcome is `finished` (not `error`, not `max_time`), the console shows that the session is asked to wrap up, and the run log has `wrap_up_start` and `wrap_up` events with the extensions used, the grace period and the outcome

#### Scenario: Session ignores the wrap-up
- **WHEN** the wrap-up session keeps working past the 15-minute grace period
- **THEN** it is ended by `max_time`, its outcome is `error`, and the `wrap_up` event records `max_time`

### Requirement: Signal of a too-big task
Each wrap-up SHALL be shown on the console and written to the run log as `wrap_up_start` and `wrap_up` events with the team, handover, phase, session, elapsed time, extensions used and grace period, and for `wrap_up` the wrap-up session, its outcome and its time limit, if any. The item's state SHALL keep a history of its sessions that were wrapped up or ended by a time limit (kind, reason, extensions used, elapsed time, outcome).

#### Scenario: Wrap-up in the run log
- **WHEN** a session is wrapped up after 3 extensions and its wrap-up session finishes
- **THEN** the run log has `wrap_up_start` and `wrap_up` with 3 extensions, the grace period and the outcome `finished`, and the item's history has one `wrap_up` entry

### Requirement: Time-limit note in the review
When the product team's review prompt for a handover is built and the item's time-limit history is not empty, the prompt SHALL contain a paragraph that summarizes the history, says the task may be too big for one session, and asks the product team to check the result's `Left:` list and, if work is left, to return the handover for it or record it as a follow-up and say which in its close or return message.

#### Scenario: Review names the wrap-up
- **WHEN** an apply session on a handover was wrapped up after 6 hours with 3 extensions and finished, and the product team now reviews that handover
- **THEN** the review prompt contains the time-limit paragraph naming the wrap-up after 6 h with 3 extensions

#### Scenario: Repeated cuts are counted
- **WHEN** two sessions on the same handover were ended by a time limit before the item reached review
- **THEN** the review prompt's paragraph names both

#### Scenario: No time limit, no paragraph
- **WHEN** no session on a handover was wrapped up or ended by a time limit
- **THEN** its review prompt has no time-limit paragraph
