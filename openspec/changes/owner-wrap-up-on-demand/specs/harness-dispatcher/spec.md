## ADDED Requirements

### Requirement: Wrap-up on demand
While a run is running, the owner SHALL be able to ask it to wrap up now, without an end time fixed at its start. Once the dispatcher sees the request it SHALL start no new step, end a running wait at once, ask every running work session of the run to wrap up, and end the run after the last running session has ended, with exit code 0 (a goal run ends as `stopped`). `STOP`, `PAUSE`, `--until` and `--until-strict` SHALL keep their behaviour.

#### Scenario: Request while idle
- **WHEN** the owner asks a run to wrap up while it waits for work and no session runs
- **THEN** the wait ends, no session starts and the run ends with exit code 0

#### Scenario: Request with two sessions running
- **WHEN** a run with parallel sessions has apply sessions of teams `app` and `backend` running when the owner asks it to wrap up
- **THEN** both sessions are asked to wrap up, no new session starts, and the run ends after both have ended

### Requirement: Requesting a wrap-up on demand
The owner SHALL request the wrap-up with the command `wrap-up` for a configuration, optionally with `--within MIN` (a number above 0), or by creating a `WRAP_UP` file in the run directory (a request without a limit). The command SHALL write that file and say what happens. A request already pending SHALL be kept and the command SHALL say when it was made.

#### Scenario: Command while a run runs
- **WHEN** the owner runs `wrap-up --within 30` while a dispatcher of that configuration runs
- **THEN** a `WRAP_UP` file with the request time and 30 minutes is written, the command prints that running sessions finish their current tool call, save their work and stop, and exits with code 0

#### Scenario: Request already pending
- **WHEN** the owner runs `wrap-up` while an earlier request of 14:05 is pending
- **THEN** the file is left as it is and the command says a wrap-up was already requested at 14:05

#### Scenario: Invalid limit
- **WHEN** the owner runs `wrap-up --within 0`
- **THEN** the command is refused with a non-zero exit code and no file is written

### Requirement: Wrap-up request without a running run
Without a running dispatcher for the configuration the `wrap-up` command MUST NOT write the file and SHALL exit with a non-zero code and a message that no run is running. The run SHALL remove the `WRAP_UP` file when it ends after a wrap-up; a `WRAP_UP` file found when a run starts SHALL be removed with a console note and MUST NOT end that run.

#### Scenario: Command without a running run
- **WHEN** the owner runs `wrap-up` and no dispatcher of that configuration runs
- **THEN** no file is written and the command exits with a non-zero code and a message that no run is running

#### Scenario: Stale file at start
- **WHEN** a run starts and a `WRAP_UP` file from an earlier run exists
- **THEN** the file is removed, the console notes it, and the run goes on as usual

### Requirement: Delivering a wrap-up on demand between tool calls
A running work session MUST NOT be stopped by the request while a tool call runs. The request SHALL reach the session in its own context, once per session, right after the tool call it is in has returned, or at the end of its turn instead of the usual "continue" nudge when no tool call comes first. After the delivery the session SHALL be allowed to end its turn without a nudge. Sessions that are not work sessions, and sessions already in a wrap-up, SHALL get no request.

#### Scenario: Request during a long tool call
- **WHEN** the owner asks for the wrap-up while an apply session for HO-20261120-ab12 runs a long test command
- **THEN** the command runs to its end and is not killed, the wrap-up text is added to the session's context right after it, and the session ends its turn without a nudge

#### Scenario: Request while the session writes its answer
- **WHEN** the session makes no further tool call after the request and ends its turn
- **THEN** the wrap-up text is given at the end of the turn instead of the nudge, and the session ends after its wrap-up

### Requirement: Wrap-up on demand text
The delivered text SHALL name the handover and the minutes left, and ask the session to start no new work, to wait for a command it started (also in the background) and use its result, and to commit what works. For apply it SHALL ask to check off finished tasks and write the open ones under `Left for a later run` in `tasks.md`; for other phases to say what is left. It SHALL ask not to report the handover done unless the phase is complete.

#### Scenario: Wrap-up text for apply
- **WHEN** the wrap-up text is delivered to an apply session for HO-20261120-ab12
- **THEN** it names the handover and the minutes left, asks to start no new work, wait for running commands, commit what works, check off finished tasks, write the open ones under `Left for a later run` in `tasks.md` and not report the handover done unless the phase is complete

### Requirement: Safety limits of a wrap-up on demand
After the request no limit check SHALL start and no extension SHALL be given. A session that received the request SHALL be stopped `wrap_up_minutes` after the delivery if it still runs (at once with `wrap_up_minutes = 0`). The inactivity limit and the maximum duration SHALL keep applying.

#### Scenario: Grace after delivery
- **WHEN** a session received the wrap-up text and still runs 15 minutes later with `wrap_up_minutes = 15`
- **THEN** it is stopped with the cause `owner_wrap_up`

#### Scenario: No extension after the request
- **WHEN** an apply session's limit-check deadline falls after the request and the session has not received the text
- **THEN** no limit check runs, and the session is stopped and resumed with the wrap-up prompt

### Requirement: Limit for reaching the sessions
With `--within MIN`, a work session that has not received the request MIN minutes after it SHALL be stopped and resumed in the same step with the wrap-up prompt, limited to `wrap_up_minutes` (only stopped with `wrap_up_minutes = 0`); any other running session SHALL be stopped. A work session that reaches its maximum duration after the request without having received it SHALL be handled the same way.

#### Scenario: Limit for a session not reached
- **WHEN** the owner requested `wrap-up --within 30` and a session's tool call is still running 30 minutes later
- **THEN** the session is stopped and resumed with the wrap-up prompt for at most `wrap_up_minutes`, then the run ends

### Requirement: Outcome of a session wrapped up on demand
A work session ended by a wrap-up on demand SHALL keep its normal outcome when it ended normally with its phase complete, or ended in a usage limit or an owner wait. Otherwise the step SHALL be `interrupted` with the cause `owner_wrap_up`, MUST NOT count as an error or as no progress, and a question from it SHALL NOT be triaged. The item's next session SHALL resume the same session with a message that the owner asked the previous run to wrap up.

#### Scenario: Next run resumes the item
- **WHEN** an apply session wrapped up on demand ended without completing its phase and a new run starts
- **THEN** the step's outcome was `interrupted` with the cause `owner_wrap_up`, and the new run's session for that item resumes the same session with a message that the owner asked the previous run to wrap up

#### Scenario: Phase completed during the wrap-up
- **WHEN** a session asked to wrap up completes its phase and reports the handover done
- **THEN** its outcome stays `finished`

### Requirement: Reporting a wrap-up on demand
The console, and so `console.log`, SHALL show when the request is seen with the sessions asked, each delivery, each session's end with the cause `owner wrap-up`, and the run's end. The run log SHALL get the events `owner_wrap_up_requested`, `owner_wrap_up_delivered`, `owner_wrap_up_stop` (with its reason) and `owner_wrap_up_done`. The `status` command SHALL show a pending wrap-up with its request time and limit.

#### Scenario: Lines and events of a wrap-up
- **WHEN** the owner asks a run with one apply session to wrap up and the session ends after its wrap-up
- **THEN** the console shows the request with that session, the delivery, the session's end with `owner wrap-up` and the run's end, and the run log has `owner_wrap_up_requested`, `owner_wrap_up_delivered` and `owner_wrap_up_done`

#### Scenario: Status while pending
- **WHEN** the owner runs `status` while a requested wrap-up is pending
- **THEN** it shows that a wrap-up was requested at its time, with its limit if any, and that the run ends after the running sessions
