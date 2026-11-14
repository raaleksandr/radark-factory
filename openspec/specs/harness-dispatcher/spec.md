# harness-dispatcher Specification

## Purpose

Our own Python dispatcher that replaces the owner in the manual workflow: it reads the handover hub, wakes the right Claude Code team agent one session at a time, keeps the agent moving through pre-agreed stops, gates archiving on the author's approval, and leaves a log the owner can audit.

## Requirements

### Requirement: Configuration
The dispatcher SHALL read its settings from one TOML file: the hub path, each team (id, repository path, kind `technical` or `product`), the Claude Code launch options, the auto-answer rules (default answer and escalation keywords), the product triage settings (triage team, the teams whose questions are triaged — all teams when not given — and the triage limit per handover), the polling interval, the per-item session limit, the session inactivity limit and the session maximum duration (default 180 minutes), the limit check extension (default 60 minutes) and the number of limit checks per session (default 3; 0 turns limit checks off), the wrap-up grace period at the last time limit (default 15 minutes; 0 turns the wrap-up off), the grace period after a wake of the computer, the idle re-ask interval in awake minutes (default 60; 0 asks again only on hub activity), and the run-time directory (logs, state, lock). The former single session timeout key SHALL be accepted as the maximum duration. It MUST refuse to start, with a message naming the problem, if the file is missing a required value, a repository path does not exist, or `ho` or `claude` cannot be found.

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

#### Scenario: Default idle re-ask interval
- **WHEN** the configuration does not set `idle_reask_minutes`
- **THEN** the idle ask is repeated after 60 minutes of awake time without hub activity

#### Scenario: Invalid idle re-ask interval
- **WHEN** the configuration sets `idle_reask_minutes` to a negative value or a non-integer
- **THEN** the dispatcher exits with a non-zero code naming the key, and starts no session

### Requirement: Selecting the next work item
The dispatcher SHALL query `ho inbox --json` for every configured team (with `HO_TEAM` set to that team and `HO_HUB` to the configured hub) and build one candidate list from: each team's `action_required` items, each team's `to_review` items, and approved changes waiting to be archived (see *Archive gate*). It SHALL pick the candidate with the most recent hub activity first; ties are broken by the order of teams in the configuration. Items marked escalated or stalled MUST be skipped, and so MUST items held while they wait for a handover's result (see *Waiting for a handover's result*). Escalation handovers (those the dispatcher sent to the owner) MUST NOT become candidates for any team. The dispatcher MUST NOT edit the teams' handovers or carry task content between repositories itself; its only hub writes are the escalation handovers described in *Escalation to the owner* and `ho sync`.

#### Scenario: Newest handover wins
- **WHEN** `app` has an older `action_required` item and `backend` has just received a newer handover from `app`
- **THEN** the dispatcher runs `backend` first

#### Scenario: Nothing to do
- **WHEN** no team has a selectable candidate
- **THEN** the dispatcher starts no session and waits for the polling interval before checking again

#### Scenario: Escalated item ignored
- **WHEN** the only `action_required` item is marked escalated
- **THEN** the dispatcher treats the hub as having nothing to do

#### Scenario: Escalation handover is not a review item
- **WHEN** the owner has responded to an escalation handover sent from `app`
- **THEN** the dispatcher does not start a `review` session for `app` on that escalation handover

#### Scenario: Held item ignored
- **WHEN** the only `action_required` item is held while its team waits for another team's result
- **THEN** the dispatcher treats the hub as having nothing to do

### Requirement: Phase prompts
For each selected candidate the dispatcher SHALL choose a phase and send the team agent a prompt that names the handover ID, the phase and the expected next step:
- a technical team's new handover → **propose**: read the handover, acknowledge it, create an OpenSpec change citing the handover ID;
- a technical team's handover whose change is proposed → **apply**: implement the change; report `ho done` when finished, or send a handover to another team if it needs one;
- a handover returned to a technical team → **apply** on the same change, following the return comments;
- an author's `to_review` item → **review**: close the handover if the result is accepted, or return it with the request;
- an approved change → **archive**: archive the OpenSpec change;
- a product team's `action_required` item → **act** on the handover per the hub guide, without creating an OpenSpec change for routine work.
A technical handover's change counts as proposed only when the dispatcher knows it: the propose session named it, or a change in the team repository cites the handover ID. A propose session after which no such change is known, whatever its outcome, MUST leave the handover new, so that its next session is propose again; the dispatcher SHALL log this and show it on the console. The no-progress rule of *Session outcome* still applies to these repeated propose sessions.
Every prompt MUST also carry the standing rule: never ask the user; choose the best variant, record the assumption in the change, and continue; stop only when the phase is complete or blocked by something outside the repository.
Every session the dispatcher starts, new or resumed, MUST also carry the long-wait rule in its system prompt: do not wait silently on a command or a background task for longer than the check interval; check its progress at least once per interval (its latest output, a progress counter, whether the process is alive); if two checks in a row show no progress, treat it as hung: stop it, record what was seen, and continue another way or report it. The check interval SHALL be half the configured inactivity limit (`loop.session_idle_minutes`), rounded down to whole minutes, and at least 1 minute (10 minutes with the default 20-minute limit), and the rule SHALL state both the interval and the inactivity limit. The inactivity limit and what counts as activity are unchanged.

#### Scenario: New task goes to propose
- **WHEN** `app` has a new `action_required` handover `HO-20261016-ab12` with no change recorded for it
- **THEN** the session prompt asks the agent to read `HO-20261016-ab12`, acknowledge it and create an OpenSpec change citing that ID

#### Scenario: Returned task continues the same change
- **WHEN** the author returns a handover whose change `add-export` is recorded for `app`
- **THEN** the prompt asks the agent to continue `add-export` according to the return comments, and not to create a new change or archive

#### Scenario: Propose cut before the change exists
- **WHEN** the propose session for `HO-20261026-47ch` acknowledges the handover and then ends with an API error, and no change in `app` cites `HO-20261026-47ch`
- **THEN** the console shows that propose created no change, and the next session for `HO-20261026-47ch` is propose, not apply

#### Scenario: Propose that failed after creating the change
- **WHEN** a propose session ends with an error and gives no `CHANGE:` line, but a change `fix-scroll` in the team repository cites the handover ID
- **THEN** `fix-scroll` is recorded for the handover and the next session is apply on `fix-scroll`

#### Scenario: Repeated propose without progress stalls
- **WHEN** two consecutive propose sessions for the same handover end with no change, no hub activity, no commits and no checked tasks
- **THEN** the item is marked stalled and escalated to the owner, as for any item without progress

#### Scenario: Record from an older dispatcher
- **WHEN** a stored record says phase `propose` with no change, the handover is not returned and the hub shows no `done` by the team
- **THEN** the next session for that handover is propose

#### Scenario: Long-wait rule with the default limit
- **WHEN** the dispatcher starts or resumes any session with the default inactivity limit of 20 minutes
- **THEN** the session's system prompt carries the standing rule and the long-wait rule with a check interval of 10 minutes, and names the 20-minute limit

#### Scenario: Long-wait rule follows the configured limit
- **WHEN** `loop.session_idle_minutes` is 30
- **THEN** the long-wait rule names a check interval of 15 minutes and the 30-minute limit

#### Scenario: Non-integer limit rounds the interval down
- **WHEN** `loop.session_idle_minutes` is 25, or 2.5
- **THEN** the long-wait rule names a check interval of 12 minutes, or of 1 minute with the 2.5-minute limit

### Requirement: Archive only after the author closes
The propose prompt SHALL tell a technical team that the change's tasks must not include archiving the change or syncing its specs, and that archive is a separate phase run after the author closes the handover. Every apply prompt, for a new or a returned handover, SHALL tell the team not to archive the change and not to sync its specs, and to end with `ho done`, leaving any archive task unchecked.

#### Scenario: Propose prompt keeps archive out of the tasks
- **WHEN** the dispatcher starts a propose session of `app` for `HO-20261104-l6tz`
- **THEN** the prompt says the change's tasks must not include archiving or spec sync, because archive runs after the author closes the handover

#### Scenario: Apply prompt for a new handover forbids archiving
- **WHEN** the dispatcher starts an apply session of `app` for a handover that was not returned
- **THEN** the prompt tells it not to archive the change and not to sync its specs, and to report with `ho done`

#### Scenario: Apply prompt for a returned handover forbids archiving
- **WHEN** the dispatcher starts an apply session for a handover the author returned
- **THEN** the prompt tells it not to archive the change and not to sync its specs, as for a new handover

#### Scenario: Archive prompt unchanged
- **WHEN** the dispatcher starts an archive session after the author closed the handover
- **THEN** the prompt asks to archive the change, as before

### Requirement: Local TODO entries reach the product team
The apply prompt SHALL tell a technical team that, when its work added an entry to its repository's own TODO or backlog or materially changed one, it names each entry in its `ho done` summary on a `Local TODO:` line (id, title, one line why), and omits the line otherwise. The review prompt SHALL tell the product team to decide for each named entry whether it belongs in the product backlog, record those that do, and state the decision in its close or return message.

#### Scenario: Apply prompt asks for local TODO entries
- **WHEN** the dispatcher starts an apply session of `backend` for `HO-20261103-pn6g`
- **THEN** the prompt asks `backend` to list, on a `Local TODO:` line of its `ho done` summary, every entry of its own TODO it added or materially changed, with id, title and one line why

#### Scenario: Review prompt asks the product team to take them in
- **WHEN** the dispatcher starts a review session of `product` for `HO-20261103-pn6g`
- **THEN** the prompt asks it to decide for each entry on a result's `Local TODO:` line whether it belongs in the product backlog, record those that do, and say what it decided when it closes or returns the handover

#### Scenario: A missing backlog entry does not return the work
- **WHEN** a result names a local TODO entry that the product backlog does not have yet
- **THEN** the review prompt tells the product team to add it itself; the missing entry is not a reason to return the handover

#### Scenario: Other phases unchanged
- **WHEN** the dispatcher builds a propose, archive or act prompt
- **THEN** the prompt does not mention local TODO entries

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

