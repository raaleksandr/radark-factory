## ADDED Requirements

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
