## ADDED Requirements

### Requirement: Stored threshold wait follows the current run's thresholds
A threshold wait stored by an earlier run or step SHALL be re-checked before every new step, so also at run start, against the current run's thresholds: the run budget for a budgeted window, else `usage_pause_percent`, with the latest reading. When its window no longer holds, the dispatcher SHALL drop the wait from the state and start the step; otherwise the wait stays. A `limit_hit` wait and another pipeline's hold SHALL NOT be dropped this way.

#### Scenario: Higher run budget drops a stored threshold wait
- **WHEN** the state holds a threshold wait on the seven-day window (stored at 90 % with `usage_pause_percent` 90, reset tomorrow), and a new run starts with a seven-day budget of 95 % while the seven-day window is at 90 % and a work item is waiting
- **THEN** the dispatcher does not wait, the wait is removed from the state, and the work item's session starts

#### Scenario: Raised threshold drops a stored threshold wait
- **WHEN** the state holds a threshold wait on the five-hour window stored at 90 %, and a new run starts with `usage_pause_percent = 95` and the five-hour window at 91 %
- **THEN** the dispatcher does not wait, the wait is removed from the state, and the next step starts

#### Scenario: Threshold still reached
- **WHEN** the state holds a threshold wait on the seven-day window, and a new run starts with a seven-day budget of 95 % while the seven-day window is at 95 % or above
- **THEN** the wait is not dropped and the run ends at its budget as for any budget reached, without starting a step

#### Scenario: Unbudgeted window still at the threshold
- **WHEN** the state holds a threshold wait on the five-hour window at 92 %, `usage_pause_percent` is 90, and a new run has only a seven-day budget
- **THEN** the wait stays and the dispatcher waits for the five-hour reset as before

#### Scenario: Usage-limit wait not dropped
- **WHEN** the state holds a wait with cause `limit_hit` on the seven-day window, and a new run starts with a seven-day budget of 95 % while the reading shows 90 %
- **THEN** the wait stays and no step starts before its until-time

#### Scenario: Another pipeline's hold not dropped
- **WHEN** another pipeline's usage-limit hold is in force, and this instance starts a run with a higher budget while the reading is below it
- **THEN** the hold stays and no step starts before it ends

## MODIFIED Requirements

### Requirement: Reporting usage waits
The dispatcher SHALL print to the console, and write to the run log: when a running session's usage report first crosses the threshold (window, used share); when it starts holding new steps or waiting after a hit (window, used share, reset time in local time, wait length, cause `threshold` or `limit_hit`); when it drops a stored threshold wait because the current run's threshold is no longer reached (window, used share, the threshold that now applies); and when it resumes. `dry-run` SHALL print the latest reading per window and whether the guard would hold the next step.

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

#### Scenario: Dropped threshold wait announced
- **WHEN** a run with a seven-day budget of 95 % drops a stored threshold wait on the seven-day window at 90 %
- **THEN** the console shows one line naming the seven-day window, 90 % and the 95 % budget and saying the stored wait no longer applies, and the run log has a matching `usage_wait_dropped` event

#### Scenario: Dry run shows a stored wait
- **WHEN** `dry-run` is run while the state holds a usage wait that has not ended
- **THEN** it prints the wait's cause and until-time in local time, and for a threshold wait that the current thresholds no longer reach it says the wait would be dropped and the next step would start
