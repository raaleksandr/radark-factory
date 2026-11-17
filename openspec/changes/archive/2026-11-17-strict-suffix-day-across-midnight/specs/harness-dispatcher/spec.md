## MODIFIED Requirements

### Requirement: Reporting an end time
At the start of a run with an end time the dispatcher SHALL print and log the end time as a local date and time with the time left, and whether it is strict: with a strict end time, when running sessions are asked to wrap up and by when they are stopped; without, that running sessions finish first. When the moment by which sessions are stopped falls on a different calendar day than the end time, it SHALL name its day (`tomorrow`, or the date when that day is not tomorrow); on the same day it SHALL be shown as a clock time only. When the end time ends the run it SHALL print and log that the end time was reached. `dry-run` given an end time SHALL print when the run would end, with the same mode.

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

#### Scenario: Strict grace period passes midnight
- **WHEN** at 22:10 a run starts with an end time of `23:59`, a strict end time and a wrap-up grace period of 15 minutes
- **THEN** the console shows `Run ends at 23:59 today, in 109 min (strict: running sessions wrap up at 23:59, stopped by 00:14 tomorrow)`

#### Scenario: Strict grace period passes midnight on a later date
- **WHEN** on 2026-11-18 a run starts with an end time of 23:59 on 2026-11-19, a strict end time and a wrap-up grace period of 15 minutes
- **THEN** the strict-mode text says that running sessions wrap up at 23:59 and are stopped by `00:14 on 2026-11-20`
