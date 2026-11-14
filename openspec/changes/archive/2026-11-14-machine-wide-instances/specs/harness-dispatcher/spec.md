## ADDED Requirements

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
