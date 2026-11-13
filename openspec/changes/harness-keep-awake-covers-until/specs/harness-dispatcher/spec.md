## MODIFIED Requirements

### Requirement: Keeping the computer awake
The owner SHALL be able to set, for a run (plain, one-shot or goal run), when the dispatcher keeps the computer from going to sleep on its own: never, for the whole run, until a moment, or every day within a time range. Without the option the configured default SHALL apply; with neither, the dispatcher MUST NOT keep the computer awake. An unreadable value MUST be refused before any session starts. When the run has an end time and the keeping-awake moment is at or after that end time, the dispatcher SHALL keep the computer awake for the whole run, until the run ends, including a session that finishes after the end time; a moment before the end time SHALL keep its meaning.

#### Scenario: Default does not keep awake
- **WHEN** the owner starts a run without the option and the configuration does not set a default
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

### Requirement: Reporting keeping awake
When keeping awake is set for a run, the start of the run SHALL print and log the setting with its moment or range, and the goal run's start record SHALL include it. When a moment at or after the end time is turned into the whole run, the start line and the log record SHALL say so and name the given moment. Each time keeping awake starts or stops during the run, the dispatcher SHALL print one console line with the local time and write a run-log event. `dry-run` SHALL accept the option and print the setting and whether the computer would be kept awake now.

#### Scenario: Start line until a moment
- **WHEN** at 14:00 the owner starts a run with keeping awake until `23:00`
- **THEN** the start shows "Keep awake: until 23:00 today, in 9 h 00 min" and the run log has a record of the setting

#### Scenario: Start line for a moment covered by the end time
- **WHEN** the owner starts a run with end time `12:00` and keeping awake until `12:00`
- **THEN** the start shows "Keep awake: whole run (until 12:00 given, the run ends at 12:00)" and the run-log record has the mode of the whole run and the given moment

#### Scenario: Stop at the moment
- **WHEN** a run keeps the computer awake until 23:00 and the clock reaches 23:00
- **THEN** the console shows "23:00  Keep awake ended; the computer may sleep." and the run log has an event with the change

#### Scenario: Dry run with a range
- **WHEN** at 23:30 the owner runs `dry-run` with keeping awake `08:00-23:00`
- **THEN** the output names the range and says the computer would not be kept awake now, until 08:00

#### Scenario: Dry run with a moment covered by the end time
- **WHEN** the owner runs `dry-run` with end time `12:00` and keeping awake until `12:00`
- **THEN** the output says the computer would be kept awake for the whole run, naming the given moment

#### Scenario: Not set
- **WHEN** a run starts with keeping awake off
- **THEN** the start shows no keep-awake line and the run log has no keep-awake event
