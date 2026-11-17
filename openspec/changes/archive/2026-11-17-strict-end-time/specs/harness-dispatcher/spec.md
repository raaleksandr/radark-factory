## MODIFIED Requirements

### Requirement: Ending a run at its end time
Before every new step the dispatcher SHALL compare the current time with the run's end time. When the end time is reached, it MUST NOT start the step and SHALL end the run. Without a strict end time a running session is never stopped by this check; with a strict end time running sessions are stopped as described in *Stopping sessions at a strict end time*. Time the computer sleeps SHALL count towards the end time. When the run also has a maximum duration or other limits, whichever is reached first ends the run.

#### Scenario: End time reached after a session
- **WHEN** a run has an end time of 07:00, a session ends at 07:12 and a work item is waiting
- **THEN** no new session starts and the run ends

#### Scenario: Session running at the end time
- **WHEN** a session is running at the end time and the run has no strict end time
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

### Requirement: Reporting an end time
At the start of a run with an end time the dispatcher SHALL print and log the end time as a local date and time with the time left, and whether it is strict: with a strict end time, when running sessions are asked to wrap up and by when they are stopped; without, that running sessions finish first. When the end time ends the run it SHALL print and log that the end time was reached. `dry-run` given an end time SHALL print when the run would end, with the same mode.

#### Scenario: Start line
- **WHEN** at 22:10 a run starts with an end time of `07:00`
- **THEN** the console shows that the run ends at 07:00 the next day, in 8 h 50 min, that running sessions finish first, and the run log records the end time with `strict` false

#### Scenario: Start line of a strict end time
- **WHEN** at 10:02 a run starts with an end time of `12:00`, a strict end time and the default wrap-up grace period of 15 minutes
- **THEN** the console shows `Run ends at 12:00 today, in 118 min (strict: running sessions wrap up at 12:00, stopped by 12:15)` and the run log records the end time with `strict` true

#### Scenario: End line
- **WHEN** the run ends because its end time of 07:00 is reached
- **THEN** the console and the run log say that the end time 07:00 was reached

#### Scenario: Dry run with an end time
- **WHEN** `dry-run` is given an end time of `07:00` at 22:10
- **THEN** it prints that the run would end at 07:00 the next day, in 8 h 50 min, and that running sessions finish first

#### Scenario: Dry run with a strict end time
- **WHEN** `dry-run` is given an end time of `12:00` and the strict option at 10:02
- **THEN** it prints that the run would end at 12:00 today, in 118 min, and that running sessions wrap up at 12:00 and are stopped by 12:15

## ADDED Requirements

### Requirement: Strict end time
The owner SHALL be able to make a run's end time strict, for one run with a command-line option (and to turn a configured default off for one run), or as the default in the `[loop]` configuration. Without either the end time SHALL NOT be strict. The setting SHALL apply to that run only and MUST NOT be stored.

#### Scenario: Option turns strict mode on
- **WHEN** the owner starts `run --until 12:00 --until-strict` with no `until_strict` in the configuration
- **THEN** the run's end time is strict

#### Scenario: Configured default and its override
- **WHEN** the configuration sets `until_strict = true` and the owner starts `run --until 12:00 --no-until-strict`
- **THEN** the run's end time is not strict

### Requirement: Validating the strict end time option
The command-line option given without an end time MUST be refused before any session starts, with a message naming the option and `--until`; the configuration default without an end time SHALL have no effect. A configured value that is not a boolean MUST be refused before any session starts.

#### Scenario: Configured default without an end time
- **WHEN** the configuration sets `until_strict = true` and the owner starts `run` without `--until`
- **THEN** the run starts as without an end time and prints nothing about strict mode

#### Scenario: Option without an end time
- **WHEN** the owner starts `run --until-strict` without `--until`
- **THEN** the dispatcher exits with a non-zero code and a message that `--until-strict` needs `--until`, and starts no session

#### Scenario: Invalid configured value
- **WHEN** the configuration sets `until_strict = "yes"`
- **THEN** the dispatcher refuses the configuration with a message naming `loop.until_strict`, and starts no session