### Requirement: Session outcome
The dispatcher SHALL save each session's full event stream to its own file and classify the outcome as one of: `finished` (normal end with a final result), `error` (non-zero exit or failure event, including a session ended by a time limit), `waiting_for_owner` (an escalation was recorded, a permission request was denied and the session did not complete its phase, see "Permission denial in a completed phase", or the worker reported that only the owner can unblock it, see "Worker blocked on the owner"), `question` (the agent's question was recorded for product triage and nothing was escalated), `usage_limit` (the plan's usage limit was hit), `interrupted` (the session was ended because the computer slept, the owner ended it with a second Ctrl+C, or the dispatcher stopped while it ran; see "Session after a wake" and "Recovery of an interrupted session"). An `interrupted` session MUST NOT count as an error or as no progress. A session ended by a time limit SHALL be logged with the limit that ended it (`idle_timeout` or `max_time`). After a `usage_limit` outcome it MUST start no new session until the configured back-off has passed. A session for a handover makes progress if, since its item's work began in that session, the hub shows new activity by the team on that handover or a new handover from that team, the team repository has new commits, or the item's OpenSpec change has more checked tasks. In the apply and act phases, new commits count only if at least one of them changes a file outside the item's own OpenSpec change directory; commits that change only files inside it (for example a note in `tasks.md` that the work still waits) MUST NOT count as progress, while more checked tasks in that change still do. If a session for a handover ends without progress, the dispatcher SHALL count it as no progress; after the configured number of sessions without progress the item MUST be marked stalled and escalated.

#### Scenario: Normal end
- **WHEN** the session exits with code 0 and a final result, with no denials and no escalations
- **THEN** the outcome is `finished` and the session ID is recorded

#### Scenario: Usage limit
- **WHEN** a session reports a rate-limit failure
- **THEN** the outcome is `usage_limit` and the dispatcher waits for the back-off before starting any session

#### Scenario: Agent going in circles
- **WHEN** two consecutive apply sessions for the same handover end without hub activity, new commits or newly checked tasks
- **THEN** the item is marked stalled, escalated to the owner, and no further session is started for it

#### Scenario: Work without hub activity counts
- **WHEN** an apply session ends with no hub event but with two new commits in the team repository that change source files
- **THEN** it counts as progress and the no-progress counter is reset

#### Scenario: Checked tasks count
- **WHEN** an apply session ends with no hub event and no commit, but three more tasks checked in the change's `tasks.md`
- **THEN** it counts as progress

#### Scenario: Only a waiting note in the change
- **WHEN** two consecutive apply sessions for HO-20261031-p3uj each end with one commit that changes only `openspec/changes/app-faster-provider/tasks.md`, with no more checked tasks and no hub activity
- **THEN** neither counts as progress, the console says the commits changed only the change's own files, and after the second the item is marked stalled and escalated to the owner

#### Scenario: Change notes with real work
- **WHEN** an apply session's commits change the change's `tasks.md` and also a test file outside the change directory
- **THEN** it counts as progress

#### Scenario: Interrupted is not an error
- **WHEN** a session is ended because the computer slept and it gives no sign of life after the wake
- **THEN** its outcome is `interrupted`, the no-progress counter of its item does not change, and the console end line names the cause

#### Scenario: Denial with an incomplete phase
- **WHEN** an apply session ends normally with one permission denial and the worker has not marked its part `done` or `declined`
- **THEN** the outcome is `waiting_for_owner` and the item is escalated with the reason `permission denied: <tool>`

### Requirement: Permission denial in a completed phase
A work-item session whose only reason to wait for the owner is a permission denial SHALL NOT be escalated when it completed its phase: it ended normally (exit 0, a final result, hooks loaded, no time limit, not interrupted) and during it the phase's signal appeared — propose: the change exists; apply or act: the worker marked `done` or `declined`; review: the handover was closed or returned to the worker; archive: the change directory is gone. Such a session SHALL get the outcome `finished`. Any other denial session SHALL be escalated as before. Sessions without a work item are not affected.

#### Scenario: Agent works around a denial and finishes
- **WHEN** an apply session has a PowerShell `Stop-Process` denied, stops its test run another way, marks its part `done` and exits with code 0 and a final result
- **THEN** the outcome is `finished`, no escalation handover is sent, the console shows the denial line and a line that the phase was completed despite it, and the run log has `denial` and `denial_not_escalated`

#### Scenario: Denial and an escalation together
- **WHEN** a session has a permission denial and also asks a question with an escalation keyword, then marks its part `done`
- **THEN** the item is escalated with both reasons, as before

#### Scenario: Denial in a session cut by a time limit
- **WHEN** a session with a permission denial is ended by the maximum duration
- **THEN** the phase is not complete and the item is escalated, as before

### Requirement: Visibility of a denial that was not escalated
For a denial that was not escalated the dispatcher SHALL keep the `denial` event and its `!` console line, also log `denial_not_escalated` (team, handover, phase, session, denials) and print one `!` line that the phase was completed despite it. It SHALL keep the denials with the item and name each (tool, shortened command or input) in the prompt of the item's next review, asking the reviewer to check that nothing required was skipped; then drop them. A goal report SHALL list them under "Permission denials not escalated" with item, team, phase, tool and command.

#### Scenario: Reviewer told about the denial
- **WHEN** the next session for that item is the author's review
- **THEN** the review prompt names the denied PowerShell command and asks the reviewer to check that nothing required was skipped because of it

#### Scenario: Goal report lists the denial
- **WHEN** a goal run ends after a session whose denial was not escalated
- **THEN** the report has a section "Permission denials not escalated" naming the item, team, phase, tool and command

### Requirement: Worker blocked on the owner
The apply and act prompts SHALL tell the worker: when it waits for another team's handover, stop without committing or commenting only to record that it still waits; when a decision is needed that its team's instructions (its `CLAUDE.md`, the owner's goal) allow the team to take, take it, record it in the change, inform the owner with a non-blocking handover (expecting only an acknowledgement) and continue; when only the owner can unblock it — what those instructions reserve for the owner, or, where they say nothing, a decision, money, credentials, a production step — end its final message with one line `BLOCKED: owner — <what is needed>`. When a work session ends with such a line as the last `BLOCKED:` line of its result and did not complete its phase (apply or act: the worker's part is not marked `done`, `declined` or answered), its outcome SHALL be `waiting_for_owner`, and the item MUST be escalated to the owner at once with the text after the dash as the reason, without waiting for `no_progress_limit`. A session that completed its phase is handled as before, whatever its last line says. The console escalation line and the run log SHALL carry the reason.

#### Scenario: Paid step needs the owner
- **WHEN** an apply session of `backend` for HO-20261031-p3uj ends with `BLOCKED: owner — go-ahead for a paid benchmark (up to $0.30)` and `backend` has not answered the handover
- **THEN** its outcome is `waiting_for_owner`, the owner receives an escalation handover naming the paid benchmark, and no further session is started for HO-20261031-p3uj until the owner answers

#### Scenario: Blocked line after the phase was completed
- **WHEN** an apply session marks its part `done` and its final message also ends with a `BLOCKED: owner — …` line
- **THEN** it is handled as a completed phase and nothing is escalated

#### Scenario: No line, no change
- **WHEN** an apply session ends normally without completing its phase and without a `BLOCKED:` line
- **THEN** the outcome and progress rules are the same as before this requirement

#### Scenario: Waiting for another team
- **WHEN** an apply session sends its own handover to `backend` with `ho new` and stops that part
- **THEN** it is not escalated; the item is held as described in "Waiting for a handover's result"

#### Scenario: Prompt tells the team to decide what its policy allows
- **WHEN** the dispatcher builds an apply or act prompt
- **THEN** the prompt tells the worker to take the decisions its team's instructions allow, record them, inform the owner with a handover that expects only an acknowledgement, and use `BLOCKED: owner` only for what those instructions reserve for the owner or, where they say nothing, for a decision, money, credentials or a production step

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

### Requirement: Limit check at the maximum duration
When a work session for a handover reaches its maximum duration and limit checks are on, the dispatcher SHALL NOT end it at once. It SHALL start a limit check consultation with the product team (the triage team, else the first product team) while the session keeps running. The check SHALL receive a digest of the session and return one verdict, `progressing` or `hung`, with a reason. It MUST NOT modify files, run `ho` write commands or contact other teams.

#### Scenario: Check instead of a cut
- **WHEN** a `app` apply session for HO-20261028-xaai reaches its maximum duration of 180 minutes
- **THEN** the session is not ended, a limit check consultation starts in the product team's repository, and the console shows that the product team is asked whether the session is hung

#### Scenario: Digest of the session
- **WHEN** a limit check starts
- **THEN** its prompt names the team, handover, phase and how long the session has run, and gives the session's recent status texts and tool calls, the tool running now and for how long, the time since the session's last event other than a heartbeat, and the session's progress so far (new commits, newly checked tasks, hub activity)

#### Scenario: Consultations are not checked
- **WHEN** a triage consultation, a limit check, a goal check or an idle ask reaches the maximum duration
- **THEN** it is ended as before, without a limit check

#### Scenario: Check changes nothing
- **WHEN** a limit check has ended
- **THEN** the product repository and the hub have no changes made by it

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

### Requirement: Sleep of the computer
The dispatcher SHALL notice when the computer has slept (a gap of at least one minute between real time and awake time), during a session, between sessions and in its waits. For each sleep it SHALL print one `!` console line with the local start, end and length of the sleep, saying the time is not counted, and write a `suspend` run-log event with the start, end and length. Waits for a moment in real time (a usage window's reset, a back-off) SHALL keep counting real time.

#### Scenario: Night's sleep reported
- **WHEN** the computer sleeps from 01:17 to 11:14 local time while a goal run is active
- **THEN** after the wake the console shows `!` "computer slept 01:17–11:14 (9 h 57 min) - not counted" and the run log has one `suspend` event

#### Scenario: Usage reset during a sleep
- **WHEN** the dispatcher waits for a usage window that resets at 04:20 and the computer sleeps from 01:00 to 07:00
- **THEN** after the wake the window counts as reset and the next step starts without further waiting

### Requirement: Session after a wake
When the computer wakes while a session runs, the dispatcher SHALL give the session the configured grace period of awake time. A session that produces a stream event in that period SHALL go on as before; otherwise the dispatcher SHALL end it with outcome `interrupted` (cause: sleep).

#### Scenario: Session recovers by itself
- **WHEN** the computer wakes during an `apply` session and the session produces a stream event within 3 minutes
- **THEN** the session is not ended and only the sleep line is printed

#### Scenario: Silent session after a wake
- **WHEN** the computer wakes during a `review` session that produces no stream event in the next 3 minutes
- **THEN** the session is ended with outcome `interrupted` and cause sleep

### Requirement: Recovery of an interrupted session
The dispatcher SHALL keep in its state a record of the running session (session ID, team, handover, phase, process) until its end has been processed. When `run` or `once` starts and finds such a record left by a dispatcher that is no longer running, it SHALL end any leftover process of that session, print a `!` line, write an `interrupted` run-log event and treat the session as `interrupted` (cause: dispatcher stopped). A second Ctrl+C makes the session `interrupted` with cause owner.

#### Scenario: Window closed during apply
- **WHEN** the owner closes the dispatcher's window during an `apply` session of HO-20261024-d6zr and starts `run` again the next morning
- **THEN** the dispatcher prints that the session was interrupted and logs an `interrupted` event, and the session counts as `interrupted`

#### Scenario: Owner ends a session with Ctrl+C
- **WHEN** the owner presses Ctrl+C twice during a `propose` session
- **THEN** the session's outcome is `interrupted` with cause owner, and the item's no-progress counter is unchanged

### Requirement: Resuming an interrupted session
The next session of an item whose session was `interrupted` SHALL resume that session in its own context, with a message naming the cause, saying the working tree may hold a partial edit, and asking to check the state and continue the phase. If the resume fails, a fresh session of the phase SHALL start. An interrupted step without a handover (goal check, idle ask, triage consultation) SHALL instead be run again when it is due.

#### Scenario: Resumed after a wake
- **WHEN** a `review` session of HO-20261024-d6zr was ended as `interrupted` after a sleep
- **THEN** the next step resumes it by its session ID with a message that the computer slept and to check the state and continue

#### Scenario: Resumed after a restart
- **WHEN** a new `run` found an interrupted `apply` session of HO-20261024-d6zr
- **THEN** its first session for that item resumes the `apply` session by its session ID instead of starting a fresh one

#### Scenario: Goal check interrupted
- **WHEN** the dispatcher stopped during a goal check and a goal run starts again
- **THEN** the record is dropped and the goal run starts with a fresh goal check

### Requirement: Auto-answering agreed stops
Every session the dispatcher starts SHALL carry hooks, supplied by the dispatcher without editing the team repository, that handle an `AskUserQuestion` call as follows:
- if the question matches an escalation keyword, refuse it with an instruction to stop and report, and record an escalation;
- otherwise, if the session's team is configured for product triage, refuse it with an instruction to end the turn because the question is being referred, and record the question with its options (see *Product triage of questions*);
- otherwise answer it with the configured default answer ("choose the best variant, record the assumption, continue").

The hooks SHALL also:
- when the agent ends its turn early with a plain-text question and its team is configured for product triage, let the session end and record the question; on any other early stop, send one "continue" instruction, never more than once in a row, so the session cannot loop;
- record a usage-limit failure so the dispatcher can see it;
- record that the hooks were loaded when the session starts.
Permission requests that the repository's allowlist and the permission mode do not settle MUST be denied rather than left waiting, and each denial recorded. Every automatic answer, refusal and denial MUST be written to the run log with the session, team and handover ID.

#### Scenario: Question from a triaged team referred
- **WHEN** the `app` agent asks "Which approach: A or B?" through `AskUserQuestion`
- **THEN** the hook refuses the call, records the question and its options, the session ends with outcome `question`, and the log shows the referral

#### Scenario: Product team's own question referred too
- **WHEN** the `product` agent, in a work session, asks "Which approach: A or B?" and no `triage.teams` limit is configured
- **THEN** the question is referred like any other team's question, to a separate consultation session of `product`

#### Scenario: Question from a non-triaged team answered directly
- **WHEN** the configuration limits triage to `app` and `backend`, and the `strategy` agent asks "Which approach: A or B?" through `AskUserQuestion`
- **THEN** the hook answers with the default answer, the agent continues, and the log shows the question and the answer

#### Scenario: Risky question escalated
- **WHEN** the agent asks whether to push to the remote repository
- **THEN** the hook refuses the question, the session ends `waiting_for_owner`, and the item is marked escalated

#### Scenario: Early stop nudged once
- **WHEN** the agent ends its turn early without a question
- **THEN** it receives one "continue" instruction; if it stops again immediately, the stop is allowed and the session ends

#### Scenario: Plain-text question referred
- **WHEN** the `backend` agent ends its turn with "Should the endpoint return 404 or an empty list?"
- **THEN** the stop is allowed, the question is recorded, and the session ends with outcome `question`

#### Scenario: Hooks not loaded
- **WHEN** a session ends and its hook-load record is missing
- **THEN** the dispatcher records the session as `error`, stops the loop and tells the owner that hooks did not fire

### Requirement: Product triage of questions
When a session ends with outcome `question`, the dispatcher SHALL refer the question directly — without creating a hub handover — to the configured product team (by default `product`) in a consultation session in that team's repository. Product triage is the fallback for every question the rules do not settle: by default the questions of every configured team are triaged, including the product team's own questions from its work sessions (answered in a separate consultation session); the configuration MAY limit triage to a list of teams. A question raised inside a consultation session is never triaged again; it gets the default answer. The consultation receives the question, its options, the asking team, the handover ID and the change name, and MUST NOT modify files, run `ho` write commands or contact other teams. The consultation prompt SHALL tell the product team to decide everything its instructions (its `CLAUDE.md`, the owner's goal) allow it to decide, to answer `owner` only for what those instructions reserve for the owner or, where they say nothing, for what a human must decide, and to put what the owner should know about a decision it takes into `note_for_owner`. It SHALL return one structured verdict:
- `technical` — the question cannot affect product success, user count or other key product figures; the team chooses the best variant;
- `product` — it can affect them; the verdict carries the chosen answer and the reason;
- `owner` — a human must decide; the verdict carries the reason.
The verdict MAY carry `note_for_owner` (see "Team decision notice"). The dispatcher SHALL then resume the asking team's session: with the default answer for `technical`, or with the product agent's answer and reason for `product`, instructing the agent to record it in the change as a product decision. For `owner`, a missing or malformed verdict, or a failed consultation, the item MUST be escalated. More than the configured number of triages for one handover (default 3) MUST also be escalated. Every verdict SHALL be written to the run log. The consultation runs only after the asking session has ended and before it is resumed, so the *one session at a time* rule holds; it is not a work phase and does not count as progress.

#### Scenario: Technical question
- **WHEN** `app` asked "Use a Map or a plain object for the cache?" and the product agent answers `technical`
- **THEN** the `app` session is resumed with "choose the best variant, record the assumption, continue", and the log shows the verdict

#### Scenario: Product-relevant question decided by product
- **WHEN** `app` asked "Show the onboarding tour on first install or only on request?" and the product agent answers `product` with "on first install, it drives activation"
- **THEN** the `app` session is resumed with that answer and reason, to be recorded in the change as a product decision

#### Scenario: Product asks for the owner
- **WHEN** the product agent answers `owner` because the question changes pricing
- **THEN** the item is escalated to the owner with the product agent's reason, and the asking session is not resumed

#### Scenario: Consultation fails
- **WHEN** the consultation session ends with an error or a verdict that does not fit the expected structure
- **THEN** the item is escalated and the asking session is not resumed

#### Scenario: Consultation changes nothing
- **WHEN** a consultation session has ended
- **THEN** the product repository and the hub have no changes made by it

#### Scenario: Consultation prompt names the team's policy
- **WHEN** the dispatcher builds a consultation prompt
- **THEN** it tells the product team to decide what its instructions allow, to answer `owner` only for what they reserve for the owner (or, where they say nothing, what a human must decide), and to put what the owner should know into `note_for_owner`

#### Scenario: Verdict without the note
- **WHEN** a consultation returns a verdict without `note_for_owner`
- **THEN** the verdict is valid and handled as before

### Requirement: Archive gate
The dispatcher SHALL keep a state record per handover: the team working on it, the OpenSpec change name (as reported by the agent in its final result or found in the repository), the current phase, the session IDs and the no-progress counter. It SHALL send a technical team the archive prompt only after the hub shows that the handover's author has closed it. It MUST NOT send an archive prompt for a handover that is reported done but not yet closed, or that was returned.

#### Scenario: Approved and archived
- **WHEN** `app` reported `done` on a handover and `product` closed it
- **THEN** the dispatcher selects an archive phase for `app` with the recorded change name

#### Scenario: Done but not reviewed
- **WHEN** a handover is reported done and the author has not acted yet
- **THEN** no archive prompt is sent; the author's review is the candidate instead

### Requirement: Asking for the next task when idle
When no candidate remains, and the option is enabled in the configuration, the dispatcher SHALL run one session in the product team asking it to choose the next work by its usual task-choice rule from its backlog, its technical debt and its own regular product tasks together. A regular task that is overdue or due within a day SHALL go first, in place of a usual task, and the product team SHALL do it itself in that session; the prompt SHALL point to the task-choice rule and schedule named in the team's own instructions without naming team files; otherwise it hands over the best backlog task that a technical team can do fully without a human (preferred) or partly, or answers that none should be started. The prompt SHALL ask for exactly one backlog item per handover, bundling items only when they are strongly linked or there is a strong reason to do them together, with that reason stated in the handover. When items are escalated or stalled, the prompt SHALL name each of them (handover, team, reason) and SHALL ask for ready work that does not depend on them, stating that a blocked item is no reason to leave other ready work waiting and that `none` is right only when every ready item waits for the owner or depends on a blocked item. The session SHALL return a structured verdict: `handed_over`, `did_regular` or `none`, a reason, and the backlog items that wait for an owner decision. After `did_regular` the dispatcher SHALL treat the idle ask as due again at once, unless the last three idle asks all returned `did_regular`; then it waits as after `none` and writes `idle_regular_limit` to the run log. When the verdict is `none` and items wait for the owner, the dispatcher SHALL send one escalation handover to the owner listing them, unless its last idle escalation listed the same items; then it SHALL send nothing and write `idle_escalation_skipped` to the run log. After an idle ask that returned `handed_over` or `none` the dispatcher MUST NOT ask again until the hub shows new activity or, when `idle_reask_minutes` is greater than zero, until that many minutes of awake time have passed since the end of the last session; with `idle_reask_minutes` set to 0 it asks again only on new hub activity. The console line of a `none` verdict SHALL give its reason and, when a re-ask is due by time, its local time.

#### Scenario: Backlog asked once
- **WHEN** the hub has had no candidates and no new activity since the last idle question, and fewer than `idle_reask_minutes` of awake time have passed
- **THEN** the dispatcher does not start another idle session

#### Scenario: Asked again after a quiet hour
- **WHEN** `idle_reask_minutes` is 60, an idle ask returned `none` at 09:26 and the hub has shown no new activity since
- **THEN** the dispatcher starts the next idle session at 10:26, and the console line of the 09:26 verdict named 10:26

#### Scenario: Re-ask by time switched off
- **WHEN** `idle_reask_minutes` is 0 and an idle ask returned `none`
- **THEN** no further idle session starts until the hub shows new activity

#### Scenario: Sleep does not count toward the re-ask
- **WHEN** `idle_reask_minutes` is 60, an idle ask returned `none` at 09:26 and the computer slept from 09:40 to 11:00
- **THEN** the next idle session starts at 11:46, not on wake

#### Scenario: Overdue regular task goes first
- **WHEN** no candidate remains, the product team's weekly report was due two days ago and a high-priority backlog item is ready
- **THEN** the idle prompt asks the team to choose from backlog, technical debt and regular tasks with overdue regular tasks first; the team writes the weekly report itself and returns `did_regular`, and the dispatcher runs the next idle ask right after it

#### Scenario: Regular task does not wait for hub activity
- **WHEN** an idle ask returned `did_regular` and the session changed only the product team's repository
- **THEN** the next idle ask starts in the next loop, without waiting for hub activity or `idle_reask_minutes`

#### Scenario: Regular tasks limited to three in a row
- **WHEN** three idle asks in a row returned `did_regular` and the hub has shown no new activity
- **THEN** the dispatcher writes `idle_regular_limit` to the run log and waits for hub activity or `idle_reask_minutes` of awake time before the next idle ask

#### Scenario: One item per handover
- **WHEN** the product team is asked for the next task
- **THEN** the prompt asks for one backlog item, and for a stated reason if it bundles several

#### Scenario: Blocked item named, other work asked for
- **WHEN** `HO-1` of `app` is escalated to the owner and no candidate remains
- **THEN** the idle prompt names `HO-1`, its team and reason, and asks for ready work that does not depend on it

#### Scenario: Nothing left without the owner
- **WHEN** the idle session returns `none` with two backlog items waiting for an owner decision
- **THEN** the owner receives one escalation handover from the product team naming both items and the reason

#### Scenario: Same owner items on a re-ask
- **WHEN** a re-asked idle session returns `none` with the same two backlog items waiting for the owner as the last idle escalation
- **THEN** no new escalation handover is sent, `idle_escalation_skipped` and the verdict are written to the run log

#### Scenario: Different owner items on a re-ask
- **WHEN** a re-asked idle session returns `none` with a third backlog item waiting for the owner besides the two of the last idle escalation
- **THEN** one new escalation handover naming all three items is sent

#### Scenario: Nothing to do at all
- **WHEN** the idle session returns `none` with no items waiting for the owner
- **THEN** no escalation handover is sent and the verdict is written to the run log

### Requirement: Escalation to the owner
When an item is escalated or stalled, the dispatcher SHALL leave the item's handover untouched, mark the item in its state, write the reason to the run log, print a notice to the console, send an escalation handover to the owner, and continue with other items. The escalation handover SHALL be sent from the team whose session escalated, to the hub team `owner`, expecting a response, closing automatically once answered, tagged `escalation` and referencing the item's handover; its body SHALL contain the question or reason, the phase, what the session reported so far and the session ID. The dispatcher SHALL send at most one open escalation handover per item. If sending fails, the item stays escalated and the failure is logged. The owner MUST also be able to list escalated items and clear one so it becomes selectable again, through dispatcher commands. For a handover waiting on a team the dispatcher does not run (see "Handover to a team the dispatcher does not run"), the escalated item SHALL be the sender's item that the handover references, if the dispatcher has a record of it that is not already escalated or stalled; the escalation is sent from the sending team, and its title and body SHALL state that the handover waits for the named team, which is not set up in the dispatcher, give the handover's ID and title, its sender, the waiting item, the configuration file, and the fix: add the team (`id`, `repo`, `kind`) and restart the dispatcher, or have the work done another way and answer. Without such an item, a standalone escalation handover with the same content SHALL be sent, referencing the waiting handover.

#### Scenario: Escalation reaches the owner through the hub
- **WHEN** a `app` session on `HO-1` ends with a question containing an escalation keyword
- **THEN** the owner's inbox shows a handover from `app`, tagged `escalation`, referencing `HO-1`, with the question and the session ID, and `HO-1` itself is unchanged

#### Scenario: Question in Russian reaches the owner
- **WHEN** a session ends with the question "Удалить старый файл тестов и заменить его новым?" and the default escalation keywords are used
- **THEN** the question is escalated to the owner, not referred to product triage

#### Scenario: Stalled item reaches the owner
- **WHEN** an item is marked stalled after the configured number of sessions without progress
- **THEN** the owner receives an escalation handover stating that it stalled and what the last session reported

#### Scenario: Owner clears an escalation
- **WHEN** the owner has answered the agent's question by hand and clears the item
- **THEN** the item is selectable again in the next loop

#### Scenario: Waiting item escalated for a missing team
- **WHEN** HO-20261025-ghyl from `app` to the unconfigured team `backend` references HO-20261025-vozr, an item of `app` the dispatcher works on
- **THEN** HO-20261025-vozr is marked escalated and skipped by selection, and the owner's escalation handover from `app` references HO-20261025-vozr and says that HO-20261025-ghyl "Build ST-35 now…" waits for team `backend`, which is not set up in the dispatcher, naming the configuration file and the `[[teams]]` entry to add

#### Scenario: Owner answers after adding the team
- **WHEN** the owner adds `backend` to the configuration, restarts the dispatcher and responds to that escalation handover
- **THEN** HO-20261025-vozr is cleared and its session is resumed with the answer, and HO-20261025-ghyl is selected as work of `backend`

#### Scenario: No waiting item
- **WHEN** a handover to an unconfigured team references no item of the sender that the dispatcher has a record of
- **THEN** a standalone escalation handover from the sender to the owner, referencing that handover, carries the same message, and no item is marked

### Requirement: Handover to a team the dispatcher does not run
Before every new step the dispatcher SHALL look for open handovers sent by a configured team to a hub team that is neither configured nor the owner, whose recipient's part is not finished (as defined in *Waiting for a handover's result*). For each such handover it SHALL escalate once, as soon as it is found, write an `unconfigured_team` run-log event and print a `!` console line naming the team. `dry-run` SHALL list such handovers.

#### Scenario: Forgotten team
- **WHEN** `app` has sent HO-20261025-ghyl to `backend`, which is a hub team but not in the configuration, and `backend` has not acted on it
- **THEN** before the next step the owner receives one escalation handover saying that HO-20261025-ghyl waits for team `backend`, which is not set up in the dispatcher, and the console shows a `!` line naming `backend`

#### Scenario: Escalated once
- **WHEN** the dispatcher has escalated HO-20261025-ghyl and the next loop iterations find it still open
- **THEN** no further escalation is sent for it

#### Scenario: Recipient finished
- **WHEN** the unconfigured team has finished its part (done or answered as expected, or declined; acknowledged for an `ack` handover), or the handover is closed
- **THEN** it is not escalated

#### Scenario: Part returned to the unconfigured team
- **WHEN** the sender returns the part of a handover to a team that is not configured
- **THEN** the handover waits again and is escalated once, as a new wait

#### Scenario: Configured team
- **WHEN** a handover is addressed to a team listed in the configuration, or to the owner
- **THEN** it is handled as before and not escalated by this rule

#### Scenario: Dry run
- **WHEN** the owner runs `dry-run` while HO-20261025-ghyl waits for the unconfigured team `backend`
- **THEN** the output names the handover, its sender and `backend`, and says it would be escalated; nothing is sent

### Requirement: Waiting for a handover's result
An item SHALL be held, not selected as work, while its team has an open handover that references it and has a recipient whose part is not finished. A part is finished as `ho` defines it per `expects`: `ack` acknowledged or declined, `done` done or declined, `response` answered or declined; `pending` and `returned` are never finished. Escalation handovers do not hold an item. The hold ends when every such handover is finished or closed. A return of the held item by its own sender SHALL release it for one session only: once a session of the item's team for that item has started after the latest return, the item is held again until the hold ends or the sender returns it again.

#### Scenario: Waiting for a configured team
- **WHEN** `app` has sent HO-20261025-ghyl, referencing its item HO-20261025-vozr, to the configured team `backend`, and `backend`'s part is pending
- **THEN** HO-20261025-vozr is not selected, and `backend`'s HO-20261025-ghyl is selected although HO-20261025-vozr has newer hub activity

#### Scenario: Result arrives
- **WHEN** `backend` marks HO-20261025-ghyl done
- **THEN** the sender's review of HO-20261025-ghyl is selected as before, and HO-20261025-vozr is selectable again

#### Scenario: Part returned to the recipient
- **WHEN** `app` returns its handover's part to `backend`
- **THEN** the referenced item is held again until `backend` finishes the part

#### Scenario: Acknowledgement is enough
- **WHEN** the waiting handover expects `ack` and the recipient has acknowledged it
- **THEN** the referenced item is not held

#### Scenario: Request to the owner
- **WHEN** a team has sent the owner a direct request (not an escalation handover) that references its item and the owner has not answered it
- **THEN** the item is held until the owner answers or the request is closed

#### Scenario: Item returned while it waits
- **WHEN** `product` returns HO-20261031-7q4q to `app` while `app`'s HO-20261031-3yyl to `backend`, referencing it, is still pending
- **THEN** one apply session of `app` for HO-20261031-7q4q is selected; after it ends without `ho done`, HO-20261031-7q4q is held again and `backend`'s HO-20261031-3yyl is selected next

#### Scenario: Returned again
- **WHEN** a held item had its one session after a return and its sender returns it once more
- **THEN** one more session is selected for it

#### Scenario: Item returned or cut short
- **WHEN** a held item was returned to its team by its own sender and no session for it has started since, or its last session was cut by a time limit or an interruption and is to be resumed
- **THEN** the item is selected as before

#### Scenario: No stall while waiting
- **WHEN** an item is held for several loop iterations
- **THEN** no session runs for it and its count of sessions without progress does not change

### Requirement: Reporting a held item
When an item starts being held the dispatcher SHALL print one console line naming the item, its team and each handover it waits for with the recipient and its state, and write a `waiting_for_handover` run-log event; when the hold ends it SHALL print one line and write `wait_ended`. `dry-run` SHALL list every held item with the handovers it waits for.

#### Scenario: Hold starts and ends
- **WHEN** HO-20261025-vozr starts waiting for HO-20261025-ghyl and later `backend` finishes it
- **THEN** the console shows one line saying HO-20261025-vozr waits for HO-20261025-ghyl (`backend`, pending), and later one line saying it is selectable again; further loop iterations print nothing more about it

#### Scenario: Dry run
- **WHEN** the owner runs `dry-run` while HO-20261025-vozr is held
- **THEN** the output names HO-20261025-vozr, HO-20261025-ghyl, `backend` and the part's state, and HO-20261025-vozr is not offered as the next step

### Requirement: Owner answer resumes the work
On every loop iteration the dispatcher SHALL check the escalation handovers it sent. When the owner has responded, it SHALL clear the item's escalated or stalled mark, record the answer in the run log and resume the escalated agent session with a message that quotes the question and the owner's answer, as it does after product triage. When the owner has declined, it SHALL clear the mark and resume the session with the refusal and its reason, telling the agent to continue without that part. If the session cannot be resumed, it SHALL start a fresh session of the item's phase whose prompt includes the owner's answer. Progress of the resumed (or fresh) session SHALL be counted from the start of the escalated session, so hub activity of the session that asked counts. An answer on an escalation that the owner already cleared by hand MUST be ignored.

#### Scenario: Owner says yes
- **WHEN** the owner runs `ho respond` on the escalation handover for `HO-1` with "yes, push to the feature branch"
- **THEN** in its next loop the dispatcher resumes the escalated `app` session with that answer, `HO-1` is no longer listed by `escalations`, and the escalation handover is closed

#### Scenario: Owner declines
- **WHEN** the owner runs `ho decline` on the escalation handover with a reason
- **THEN** the escalated session is resumed with the refusal and the reason

#### Scenario: Work before the question counts as progress
- **WHEN** the escalated session acknowledged `HO-1` before asking, and the session resumed with the owner's answer writes nothing to the hub
- **THEN** the item's count of sessions without progress does not grow

#### Scenario: Already cleared by hand
- **WHEN** the owner cleared `HO-1` with the `clear` command and later responds to its escalation handover
- **THEN** the dispatcher does not resume the session again

### Requirement: Observable and stoppable
The dispatcher SHALL append one JSON line per event to a run log: session start (team, repository, handover ID, phase, prompt, time) and end (time, exit code, outcome, session ID, auto-answers, denials, escalations). Between sessions it SHALL check for a `PAUSE` file (wait while it exists) and a `STOP` file (exit cleanly). On Ctrl+C during a session it SHALL let the owner choose between finishing the running session and ending it, and in both cases start no new session. It SHALL offer a dry-run mode that reads the hub and prints the candidates and the session it would start, without starting a session or writing to the hub, and a once mode that runs a single session and exits.

The console SHALL let the owner follow a run without the run log. When a session starts, the console SHALL show at most two lines with the local start time, the team, the phase and what the session works on: for a handover its ID and its title (shortened to fit one line), otherwise the kind of step (goal check, idle ask, triage consultation, resume with the owner's answer, resume after a time limit). When the session ends, the console SHALL show one line with the local time, the outcome and the duration. Problems SHALL be printed when they happen, each as one short line marked with a leading `!`: a session that ended with an error together with its cause (exit code, no result, time limit, hooks not loaded), a session without progress with the count against the stall limit, a question with where it went (product triage and its verdict, or the owner), a permission denial, a failed hub command, and a goal check or idle ask without a valid verdict; escalations, stalls and usage waits SHALL carry the same mark. Times on the console SHALL be local, as `HH:MM` with the date added when it is not today; the run log keeps UTC times. In run and once mode the dispatcher SHALL also append everything it writes to the console (standard output and standard error, including the goal report and error tracebacks) to a UTF-8 file `console.log` in the run directory, with one header line per start giving the local time, the process ID and the arguments, so that a session watching the run sees the same text as the owner's window; characters the console cannot show are replaced on the console only. In run and once mode on Windows the dispatcher SHALL turn off QuickEdit of its console window at start, so that a click in the window does not start a selection that blocks console output and with it the run; when standard input is not a console it SHALL leave the mode alone.

#### Scenario: Owner reviews a run
- **WHEN** the owner reads the run log after an unattended run
- **THEN** they see each session in order with its outcome and every automatic answer

#### Scenario: Pause between sessions
- **WHEN** the owner creates the `PAUSE` file while a session runs
- **THEN** the running session finishes and no new one starts until the file is removed

#### Scenario: Dry run against the real hub
- **WHEN** the owner runs the dispatcher in dry-run mode with the real hub configured
- **THEN** it prints the selected candidate, phase and prompt, starts no Claude Code session and changes nothing in the hub or any repository

#### Scenario: Owner sees what is being worked on
- **WHEN** the dispatcher starts an `apply` session of team `app` for handover `HO-20261024-sx7z` titled "The agent is told a slow page is loading, not failed (BL-049)" at 22:24 local time
- **THEN** the console shows at most two lines naming 22:24, `app`, `apply`, `HO-20261024-sx7z` and the title, shortened if it does not fit one line

#### Scenario: Owner sees how a session ended
- **WHEN** that session finishes after 36 minutes
- **THEN** the console shows one line with the local end time, the outcome `finished` and the duration 36 min

#### Scenario: A step without a handover
- **WHEN** a goal run starts a goal check of the product team
- **THEN** the start line names the local time, the product team and "goal check"

#### Scenario: A problem is visible on the console
- **WHEN** a session ends with outcome `error` because its time limit was reached, and the item made no progress
- **THEN** the console shows a `!` line with the error and the cause "time limit", and a `!` line saying the item made no progress, with the count against the stall limit

#### Scenario: A question goes to triage
- **WHEN** a session ends with a question and the product triage answers `technical`
- **THEN** the console shows a `!` line that the question went to product triage with verdict `technical`, and the start line of the resumed session

#### Scenario: The run log is unchanged
- **WHEN** a run prints the new console lines
- **THEN** the run log has the same events and fields as before, with UTC times

#### Scenario: Watching session sees the console
- **WHEN** the owner starts a goal run in a console window of its own and the run prints a start line, an end line and the goal report
- **THEN** `console.log` in the run directory has a header line for this start followed by the same lines in the same order, with `·` and `→` intact even if the window showed replacements

#### Scenario: A click in the window does not stop the run
- **WHEN** the owner starts a goal run in a console window of its own on Windows and clicks in the window while a session runs
- **THEN** no selection starts, and when the session ends its end line is printed and the next step starts without the owner pressing a key

### Requirement: Predicting the next steps
The dispatcher SHALL offer a read-only plan mode that prints, in order, the next steps it would take if every step succeeded, each with its team, phase, handover ID and title. The number of steps SHALL default to 5 and be settable by the owner. The mode SHALL start from the same hub and state snapshot as dry-run and pick every step with the rule of *Selecting the next work item*. It MUST NOT start a session or write to the hub, the state, the goal file, its goal record or the run log.

#### Scenario: Five steps ahead
- **WHEN** `backend` has a proposed change for handover `HO-20261026-rbkb` sent by `product`, `app` has a closed handover `HO-20261025-vozr` waiting for archive, and the owner asks for the plan of a goal run
- **THEN** the steps are: `backend` apply `HO-20261026-rbkb`, `product` review `HO-20261026-rbkb`, `backend` archive `HO-20261026-rbkb`, `app` archive `HO-20261025-vozr`, `product` goal check

#### Scenario: First step agrees with dry-run
- **WHEN** the owner runs dry-run and plan on the same hub and state
- **THEN** the first step of the plan is the session dry-run says it would start

#### Scenario: Nothing changes
- **WHEN** the owner runs plan mode
- **THEN** no Claude Code session starts, and the hub, the state file, `goal.json`, the run log and `console.log` are unchanged

### Requirement: Assumed outcome of a predicted step
After each predicted step the plan SHALL assume that step's successful outcome and pick the next step from the result: a propose makes the next step of that handover apply; an apply, or a product team's act, finishes the team's part as the handover's `expects` asks, and once every recipient's part is finished the author's review is a candidate. Each assumed outcome SHALL count as the newest hub activity at that point.

#### Scenario: Propose then apply
- **WHEN** the first step is `app` propose on a new handover
- **THEN** a later step is `app` apply on the same handover, ordered by the activity of the propose

#### Scenario: Review by a team the dispatcher does not run
- **WHEN** an apply finishes a handover whose author is not a configured team
- **THEN** no review step follows for it, and the plan says the handover waits for that author

#### Scenario: Item released from a hold
- **WHEN** an item is held while it waits for a handover to another configured team, and a predicted step finishes that team's part
- **THEN** the held item can be picked in a later step

#### Scenario: Several recipients
- **WHEN** a handover has two configured recipients and only one of them has a predicted apply
- **THEN** no review step follows for that handover until the other recipient's part is also finished

### Requirement: Assumed review and archive in a prediction
A predicted review SHALL be assumed to accept the work and close the handover; a technical handover reported done then becomes an archive candidate under *Archive gate*. A predicted archive SHALL end the handover, so it is not picked again.

#### Scenario: Apply, review, archive
- **WHEN** the first step is `app` apply on a handover sent by `product`, and nothing newer is in the hub
- **THEN** the next steps are `product` review and then `app` archive of that handover

#### Scenario: Archived handover not picked again
- **WHEN** a predicted step archives a handover
- **THEN** no later step names that handover

### Requirement: End of a prediction
The plan SHALL stop before the requested number of steps when the next outcome cannot be known from the hub and state: when nothing is left to pick it SHALL name a goal check of the product team in a goal run, or the idle state (with the idle ask when it is enabled) otherwise; a pending owner answer or guidance the product team has not yet received SHALL be the first step and end the prediction. It SHALL print why it stopped.

#### Scenario: Goal check ends the prediction
- **WHEN** in a goal-run plan no candidate is left after three steps
- **THEN** the fourth step is a goal check of the product team, the plan stops and says the next steps depend on its verdict

#### Scenario: Idle without a goal
- **WHEN** a plan without a goal file has no candidate left after two steps
- **THEN** the plan stops after two steps and says the dispatcher would be idle

#### Scenario: Carried guidance first
- **WHEN** the previous goal run on the same goal file ended with guidance the product team has not received
- **THEN** the only step is a goal check of the product team, and the plan says why it stopped

### Requirement: Limits and assumptions in a prediction
In a goal-run plan the dispatcher SHALL mark the step after which the session limit (`--max-sessions` or the configured default) would end the run. The plan SHALL end with a short list of what it assumes and cannot check: reviews accept the work, no question escalates or goes to triage, no permission is denied, checks pass, sessions send no new handovers, and goal checks hand over unknown work.

#### Scenario: Session limit inside the plan
- **WHEN** the owner asks for five steps of a goal run with `--max-sessions 3`
- **THEN** the plan shows five steps and marks that the run would end after step 3

#### Scenario: Assumptions printed
- **WHEN** the plan prints any steps
- **THEN** it ends with the list of assumptions it cannot check

### Requirement: Goal run
The owner SHALL be able to start a bounded run by giving the dispatcher a goal file: plain text written by the owner that states the scope of the work, what counts as done, and any guidelines for the run. During a goal run the dispatcher SHALL select and run work items exactly as in a normal run, and MUST NOT poll an idle hub indefinitely: the run ends under the conditions in "End of a goal run". The run SHALL have a maximum number of sessions and a maximum duration, with defaults in the configuration that the owner can override when starting the run. Without a goal file the dispatcher's behaviour is unchanged. A missing or empty goal file MUST be refused before any session starts.

#### Scenario: Start a goal run
- **WHEN** the owner starts the dispatcher with a goal file that names three backlog items
- **THEN** the dispatcher logs the start of a goal run with the goal text and its limits, and begins its loop

#### Scenario: Empty goal refused
- **WHEN** the goal file does not exist or contains only whitespace
- **THEN** the dispatcher exits with a non-zero code naming the file, and starts no session

#### Scenario: Normal run unchanged
- **WHEN** the owner starts the dispatcher without a goal file
- **THEN** it loops and polls as before and never runs a goal check

### Requirement: Goal check
In a goal run, whenever no candidate remains, the dispatcher SHALL run one session in the product team instead of the idle ask. The prompt SHALL give the goal text and ask the team to compare it with the hub, the backlog and the results so far, and then either hand over the next piece of work toward the goal through the hub (one backlog item per handover, bundling only strongly linked items with a stated reason) or report that the goal is complete or blocked. The prompt SHALL state that only this run's goal sets the order of work and that goals of earlier runs have ended. The session SHALL end with a structured verdict: `complete` (the goal is met), `continue` (work toward the goal was handed over or is still in progress), or `blocked` (what is left cannot proceed without the owner), with a reason, a list of what was done and a list of what is left or blocked. A missing or malformed verdict SHALL be treated as `continue` without new work.

#### Scenario: Next piece handed over
- **WHEN** no candidate remains and the goal names items not yet started
- **THEN** the product team hands over one of them, returns `continue`, and the dispatcher picks the new handover in its next loop

#### Scenario: Only this run's goal counts
- **WHEN** a goal run starts on a new goal file while the product team's backlog still records the order of an earlier goal
- **THEN** the goal check prompt states that only this run's goal sets the order of work and that earlier goals have ended

#### Scenario: Goal met
- **WHEN** every item in the goal has been closed by its author and the product team finds nothing left
- **THEN** the verdict is `complete` and the goal run ends

#### Scenario: Only owner-dependent work left
- **WHEN** the remaining items are escalated or need a decision only the owner can make
- **THEN** the verdict is `blocked`, lists those items, and the goal run ends

#### Scenario: Continue without new work
- **WHEN** two consecutive goal checks return `continue` (or no valid verdict) and neither produced a new handover or any other hub activity
- **THEN** the goal run ends with status `stalled`

### Requirement: No active goal in a run without a goal
In a run started without a goal, every session prompt of the product team (idle ask, review, act, triage consultation) SHALL state that no owner goal is active, that goals of earlier runs have ended and set no order of work, and that the next task is chosen by the team's usual task-choice rule. Prompts of a goal run and prompts of technical teams SHALL NOT carry this statement. A session resumed with a follow-up message (limit check, wrap-up, owner answer) SHALL NOT get it again.

#### Scenario: Idle ask without a goal
- **WHEN** the owner starts `run --until 17:00` without a goal and the product team is asked for the next task
- **THEN** the prompt says no owner goal is active, earlier goals have ended, and the team's usual task-choice rule applies

#### Scenario: Technical prompts untouched
- **WHEN** a technical team gets an apply prompt in a run without a goal
- **THEN** the prompt does not contain the no-goal statement

#### Scenario: Goal run keeps its goal
- **WHEN** the owner starts a run with a goal file
- **THEN** the product team's prompts carry the goal and not the no-goal statement

### Requirement: Ended goal removed from the backlog
In a run without a goal, the first product-team session after a goal run has ended SHALL also name that goal (goal file, end status, local end time) and ask the team to remove the order of work it set from the team's backlog files, keeping its unfinished parts as ordinary backlog items. The request SHALL be given once per ended goal run, identified by its goal file and start time; a session that ended `interrupted` or at a usage limit SHALL NOT count.

#### Scenario: First run after a goal run
- **WHEN** the goal run on `goal-release.md` ended with `limit` at 17:00 and the next run has no goal
- **THEN** the first product-team prompt of that run names the goal, `limit` and 17:00, and asks to remove its order of work from the backlog, keeping unfinished parts as ordinary items

#### Scenario: Note appended after the goal run
- **WHEN** the owner appends a note to the goal file of an ended goal run whose request was already given
- **THEN** the request is not given again

#### Scenario: Interrupted session does not count
- **WHEN** the first product-team session carrying the request ends `interrupted` because the computer slept
- **THEN** the next product-team prompt carries the request again

#### Scenario: Asked only once
- **WHEN** a product-team session of a run without a goal has finished after carrying the request for that ended goal
- **THEN** later product-team prompts, in this run or the next one without a goal, carry only the no-goal statement

### Requirement: Goal run ended without a report
In a run without a goal, a previous goal run whose record still shows it running SHALL be treated as ended: the ended-goal request SHALL name it as ended without a report, with no end time.

#### Scenario: Goal run ended without a report
- **WHEN** the previous goal run's record still shows it running and the next run has no goal
- **THEN** the first product-team prompt names that goal as ended without a report, gives no end time, and asks for the same cleanup

### Requirement: Owner guidance during a goal run
During a goal run the dispatcher SHALL include the current goal text, marked as the owner's goal and guidelines for this run, in every prompt it sends to the product team (act, review, triage consultation and goal check); prompts to technical teams are unchanged. The dispatcher SHALL re-read the goal file between sessions. When its content has changed since the last product session, the dispatcher SHALL log the change and make the next session a goal check — before any other candidate — whose prompt says the owner's guidance changed and asks the team to adjust work in flight where needed (comment on or return its handovers, send a follow-up handover) or to keep the guidance for later work. The owner SHALL be able to append a timestamped note to the goal file through a dispatcher command while the run is in progress.

#### Scenario: Guidelines reach the product team
- **WHEN** the goal file says "do not change the pricing page" and the product team reviews a finished handover
- **THEN** the review prompt contains the goal text including that guideline

#### Scenario: Guidance changed mid-run
- **WHEN** the owner appends a note while a technical team's session is running
- **THEN** after that session ends, the next session is a goal check that shows the updated goal and says the guidance changed

#### Scenario: Technical prompts untouched
- **WHEN** a technical team gets an apply prompt during a goal run
- **THEN** the prompt does not contain the goal text

### Requirement: Owner guidance carried to the next goal run
The dispatcher SHALL keep, across goal runs, the goal text the product team last received. When a goal run starts on the same goal file as the previous goal run and the file's content differs from that text, the first session SHALL be a goal check that says the owner's guidance changed, quotes the added text when the change is an addition, and comes before any other candidate. A run on another goal file, or the first run on a goal file, SHALL NOT count as changed guidance.

#### Scenario: Note added between runs
- **WHEN** a goal run ends with the session limit, the owner appends a note with the dispatcher command, and starts a new run on the same goal file while a technical item is waiting
- **THEN** the first session of the new run is a goal check whose prompt says the owner added the note and quotes it, and the technical item runs after it

#### Scenario: Note added late in a run
- **WHEN** the owner appends a note during a goal run and the run reaches its session limit before any product-team session
- **THEN** the next goal run on that file starts with a goal check that passes the note on

#### Scenario: Nothing new
- **WHEN** the previous run's product team received the current text and the file is unchanged
- **THEN** the new run starts with the normal selection and no goal check is added

#### Scenario: Other goal file
- **WHEN** the previous goal run used another goal file
- **THEN** the new run starts with the normal selection

#### Scenario: State from an older dispatcher
- **WHEN** the stored state of the previous run has no saved text but a hash of the goal file, and the current file is that text with a note appended
- **THEN** the first session is a goal check that quotes the appended note; when the seen text cannot be recovered but the stored hash differs or guidance was still pending, the goal check says the owner edited the goal text

### Requirement: End of a goal run
A goal run SHALL end when a goal check returns `complete` or `blocked`, when it is `stalled` as defined in "Goal check", when the `STOP` file is found, when the maximum number of sessions or the maximum duration (in awake time) is reached, when a usage budget of the run is reached, or when the end time of the run is reached (checked between sessions; a running session is not cut by these limits). At the end the dispatcher SHALL write a `goal_result` record to the run log (status `complete | blocked | stalled | stopped | limit`, reason, done and left lists from the last verdict, escalated and stalled items, number of sessions, duration in awake time, time slept), write the same as a Markdown report in the run directory together with one line per session of the run (local end time, team, phase or step kind, handover ID, outcome, duration), print it, and exit with a code that distinguishes `complete` from the other statuses. When the run had no goal check of its own, the done and left lists SHALL come from the last goal check of an earlier run on the same goal file, and the report SHALL say so and give that check's time. When the dispatcher runs in an interactive console it SHALL then wait for a key press with the message "Press any key to exit", unless the owner asked not to wait.

#### Scenario: Complete run
- **WHEN** a goal check returns `complete`
- **THEN** the run log has a `goal_result` with status `complete`, the report is printed and saved, the console shows "Press any key to exit", and the exit code is 0

#### Scenario: Session limit
- **WHEN** the run reaches its maximum number of sessions while candidates remain
- **THEN** no new session starts and the run ends with status `limit` and a non-zero exit code

#### Scenario: Usage budget reached
- **WHEN** a goal run with a seven-day budget of 80 % finishes a session with the seven-day window at 80 % while candidates remain
- **THEN** no new session starts and the run ends with status `limit`, a reason naming the seven-day window and the budget, and a non-zero exit code

#### Scenario: End time reached
- **WHEN** a goal run with an end time of 07:00 finishes a session at 07:05 while candidates remain
- **THEN** no new session starts and the run ends with status `limit`, a reason naming the end time, and a non-zero exit code

#### Scenario: Not interactive
- **WHEN** the dispatcher's standard input is not a console, or the owner passed the no-wait option
- **THEN** it exits right after printing the report, without waiting for a key

#### Scenario: Short run reports what it did
- **WHEN** a goal run with a maximum of one session runs one `apply` session and an earlier run on the same goal file ended with a goal check
- **THEN** the report lists that `apply` session with its handover and outcome, and shows done and left from the earlier goal check, marked as earlier with its time

#### Scenario: A night's sleep does not end the run
- **WHEN** a goal run with a maximum of 12 hours and no end time has worked 2 hours, the computer sleeps for 8 hours and wakes
- **THEN** the run goes on, and its report gives the awake duration and the time slept

### Requirement: Usage reading
The dispatcher SHALL read the plan's usage reports from every session's event stream and keep, per usage window (such as five-hour and seven-day), the latest used share, reset time and status. The latest reading MUST be stored in the dispatcher's state so it survives a restart. A window whose reset time has passed SHALL be treated as reset (nothing used).

#### Scenario: Reading recorded from a session
- **WHEN** a session's stream reports the five-hour window at 61 % used with reset at 15:30 and the seven-day window at 34 % used
- **THEN** after the session the dispatcher's state holds both windows with those shares and reset times

#### Scenario: Reading survives a restart
- **WHEN** the dispatcher is restarted after a session that reported the five-hour window at 92 %
- **THEN** the restarted dispatcher uses the stored 92 % reading for its next decision

#### Scenario: Window already reset
- **WHEN** the stored reading shows the five-hour window at 95 % but its reset time is in the past
- **THEN** the window counts as reset and does not hold new steps

#### Scenario: No usage reports
- **WHEN** no session has reported usage yet
- **THEN** the guard does not hold any step and behaviour is as before

### Requirement: Holding new steps near the usage limit
Before starting a new step (a work item session, a resume with an owner's answer, an idle ask) the dispatcher SHALL check the latest reading. If any window that has not reset is used at or above `usage_pause_percent` (default 90), it MUST NOT start the step and SHALL wait until that window's reset time plus a short margin; with several such windows it waits for the latest reset. A window that has a usage budget for the current run is not held by this check (see "Run budget overrides the configured threshold"). A session already running is never stopped by this check.

#### Scenario: Five-hour window almost used up
- **WHEN** the latest reading shows the five-hour window at 91 % used with reset in 40 minutes and a work item is waiting
- **THEN** no session starts, the dispatcher waits about 40 minutes and then starts the work item

#### Scenario: Below the threshold
- **WHEN** the latest reading shows the five-hour window at 89 % used
- **THEN** the next step starts as usual

#### Scenario: Running session not interrupted
- **WHEN** the five-hour window crosses 90 % while a session is running
- **THEN** the session runs to its end and only the following step is held

#### Scenario: Threshold configured
- **WHEN** the configuration sets `usage_pause_percent = 80` and the reading shows 82 %
- **THEN** the next step is held until the window resets

#### Scenario: One-shot run while held
- **WHEN** `run --once` is started while the guard holds new steps
- **THEN** no session starts and the dispatcher prints the window, its used share and reset time, and exits

#### Scenario: Budgeted window not held
- **WHEN** a run has a seven-day budget of 95 %, the threshold is 90 % and the seven-day window is at 91 %
- **THEN** the next step starts without waiting for the seven-day reset

### Requirement: Waiting for the known reset after a usage-limit hit
After a session ends with outcome `usage_limit`, the dispatcher SHALL start no new session until the reset time of the exhausted window reported in that session's stream (or the latest stored reading) plus a short margin. Only when no future reset time is known SHALL it fall back to the configured back-off (`usage_backoff_minutes`, doubling up to `usage_backoff_max_minutes`).

#### Scenario: Reset time known
- **WHEN** a session hits the limit and its stream reported the five-hour window with reset at 15:30
- **THEN** the dispatcher starts no session before 15:30 and starts the next step shortly after it

#### Scenario: Reset time unknown
- **WHEN** a session hits the limit and no usage report with a future reset time exists
- **THEN** the dispatcher waits the configured back-off as before

### Requirement: Reporting usage waits
The dispatcher SHALL print to the console, and write to the run log: when a running session's usage report first crosses the threshold (window, used share); when it starts holding new steps or waiting after a hit (window, used share, reset time in local time, wait length, cause `threshold` or `limit_hit`); and when it resumes. `dry-run` SHALL print the latest reading per window and whether the guard would hold the next step.

#### Scenario: Wait announced
- **WHEN** the guard holds new steps because the five-hour window is at 93 % with reset at 15:30
- **THEN** the console shows one line naming the five-hour window, 93 %, 15:30 local time and the remaining minutes, and the run log has a matching event with cause `threshold`

#### Scenario: Crossing announced during a session
- **WHEN** a running session's stream reports the five-hour window going from 89 % to 90 %
- **THEN** the console shows once for that session that the window is at 90 % and no new step will start after this session

#### Scenario: Resume announced
- **WHEN** the reset time of the held window passes
- **THEN** the console shows that the usage window has reset and work resumes, and the run log records the resume

#### Scenario: Dry run shows usage
- **WHEN** `dry-run` is run with a stored reading of five-hour 72 % and seven-day 40 %
- **THEN** it prints both windows with their shares and reset times and states that the next step would start

### Requirement: Usage budget of a run
When starting a run (plain, one-shot or goal run) the owner SHALL be able to give a usage budget per window: a used share from 1 to 100 % for the five-hour window, the seven-day window, or both. The budget SHALL apply to that run only and MUST NOT be stored for later runs. A budget outside 1–100 MUST be refused before any session starts.

#### Scenario: Weekly budget given
- **WHEN** the owner starts a run with a seven-day budget of 80 %
- **THEN** the run starts and prints that it will end once the seven-day window is used 80 % or more

#### Scenario: Budget not carried over
- **WHEN** a run with a seven-day budget of 80 % has ended and the owner starts a new run without a budget
- **THEN** the new run has no budget and uses only the configured threshold

#### Scenario: Invalid budget
- **WHEN** the owner gives a five-hour budget of 0 or 120
- **THEN** the dispatcher exits with a non-zero code and a message naming the option, and starts no session

### Requirement: Ending a run at its usage budget
Before every new step the dispatcher SHALL compare the latest reading of each budgeted window that has not reset with its budget. When a window is used at or above its budget, or reports a rejected status, the dispatcher MUST NOT start the step and SHALL end the run instead of waiting for the reset. A running session is never stopped by this check; a reset window counts as unused.

#### Scenario: Budget reached after a session
- **WHEN** a run has a seven-day budget of 80 %, a session ends with the seven-day window at 81 % and a work item is waiting
- **THEN** no new session starts and the run ends

#### Scenario: Budget already reached at start
- **WHEN** the stored reading shows the seven-day window at 82 %, not reset, and the owner starts a run with a seven-day budget of 80 %
- **THEN** the run ends before any session starts

#### Scenario: Below the budget
- **WHEN** a run has a seven-day budget of 80 % and the reading shows 78 %
- **THEN** the next step starts as usual

#### Scenario: Plain run ends with success
- **WHEN** a run without a goal ends because a budget is reached
- **THEN** the exit code is 0

### Requirement: Run budget overrides the configured threshold
For a window with a run budget, the configured `usage_pause_percent` (default 90, set in the configuration file) SHALL NOT hold or wait during that run; the budget decides instead, whether it is lower or higher. Windows without a budget SHALL keep the configured threshold. When a budget is higher than the configured threshold, the dispatcher SHALL print a warning at the start of the run and write it to the run log.

#### Scenario: Budget above the threshold
- **WHEN** the configured threshold is 90 %, the owner starts a run with a seven-day budget of 95 % and the seven-day window reaches 92 %
- **THEN** the start of the run printed a warning naming the seven-day window, 95 % and 90 %, and the next step starts

#### Scenario: Unbudgeted window still waits
- **WHEN** a run has only a seven-day budget of 80 % and the five-hour window reaches 91 % with the configured threshold at 90 %
- **THEN** the dispatcher holds new steps until the five-hour window resets, as without a budget, and the run goes on

#### Scenario: Budget below the threshold gives no warning
- **WHEN** the configured threshold is 90 % and the owner gives a seven-day budget of 80 %
- **THEN** no warning is printed

### Requirement: Reporting a usage budget
At the start of a run with a budget the dispatcher SHALL print and log each budget with the window's latest stored share. When the budget ends the run it SHALL print and log the window, its used share and the budget. When a running session's report first reaches a budget, the console SHALL say that no new step will start after this session. `dry-run` given a budget SHALL say whether the budget would end the run now.

#### Scenario: Start line
- **WHEN** a run starts with a seven-day budget of 80 % and the stored reading shows 77 %
- **THEN** the console shows the seven-day budget 80 % with the current 77 %, and the run log records the budget

#### Scenario: End line
- **WHEN** the run ends because the seven-day window is at 81 % with a budget of 80 %
- **THEN** the console and the run log name the seven-day window, 81 % and 80 %

#### Scenario: Dry run with a budget
- **WHEN** `dry-run` is given a seven-day budget of 75 % and the stored reading shows 77 %, not reset
- **THEN** it prints that the budget is reached and the run would end without starting a step

### Requirement: End time of a run
When starting a run (plain, one-shot or goal run) the owner SHALL be able to give an end time in local wall-clock time, either as a time of day (the next such moment: today, or tomorrow if it has passed) or as a full date and time. The end time SHALL apply to that run only and MUST NOT be stored for later runs. An unreadable end time, or a full date and time already in the past, MUST be refused before any session starts.

#### Scenario: Time of day later today
- **WHEN** at 22:10 the owner starts a run with an end time of `07:00`
- **THEN** the run ends at 07:00 the next morning

#### Scenario: Time of day still ahead today
- **WHEN** at 09:00 the owner starts a run with an end time of `17:30`
- **THEN** the run ends at 17:30 the same day

#### Scenario: Full date and time
- **WHEN** the owner starts a run with an end time of `2026-10-31 08:00`
- **THEN** the run ends at 08:00 on 31 October 2026

#### Scenario: Invalid or past end time
- **WHEN** the owner gives an end time of `25:00`, `tomorrow`, or a full date and time that has already passed
- **THEN** the dispatcher exits with a non-zero code and a message naming the option and the accepted forms, and starts no session

#### Scenario: End time not carried over
- **WHEN** a run with an end time has ended and the owner starts a new run without one
- **THEN** the new run has no end time

### Requirement: Ending a run at its end time
Before every new step the dispatcher SHALL compare the current time with the run's end time. When the end time is reached, it MUST NOT start the step and SHALL end the run. A running session is never stopped by this check. Time the computer sleeps SHALL count towards the end time. When the run also has a maximum duration or other limits, whichever is reached first ends the run.

#### Scenario: End time reached after a session
- **WHEN** a run has an end time of 07:00, a session ends at 07:12 and a work item is waiting
- **THEN** no new session starts and the run ends

#### Scenario: Session running at the end time
- **WHEN** a session is running at the end time
- **THEN** the session runs to its end and the run ends after it

#### Scenario: End time passed while the computer slept
- **WHEN** a run has an end time of 07:00 and the computer sleeps from 02:00 to 08:00
- **THEN** after waking the dispatcher starts no new step and the run ends

#### Scenario: Plain run ends with success
- **WHEN** a run without a goal ends because its end time is reached
- **THEN** the exit code is 0

#### Scenario: Earlier maximum duration wins
- **WHEN** a goal run has a maximum of 2 hours of awake time and an end time 5 hours ahead
- **THEN** the run ends with the maximum duration after 2 hours of awake time

### Requirement: Waits end at the end time
While a run with an end time waits without a session (polling an idle hub, a `PAUSE` file, a usage-limit wait or back-off, or a wait for a handover's result), the wait SHALL NOT go past the end time: the dispatcher SHALL end the run within a minute of the end time.

#### Scenario: Idle hub
- **WHEN** a plain run with an end time of 07:00 polls an idle hub every 2 minutes and the clock reaches 07:00 between two polls
- **THEN** the run ends at about 07:00 without waiting for the next poll

#### Scenario: Usage wait beyond the end time
- **WHEN** a run with an end time of 07:00 waits for a usage window that resets at 09:00
- **THEN** the run ends at about 07:00 and starts no session

### Requirement: Reporting an end time
At the start of a run with an end time the dispatcher SHALL print and log the end time as a local date and time with the time left. When the end time ends the run it SHALL print and log that the end time was reached. `dry-run` given an end time SHALL print when the run would end.

#### Scenario: Start line
- **WHEN** at 22:10 a run starts with an end time of `07:00`
- **THEN** the console shows that the run ends at 07:00 the next day, in 8 h 50 min, and the run log records the end time

#### Scenario: End line
- **WHEN** the run ends because its end time of 07:00 is reached
- **THEN** the console and the run log say that the end time 07:00 was reached

#### Scenario: Dry run with an end time
- **WHEN** `dry-run` is given an end time of `07:00` at 22:10
- **THEN** it prints that the run would end at 07:00 the next day, in 8 h 50 min

### Requirement: Keeping the computer awake
The owner SHALL be able to set, for a run (plain, one-shot or goal run), when the dispatcher keeps the computer from going to sleep on its own: never, for the whole run, until a moment, or every day within a time range. Without the option the configured default SHALL apply; with neither, the dispatcher SHALL keep the computer awake for the whole run. With `off` the dispatcher MUST NOT keep the computer awake. An unreadable value MUST be refused before any session starts. When the run has an end time and the keeping-awake moment is at or after that end time, the dispatcher SHALL keep the computer awake for the whole run, until the run ends, including a session that finishes after the end time; a moment before the end time SHALL keep its meaning.

#### Scenario: Default keeps awake for the whole run
- **WHEN** the owner starts a run without the option and the configuration does not set a default
- **THEN** the computer does not go to sleep on its own while the run lasts, also after the display turns off as the power plan says

#### Scenario: Default does not keep awake
- **WHEN** the configuration sets the default to `off` and the owner starts a run without the option
- **THEN** the dispatcher does not keep the computer awake, and Windows may put it to sleep as its power plan says

#### Scenario: Whole run
- **WHEN** the owner starts a run with keeping awake `on`
- **THEN** the computer does not go to sleep on its own while the run lasts

#### Scenario: Until a moment
- **WHEN** at 14:00 the owner starts a run with keeping awake until `23:00`
- **THEN** the computer is kept awake until 23:00 and may sleep after it, while the run goes on

#### Scenario: Moment forms as for the end time
- **WHEN** the owner gives `07:00` at 22:10, or `2026-11-01 08:00`
- **THEN** keeping awake lasts until 07:00 the next morning, or until 08:00 on 1 November 2026

#### Scenario: Moment equal to the end time
- **WHEN** the owner starts a run with end time `12:00` and keeping awake until `12:00`, and a session started at 11:25 is still running at 12:00
- **THEN** the computer is kept awake until that session finishes and the run ends, and no "Keep awake ended" line is printed at 12:00

#### Scenario: Moment after the end time
- **WHEN** the owner starts a run with end time `12:00` and keeping awake until `13:00`, and the last session finishes at 13:20
- **THEN** the computer is kept awake until the run ends at 13:20

#### Scenario: Moment before the end time
- **WHEN** the owner starts a run with end time `12:00` and keeping awake until `07:00`
- **THEN** the computer is kept awake until 07:00 and may sleep after it, while the run goes on until 12:00

#### Scenario: Option overrides the configured default
- **WHEN** the configuration sets keeping awake to `on` and the owner starts a run with `off`
- **THEN** the dispatcher does not keep the computer awake in that run

#### Scenario: Invalid value
- **WHEN** the owner gives `25:00`, `soon`, `23:00-23:00`, or a full date and time already in the past
- **THEN** the dispatcher exits with a non-zero code and a message naming the option and the accepted forms, and starts no session

### Requirement: Daily time range for keeping awake
With a time range the dispatcher SHALL keep the computer awake only while the local time is within the range, every day of the run, and SHALL start and stop doing so at the range's edges on its own. A range whose end is earlier than its start SHALL cross midnight. The dispatcher cannot wake a sleeping computer: a range that starts while the computer sleeps takes effect after the next wake.

#### Scenario: Day range over two days
- **WHEN** a run with the range `08:00-23:00` starts at 20:00 and lasts until 10:00 the next day
- **THEN** the computer is kept awake from 20:00 to 23:00, may sleep from 23:00 to 08:00, and is kept awake again from 08:00

#### Scenario: Range across midnight
- **WHEN** a run has the range `22:00-02:00` and the clock is 01:30
- **THEN** the computer is kept awake

#### Scenario: Range starts during a sleep
- **WHEN** a run has the range `08:00-23:00` and the computer sleeps from 23:30 to 09:15
- **THEN** keeping awake starts after the wake at 09:15

### Requirement: What keeping awake blocks
Keeping the computer awake SHALL block the sleep that the system starts on its own after a period of no user input, and the standby that turning off the screen starts (by the display timeout or with the project's screen-off script). Sleep the owner asks for, or that the power plan starts on closing the lid or on a low battery, MUST still happen. When the run ends in any way (end of the work, a limit, `STOP`, Ctrl+C, a closed window), keeping awake SHALL end with it.

#### Scenario: Owner puts the computer to sleep
- **WHEN** keeping awake is on and the owner chooses Sleep in the Start menu
- **THEN** the computer sleeps, and the dispatcher handles the sleep as without the option

#### Scenario: Owner turns the screen off for the night
- **WHEN** keeping awake is on and the owner runs the screen-off script on a computer with Modern Standby
- **THEN** the screen goes dark, the computer does not enter standby, the session goes on and no sleep line is printed

#### Scenario: Display timeout
- **WHEN** keeping awake is on and the display turns off after the power plan's display timeout
- **THEN** the computer does not enter standby and no sleep line is printed

#### Scenario: Screen off without keeping awake
- **WHEN** no run keeps the computer awake and the owner runs the screen-off script
- **THEN** the computer may enter standby as its power plan says

#### Scenario: Run ends
- **WHEN** a run with keeping awake `on` ends because its end time was reached
- **THEN** the computer may again sleep as its power plan says

#### Scenario: Window closed
- **WHEN** the owner closes the dispatcher's window while keeping awake is on
- **THEN** the computer is no longer kept awake

### Requirement: Keeping awake not available
On a system where the dispatcher cannot keep the computer awake, a run with keeping awake set by the option or the configuration SHALL print one `!` console line saying the computer is not kept awake, and SHALL otherwise go on as without the option. When keeping awake comes only from the default, such a run SHALL print no such line and SHALL go on as with `off`.

#### Scenario: Not Windows
- **WHEN** a run with keeping awake `on` given by the option or the configuration starts on a system without the Windows power API
- **THEN** the console shows one `!` line that the computer is not kept awake, and the run continues

#### Scenario: Not Windows with the default
- **WHEN** a run without the option, and without a configured default, starts on a system without the Windows power API
- **THEN** the console shows no keep-awake line and no `!` line about it, the run log has no keep-awake record, and the run continues

### Requirement: Reporting keeping awake
When keeping awake is set for a run, the start of the run SHALL print and log the setting with its moment or range, and the goal run's start record SHALL include it; this SHALL hold also when the setting comes from the default without the option or the configuration, and then the start line SHALL say that it is the default and how to let the computer sleep. When a moment at or after the end time is turned into the whole run, the start line and the log record SHALL say so and name the given moment. Each time keeping awake starts or stops during the run, the dispatcher SHALL print one console line with the local time and write a run-log event. `dry-run` SHALL accept the option and print the setting and whether the computer would be kept awake now.

#### Scenario: Start line without the option
- **WHEN** the owner starts a run without the option and the configuration does not set a default
- **THEN** the start shows "Keep awake: whole run (default; --keep-awake off lets the computer sleep)" and the run log has a record of the setting with the mode of the whole run

#### Scenario: Start line until a moment
- **WHEN** at 14:00 the owner starts a run with keeping awake until `23:00`
- **THEN** the start shows "Keep awake: until 23:00 today, in 9 h 00 min" and the run log has a record of the setting

#### Scenario: Start line for a moment covered by the end time
- **WHEN** the owner starts a run with end time `12:00` and keeping awake until `12:00`
- **THEN** the start shows "Keep awake: whole run (until 12:00 given, the run ends at 12:00)" and the run-log record has the mode of the whole run and the given moment

#### Scenario: Stop at the moment
- **WHEN** a run keeps the computer awake until 23:00 and the clock reaches 23:00
- **THEN** the console shows "23:00  Keep awake ended; the computer may sleep." and the run log has an event with the change

#### Scenario: Dry run without the option
- **WHEN** the owner runs `dry-run` without the option and the configuration does not set a default
- **THEN** the output says "Would keep awake: whole run (default; --keep-awake off lets the computer sleep)"

#### Scenario: Dry run with a range
- **WHEN** at 23:30 the owner runs `dry-run` with keeping awake `08:00-23:00`
- **THEN** the output names the range and says the computer would not be kept awake now, until 08:00

#### Scenario: Dry run with a moment covered by the end time
- **WHEN** the owner runs `dry-run` with end time `12:00` and keeping awake until `12:00`
- **THEN** the output says the computer would be kept awake for the whole run, naming the given moment

#### Scenario: Whole run set explicitly
- **WHEN** the owner starts a run with `--keep-awake` or the configuration sets `keep_awake = "on"`
- **THEN** the start shows "Keep awake: whole run" without the default note

#### Scenario: End time alone with the default
- **WHEN** the owner starts a run with end time `12:00`, without the option, and the configuration does not set a default
- **THEN** the start shows "Keep awake: whole run (default; --keep-awake off lets the computer sleep)", and the computer is kept awake until the run ends, including a session that finishes after 12:00

#### Scenario: Not set
- **WHEN** a run starts with keeping awake `off`
- **THEN** the start shows no keep-awake line and the run log has no keep-awake event

### Requirement: Hub command across a sleep
The time limit of a hub command SHALL count awake time only. When the computer sleeps while a hub command runs and the command has not finished at the wake, the dispatcher SHALL wait for it or run it once more, and SHALL NOT treat the sleep as the command's failure.

#### Scenario: Sleep during a hub read after a session
- **WHEN** the dispatcher reads a handover from the hub after a session, the computer sleeps for 5 minutes during the read, and the read finishes after the wake
- **THEN** the result of the read is used as without the sleep, the sleep line is printed, and the run goes on

#### Scenario: Command left hanging by the sleep
- **WHEN** a hub command is still running after the wake and does not finish within its limit counted in awake time, and the same command run once more finishes in time
- **THEN** the dispatcher uses the result of the second run, and no problem line is printed

### Requirement: Hub command that does not answer
A hub command that does not finish within its time limit (counted in awake time, after any repeat for a sleep) SHALL be handled as a failed hub command: the dispatcher prints a problem line naming the command and the limit and goes on as for other hub errors. The run MUST NOT end with a traceback because of it.

#### Scenario: Hub hangs
- **WHEN** `ho show` of a handover does not finish within its limit while the dispatcher checks a session's progress
- **THEN** the console shows a problem line "ho show <ID> failed: no answer within 120 s", the progress check goes on without the hub, and the run continues with its next step

### Requirement: Package and command name
The dispatcher SHALL be installed as the Python package `radark` and started with `python -m radark <command>` or the `radark` console script. Its hook scripts and the sandbox script SHALL be resolved inside the installed `radark` package. Texts the dispatcher writes that name a command (help, escalation hints, error hints, sandbox hints) SHALL name `python -m radark`.

#### Scenario: Starting by the new name
- **WHEN** the owner runs `python -m radark --help` or `radark --help` after installing the release
- **THEN** the dispatcher's help is printed, naming `python -m radark` as the program, and the exit code is 0

#### Scenario: Hooks come from the installed package
- **WHEN** the dispatcher starts a Claude Code session
- **THEN** every hook command it passes to the session points to a script inside the `radark` package's `hooks` directory

#### Scenario: Escalation hint names the new command
- **WHEN** the dispatcher writes an escalation that tells the owner how to clear the item `HO-1`
- **THEN** the hint names `python -m radark clear HO-1`

### Requirement: Deprecated alias harness
For at least one release after the rename, `python -m harness <arguments>` SHALL run the same dispatcher as `python -m radark <arguments>`, with the same standard output and the same exit code; it MAY add one deprecation line to standard error naming `python -m radark`. Importing `harness` or `harness.<module>` SHALL give the same module objects as `radark` and `radark.<module>`.

#### Scenario: Old command, same result
- **WHEN** the owner runs `python -m harness dry-run` and `python -m radark dry-run` with the same configuration
- **THEN** both print the same standard output and end with the same exit code, and the first also prints one deprecation line to standard error

#### Scenario: Old command with a bad argument
- **WHEN** the owner runs `python -m harness` with an unknown command
- **THEN** the exit code is the same as for `python -m radark` with that command

#### Scenario: Old import
- **WHEN** existing code runs `from harness.state import GoalRun`
- **THEN** the import succeeds and `GoalRun` is the same object as `radark.state.GoalRun`

### Requirement: Configuration and run file names unchanged by the rename
The package rename SHALL NOT change the default configuration file name `harness.toml`, the example file `harness.toml.example`, the default run directory `.harness/` or any configuration key.

#### Scenario: Run files keep their names
- **WHEN** the dispatcher is started as `python -m radark` in a directory with `harness.toml`
- **THEN** it reads `harness.toml` by default and keeps its run files in `.harness/` as before

### Requirement: Compatibility of ho
At the start of `run`, `once`, `dry-run` and `plan`, before any other hub command and before any session, the dispatcher SHALL run the configured `ho` with `--version --json` (without `HO_TEAM`, with a time limit) and read its package version and JSON contract version. The supported contract versions SHALL be one constant in the code. The commands that do not use the hub (`escalations`, `clear`, `keep`, `note`) do not run the check.

#### Scenario: Compatible ho
- **WHEN** the owner runs `dry-run` and `ho --version --json` reports version `0.2.0` and contract `1`, which the engine supports
- **THEN** the dry run continues as before

#### Scenario: Local commands skip the check
- **WHEN** the owner runs `escalations` with an incompatible `ho`
- **THEN** the command works as before

### Requirement: Stopping on an incompatible ho
When `ho` cannot be started, exits non-zero or gives no usable version answer (too old to have `--version`), does not answer in time, or reports an unsupported contract, the dispatcher MUST exit with code 2 before any session and without taking the run lock. It SHALL print one message naming the `ho` command, the found versions (or none), the needed contract version(s) and what to install.

#### Scenario: ho missing
- **WHEN** the configured `ho` command cannot be started
- **THEN** the dispatcher exits with code 2, names the `ho` command, says no `ho` was found and which contract it needs, and starts no session

#### Scenario: ho too old
- **WHEN** `ho --version --json` exits with a non-zero code or prints no version answer
- **THEN** the dispatcher exits with code 2, says this `ho` has no `--version` (older than the engine needs), names the needed contract and says to install a matching `radark-handover`, and starts no session

#### Scenario: Unsupported contract
- **WHEN** `ho --version --json` reports version `0.9.0` and contract `2`, and the engine supports only contract `1`
- **THEN** the dispatcher exits with code 2 with a message naming `ho 0.9.0`, contract `2` found, contract `1` needed, and to install a `radark-handover` with contract `1` or a `radark-factory` that supports contract `2`

#### Scenario: Check before the loop
- **WHEN** `run` is started with an incompatible `ho`
- **THEN** no other hub command runs, no run lock is taken, no `dispatcher_start` event is written and no Claude Code session is started

#### Scenario: Plan checks too
- **WHEN** the owner runs `plan` with an `ho` that reports an unsupported contract
- **THEN** it exits with code 2 with the same message and prints no prediction

### Requirement: Reporting the ho version
With a compatible `ho`, the start summary of `run`, `once` and `dry-run` SHALL include one line `ho: <version> (contract <n>)`, right after the Claude Code version.

#### Scenario: Start line
- **WHEN** `ho --version --json` reports version `0.2.0` and contract `1`
- **THEN** the start summary contains the line `ho: 0.2.0 (contract 1)`

### Requirement: Session temp directory
For every session it starts, new or resumed, the dispatcher SHALL create the directory `<run_dir>/tmp/<team>/` if missing, add it to the session's working directories, and set `TEMP`, `TMP` and `TMPDIR` in the session's environment to it. The dispatcher MUST NOT delete files in it. Team repositories are not changed.

#### Scenario: Temp directory of a session
- **WHEN** the dispatcher starts an apply session of `app`
- **THEN** `<run_dir>/tmp/app/` exists, the Claude Code command adds it as a working directory, and the session's `TEMP`, `TMP` and `TMPDIR` name it

#### Scenario: Resumed session
- **WHEN** the dispatcher resumes a session of `backend` with the owner's answer
- **THEN** the resumed session gets `<run_dir>/tmp/backend/` the same way

### Requirement: Discarding working-tree edits
The dispatcher's hooks SHALL allow, in a session's shell tool, a `git restore` (no `--source`) or `git checkout --` whose every path names an existing file inside the session's repository. A form with `.`, a directory, a wildcard, pathspec magic, a path outside the repository or `--source` SHALL be denied with a reason naming the allowed ways: name the files, or re-write each file. Any other command is not decided by this rule.

#### Scenario: Named file is restored
- **WHEN** a session in `app` runs `git restore -- src/cache.py` and `src/cache.py` is a file of the repository
- **THEN** the hook allows the command and no permission denial is recorded

#### Scenario: Whole tree is not restored
- **WHEN** a session runs `git checkout -- .`
- **THEN** the hook denies it and the reason tells the session to name the files (`git restore -- <file>`) or re-write each file

#### Scenario: Path outside the repository
- **WHEN** a session runs `git restore ../backend/src/api.py`
- **THEN** the hook denies it with the same reason

### Requirement: Stopping the session's own processes
The dispatcher's hooks SHALL allow, in a session's shell tool, stopping processes by ID (`Stop-Process -Id`, `taskkill /PID`, `kill <pid>`) when every ID is a process descended from the session's own Claude Code process. Stopping by name or image, or a process outside that tree, SHALL be denied with a reason naming the allowed ways: stop the processes the session started by ID, or run servers as background tasks and stop them with the task tool.

#### Scenario: Own test server is stopped
- **WHEN** a session started a test server as a child process with ID 4242 and runs `Stop-Process -Id 4242`
- **THEN** the hook allows the command

#### Scenario: Stop by name
- **WHEN** a session runs `Stop-Process -Name node`
- **THEN** the hook denies it and the reason tells the session to stop only the processes it started, by ID, or to stop a background task with the task tool

#### Scenario: Foreign process
- **WHEN** a session runs `taskkill /PID 1234 /F` and 1234 is not descended from the session's Claude Code process
- **THEN** the hook denies it with the same reason

### Requirement: Temporary files go to the session temp directory
The dispatcher's hooks SHALL deny a file write or edit tool call, and a shell command, that targets the system temporary directory (the session's original `TEMP` / `TMP`, or `/tmp`), with a reason naming the session temp directory as the place for temporary files. Paths in the session temp directory and in the repository are not decided by this rule.

#### Scenario: Script written to the system temp directory
- **WHEN** a session writes `check.ps1` to the system temporary directory
- **THEN** the hook denies it and the reason names `<run_dir>/tmp/<team>/` as the place for temporary files

#### Scenario: Script in the session temp directory
- **WHEN** a session writes `check.ps1` to `<run_dir>/tmp/<team>/`
- **THEN** the hook does not deny it

### Requirement: Nothing outward becomes allowed
The hooks' allow decisions SHALL cover only the narrow forms named in "Discarding working-tree edits" and "Stopping the session's own processes". A command that pushes, publishes, tags, deletes outside the session's repository and temp directory, or spends money MUST NOT be allowed by a hook; such commands, and every command the hook rules do not name, stay with the configured permission mode.

#### Scenario: Push stays with the permission mode
- **WHEN** a session runs `git push origin main`
- **THEN** the hooks make no decision and the permission mode decides as before

#### Scenario: Restore combined with another command
- **WHEN** a session runs `git restore -- src/cache.py; git push`
- **THEN** the hooks do not allow it, and the permission mode decides

### Requirement: Denial rule in the system prompt
Every session the dispatcher starts, new or resumed, SHALL carry in its system prompt, after the long-wait rule, the denial rule: when a command is denied, do the same another allowed way (temp files in the session temp directory; discard edits by naming the files or re-writing them; stop only its own processes by ID); if the phase cannot be completed without it, end with one line `BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <proposal>`.

#### Scenario: Rule names the temp directory
- **WHEN** the dispatcher starts a session of `app`
- **THEN** its system prompt carries the denial rule naming `<run_dir>/tmp/app/` and the `BLOCKED: owner — denied: …` line format

### Requirement: One clear question for a denial
A work session that ends with a permission denial and is escalated (it did not complete its phase, see "Permission denial in a completed phase") SHALL produce exactly one escalation handover for the item, in every work phase. Its reason SHALL keep `permission denied: <tool>`; its body SHALL list each denied tool with its shortened command or input; its question SHALL be the session's last `BLOCKED: owner — …` text when the session gave one, otherwise a question naming the denied commands.

#### Scenario: Denied command with the team's suggestion
- **WHEN** an apply session of `backend` has `Remove-Item C:\cache -Recurse` denied, does not mark its part `done`, and ends with `BLOCKED: owner — denied: Remove-Item C:\cache -Recurse; needed for: a clean benchmark; suggestion: allow it once or run the benchmark without a clean cache`
- **THEN** the owner receives one escalation handover whose body names the denied PowerShell command and whose question is that text

#### Scenario: Denial without a blocked line
- **WHEN** a propose session has one Bash denial, no change is created, and its final message has no `BLOCKED:` line
- **THEN** the owner receives one escalation handover whose question names the denied Bash command and asks how the team should go on

#### Scenario: Several denials in one session
- **WHEN** an apply session has three denials and ends without completing its phase
- **THEN** exactly one escalation handover is sent, listing all three

### Requirement: Team decision notice
When a `technical` or `product` triage verdict carries a non-empty `note_for_owner`, the dispatcher SHALL send the owner one handover from the triage team, expecting an acknowledgement, auto-closing, tagged `team-decision`, referencing no handover, naming the asking team, the item, the question, the decision and the note. It MUST NOT hold or escalate any item; the asking session is resumed as for the verdict. A failed send is logged and shown only.

#### Scenario: Failed notice
- **WHEN** sending the team-decision handover fails
- **THEN** the run log and the console show the failure, and the asking session is still resumed with the verdict

#### Scenario: Product decides and informs the owner
- **WHEN** triage answers `product` with "use the recommended cache option" and a `note_for_owner`
- **THEN** the asking session is resumed with that answer, and the owner's inbox shows a `team-decision` handover from `product` naming the question, the decision and the note, expecting only an acknowledgement

#### Scenario: No note, no notice
- **WHEN** triage answers `technical` with an empty `note_for_owner`
- **THEN** no handover is sent to the owner, as before

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
With `parallel_sessions` above 1, the start check of `ho` (see *Compatibility of ho*) for `run`, `once` and `dry-run` SHALL also require the installed `ho` to report that it serialises hub writes and `sync` (`"hub-lock"` in the `features` of `ho --version --json`). When it does not, the dispatcher MUST stop as *Stopping on an incompatible ho* says, with a message that names the `ho` version and says to install a radark-handover with the hub lock or to set `parallel_sessions = 1`. Otherwise the check is as before.

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

### Requirement: Machine directory
The dispatcher SHALL keep everything it shares with other dispatcher instances of the same OS user on one computer in one machine directory: `RADARK_MACHINE_DIR` when set, otherwise `%LOCALAPPDATA%\radark\machine` on Windows and `$XDG_STATE_HOME/radark/machine` (or `~/.local/state/radark/machine`) elsewhere. It SHALL create the directory when missing. A machine directory that cannot be created or written, or that lies inside the run directory or a configured team repository, MUST be refused by `run`, `once` and `dry-run` with exit code 2 and a message naming the directory, before any session starts. Nothing in the machine directory SHALL depend on the hub or the `ho` install, so instances with different hubs share it.

#### Scenario: Override for a sandbox
- **WHEN** `RADARK_MACHINE_DIR` points to a temporary directory and two instances are started with it
- **THEN** both use that directory and nothing is written to the default machine directory

#### Scenario: Machine directory inside a repository
- **WHEN** `RADARK_MACHINE_DIR` points inside the `app` repository
- **THEN** `run` exits with code 2 naming the directory and starts no session

### Requirement: Machine limits
The owner SHALL set the machine limits once, in `machine.toml` in the machine directory: `[machine] sessions` (concurrent work sessions of all instances, default 2) and `test_runs` (concurrent full test runs through the test slot, default 1). A missing file or key SHALL use the default. A value that is not an integer of at least 1 MUST be refused by `run`, `once` and `dry-run` with exit code 2 and a message naming the file and key. A change of the file while instances run SHALL apply at their next slot request; an invalid value read later SHALL keep the last valid limits and be reported once.

#### Scenario: Defaults without a file
- **WHEN** the machine directory has no `machine.toml`
- **THEN** the limits are 2 sessions and 1 test run

#### Scenario: Invalid limit
- **WHEN** `machine.toml` sets `sessions = 0`
- **THEN** `run` exits with code 2 naming `machine.toml` and `sessions`

### Requirement: Shared usage across instances
Every usage reading (window, used share, reset time, status) from a session of any instance SHALL also be written to one machine-wide usage record, under a short OS lock, as soon as it is read from the stream. Every decision on usage — holding new steps near the limit, the run budget check and the reports of `dry-run` and `status` — SHALL use, per window, the newest reading of the machine record and the instance's own stored reading. Run budgets (`--budget-5h`, `--budget-7d`) stay per run and are measured against these readings.

#### Scenario: Other instance's reading holds new starts
- **WHEN** a session of `pipeline-a` reports the five-hour window at 92 % and `pipeline-b` (threshold 90 %) has a work item to start
- **THEN** `pipeline-b` starts no session and waits for the five-hour reset as for its own reading

#### Scenario: Budget against the shared reading
- **WHEN** `pipeline-b` runs with `--budget-5h 70` and a session of `pipeline-a` reports the five-hour window at 72 %
- **THEN** `pipeline-b` ends at its budget as if its own session had reported 72 %

#### Scenario: Single instance
- **WHEN** one instance runs alone
- **THEN** its usage decisions are the same as before, and its readings are also in the machine record

### Requirement: Usage-limit hit holds all instances
When a session of any instance ends with outcome `usage_limit`, the instance SHALL write the hold (the exhausted window's reset time plus the margin, or the back-off end when no reset is known) to the machine usage record. Every instance SHALL start no new step until the latest such hold has passed, and its wait line SHALL say when the hold was seen by another pipeline. Running sessions are not stopped.

#### Scenario: Limit hit in another pipeline
- **WHEN** a session of `pipeline-a` hits the usage limit with the five-hour reset at 15:30 and `pipeline-b` has a candidate
- **THEN** `pipeline-b` starts nothing before 15:30, prints that the limit was hit in another pipeline, and starts after the reset

### Requirement: Machine session limit
Before starting a work session, an owner-answer resume or a whole-hub step (idle ask, goal check), an instance SHALL take a free machine session slot in addition to its own place under `parallel_sessions`, and SHALL hold it until the session or step has been processed. Limit checks and triage consultations do not take a slot. When no slot is free, the instance MUST NOT start the step, fail or count the wait as a stall: it SHALL print one console line naming the reason (for example `machine limit: 2 sessions running in other pipelines`), write a `machine_wait` run-log event, wait (checking at least every 30 seconds and still honouring STOP, PAUSE, `--until` and Ctrl+C) and start when a slot frees, printing one line and writing `machine_wait_end`.

#### Scenario: Second pipeline waits
- **WHEN** the machine limit is 2, `pipeline-a` runs 2 sessions and `pipeline-b` has a candidate
- **THEN** `pipeline-b` prints `machine limit: 2 sessions running in other pipelines`, starts nothing and starts its candidate after one of `pipeline-a`'s sessions has ended

#### Scenario: Limit caps the sum
- **WHEN** the machine limit is 2, `pipeline-a` has `parallel_sessions = 2` and runs 1 session, and `pipeline-b` runs 1 session
- **THEN** `pipeline-a` starts no second session until one of the two ends

#### Scenario: Single instance with defaults
- **WHEN** one instance with `parallel_sessions = 1` runs alone with the default machine limit
- **THEN** it never waits for a machine slot and behaves as before

### Requirement: Machine test-run limit
The dispatcher SHALL provide a command `python -m radark test-slot [--] <command> [args...]` that waits for a free machine test-run slot, runs the command with the slot held, releases the slot when the command ends and exits with the command's exit code. While it waits it SHALL print a line at the start and at least every minute naming how many test runs are in progress. Inside a command run through it (`HARNESS_TEST_SLOT_HELD` set) a nested `test-slot` SHALL run its command at once. Without a machine directory override it SHALL use the default machine directory, so it also works outside a pipeline. Every session SHALL get `RADARK_MACHINE_DIR`, `HARNESS_TEST_SLOT` (the path of a `radark-test-slot` wrapper in the run directory that calls this command with the dispatcher's Python) and that wrapper's directory at the front of `PATH`.

#### Scenario: Second test run waits
- **WHEN** the test-run limit is 1 and a session of `pipeline-a` runs `radark-test-slot python -m pytest`
- **THEN** a `radark-test-slot` call of a session of `pipeline-b` waits, printing that 1 test run is in progress, and runs its command after the first has ended

#### Scenario: Exit code passed through
- **WHEN** the command run through `test-slot` exits with code 1
- **THEN** `test-slot` exits with code 1 and the slot is free

### Requirement: Test-slot note in the work prompt
Work prompts (phase prompts and resumes) SHALL carry a note telling the agent to run a full test suite through `radark-test-slot <command>` and that it may wait for another session's test run, when more than one session can run on the computer at that moment: `parallel_sessions` is above 1 or another instance is running when the session starts. Otherwise the prompt is as before.

#### Scenario: Another pipeline running
- **WHEN** `pipeline-b` with `parallel_sessions = 1` starts a session while `pipeline-a` is running
- **THEN** the prompt carries the test-slot note

#### Scenario: Alone with one session
- **WHEN** one instance with `parallel_sessions = 1` runs alone
- **THEN** the prompt has no test-slot note

### Requirement: One repository, one instance
A team repository (resolved path, compared case-insensitively on Windows) SHALL belong to at most one running instance. `run` and `once` SHALL claim every configured team repository after taking the run lock and before any session; when a repository is already claimed by a running instance, the instance MUST release what it claimed, start no session and exit with code 2 and a message naming the repository and the other instance's configuration path. `dry-run` and `status` SHALL NOT claim repositories and SHALL show such a conflict.

#### Scenario: Shared repository refused
- **WHEN** `pipeline-a` is running with the `app` repository and `pipeline-b`'s configuration also lists it
- **THEN** `pipeline-b run` exits with code 2 naming the `app` repository path and `pipeline-a`'s configuration path

#### Scenario: Dry run shows the conflict
- **WHEN** the owner runs `pipeline-b dry-run` in the same situation
- **THEN** the output names the conflict and the session it would start, and the exit code is as before

#### Scenario: Same path in another spelling
- **WHEN** on Windows `pipeline-b` lists the repository with different letter case or through a relative path
- **THEN** it is refused as the same repository

### Requirement: Machine layer released on crash
Every claim in the machine directory (instance, repository, session slot, test-run slot, usage record update) SHALL be an OS file lock held by the claiming process, so the OS releases it when the process ends in any way. A record next to a lock (PID, process start time, configuration path, sessions running) SHALL be treated as stale when its lock is free, ignored for every decision and may be removed by any instance or by `status`. A killed instance MUST never block another one.

#### Scenario: Killed instance
- **WHEN** `pipeline-a` is killed while it runs a session and its instance record is left behind
- **THEN** `pipeline-b` can claim `pipeline-a`'s repositories and slots at once, and `status` does not list `pipeline-a`

### Requirement: Keeping awake with several instances
Each instance SHALL keep its own keep-awake request as before; the dispatcher SHALL rely on Windows combining the requests of all processes, so the computer stays awake while any instance wants it awake, and one instance ending or leaving its keep-awake range does not end another instance's request. Each instance's sleep watch and wake grace SHALL work as before with other instances running.

#### Scenario: One instance ends
- **WHEN** `pipeline-a` and `pipeline-b` both keep the computer awake and `pipeline-a` ends
- **THEN** the computer stays awake while `pipeline-b` runs

### Requirement: Machine status
The dispatcher SHALL provide a read-only command `status` that is not blocked by the run lock or by other instances and prints: the machine directory, the machine limits (or the error in `machine.toml`), every other running instance (configuration path, PID, start time, sessions running), the session and test-run slots in use, the shared usage reading per window, and the repository conflicts of the given configuration. `run` and `once` SHALL print at start one line with the machine limits and one line per other running instance; `dry-run` SHALL print the same lines and whether a machine slot is free for the session it would start. Another instance's details MUST be limited to its configuration path, PID, start time and number of running sessions.

#### Scenario: Status with another instance
- **WHEN** `pipeline-a` runs one session and the owner runs `pipeline-b status`
- **THEN** the output lists `pipeline-a`'s configuration path with 1 session running, the limits 2 sessions and 1 test run, and the shared usage reading

#### Scenario: Start line
- **WHEN** `pipeline-b run` starts while `pipeline-a` runs
- **THEN** a start line names `pipeline-a`'s configuration path and its running sessions
