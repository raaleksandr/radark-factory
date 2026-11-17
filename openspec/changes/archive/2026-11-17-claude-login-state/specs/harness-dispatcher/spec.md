## ADDED Requirements

### Requirement: Reporting the Claude Code login state
The start summary of `run`, `once` and `dry-run` (also `run --once` and `run --dry-run`) SHALL append the Claude Code login state to the Claude Code version line, after `; `. A status with `loggedIn` true SHALL give `logged in`; with `loggedIn` false, `` NOT logged in - run `claude` and log in (sessions would fail) ``; any other outcome SHALL give `login state unknown (<reason>)`, the reason saying that the status command is not available, timed out, or gave no readable answer.

#### Scenario: Logged in
- **WHEN** `dry-run` starts and `claude auth status --json` prints `{"loggedIn": true, ...}`
- **THEN** the start summary has the line `Claude Code: <version>; logged in`

#### Scenario: Not logged in
- **WHEN** `run` starts and the status command prints `{"loggedIn": false}` and exits 1
- **THEN** the start summary has `` Claude Code: <version>; NOT logged in - run `claude` and log in (sessions would fail) ``

#### Scenario: Status command missing
- **WHEN** the installed Claude Code rejects `auth status` with an error and a non-zero exit code
- **THEN** the line ends with `` login state unknown (`claude auth status` not available) ``

#### Scenario: Status command hangs
- **WHEN** the status command does not answer within the limit
- **THEN** it is stopped and the line ends with `` login state unknown (`claude auth status` timed out) ``

#### Scenario: Unreadable answer
- **WHEN** the status command exits 0 but its output is not a JSON object with a boolean `loggedIn`
- **THEN** the line ends with `` login state unknown (`claude auth status` gave no readable answer) ``

### Requirement: Login probe
The dispatcher SHALL learn the login state from one read-only probe per start, `claude auth status --json` with the configured `claude` command and a 10-second limit, run in the process environment without `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`. The probe starts no session and spends no tokens. The dispatcher MUST NOT probe again during the run, and MUST NOT print, log or store any field of the status output other than the login state.

#### Scenario: One probe per start
- **WHEN** `run` starts and then runs several sessions
- **THEN** `claude auth status` was called exactly once

#### Scenario: Account details stay private
- **WHEN** the status output also has an e-mail address and an organisation name
- **THEN** neither appears in the start summary, `console.log`, the run log or the state

### Requirement: Login state is a warning
The login state SHALL be a warning only: it MUST NOT change any exit code, and `run` and `once` SHALL go on to start sessions when not logged in or when the state is unknown.

#### Scenario: Dry run exit code
- **WHEN** `dry-run` reports `NOT logged in` or `login state unknown (...)`
- **THEN** it exits with the same code as when logged in, and no Claude Code session is started

#### Scenario: Run goes on
- **WHEN** `once` starts with work waiting and the summary says `NOT logged in`
- **THEN** it still starts the session for that work
