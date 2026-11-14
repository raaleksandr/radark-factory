## MODIFIED Requirements

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

## ADDED Requirements

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