### Requirement: Stopping sessions at a strict end time
With a strict end time, every running session of the run SHALL end by the end time plus the wrap-up grace period. A work session that is not a wrap-up SHALL be stopped at the end time and, with a grace period above 0, resumed at once in the same step with an end-time wrap-up prompt, limited to the grace period, without a limit check or a second wrap-up. Other sessions SHALL be stopped at the end time plus the grace period. The run then ends.

#### Scenario: Strict end time with a work session running
- **WHEN** a run with a strict end time of 12:00 and a grace period of 15 minutes has an apply session running at 12:00
- **THEN** at 12:00 the session is stopped and resumed with the end-time wrap-up prompt, no limit check runs and no extension is given, the wrap-up session is stopped by 12:15 if it still runs, no new session starts and the run ends

#### Scenario: Grace period turned off
- **WHEN** a strict run has `wrap_up_minutes = 0` and a work session runs at the end time
- **THEN** the session is stopped at the end time, without a wrap-up, as `interrupted` with the cause `end_time`

#### Scenario: Parallel sessions at a strict end time
- **WHEN** two work sessions of different teams run at a strict end time
- **THEN** both are stopped at the end time and wrap up, and the run ends after both

### Requirement: No extension after a strict end time
With a strict end time, no limit check SHALL run and no extension SHALL be given after the end time. Without a strict end time limit checks and extensions SHALL work as before.

#### Scenario: Deadline after the end time
- **WHEN** a strict run's end time is 12:00 and a running apply session's limit-check deadline falls at 12:05
- **THEN** no limit check runs for that deadline and the session gets no extension

#### Scenario: Default mode unchanged
- **WHEN** a run with an end time that is not strict has a work session running at the end time whose limit check later finds it progressing
- **THEN** the session is not stopped and gets its extension, as before

### Requirement: End-time wrap-up prompt
The end-time wrap-up prompt SHALL name the end time and the grace period, say the running step was cut off, and ask the session to check `git status`, start no new work and commit what works. For apply it SHALL ask to check off finished tasks, write the open ones in `tasks.md`, and not report the handover done unless the phase is complete.

#### Scenario: Wrap-up prompt at the end time
- **WHEN** an apply session for HO-20261028-vw90 is stopped at a strict end time of 12:00 with the default grace period
- **THEN** the resumed session's prompt names the end time and the 15-minute grace period, asks to check `git status`, start no new work, commit what works, check off finished tasks and write the open ones in `tasks.md`, and not to report the handover done unless the phase is complete

### Requirement: Outcome of a session stopped at a strict end time
A session stopped at a strict end time SHALL be classified `interrupted` with the cause `end_time` and MUST NOT count as an error or as no progress; the item's next session SHALL resume it in its own context with a message that the previous run reached its end time. An end-time wrap-up that completes its phase SHALL keep its normal outcome. Each stop SHALL be logged as `end_time_stop` and shown on the console, each end-time wrap-up logged as `end_time_wrap_up` with its outcome.

#### Scenario: Unfinished work resumed by the next run
- **WHEN** the end-time wrap-up session is stopped at 12:15 without completing its phase
- **THEN** the step's outcome is `interrupted` with the cause `end_time`, not `error`, and the next run's session for that item resumes the same session with a message that the previous run reached its end time

### Requirement: Hint when a session runs past a non-strict end time
When the end time of a run that is not strict passes while a session is running, the dispatcher SHALL print once per run, on the console and so in `console.log`, a line that the end time has passed, the running session finishes, and that `--until-strict` ends on time, and SHALL log it as `end_time_passed`. A run with a strict end time or without an end time SHALL NOT print it.

#### Scenario: Hint printed once
- **WHEN** a run with a non-strict end time of 12:00 has a session running at 12:00, and a second session (its wrap-up) runs after it
- **THEN** the console shows `Note: the end time 12:00 has passed; the running session finishes. To end on time, use --until-strict.` exactly once and the run log has one `end_time_passed` event

#### Scenario: No hint when nothing runs
- **WHEN** a run with a non-strict end time of 12:00 is idle at 12:00
- **THEN** no hint is printed and the run ends at the end time
