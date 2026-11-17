## ADDED Requirements

### Requirement: Start banner
When the dispatcher starts in run, once or dry-run mode (also `run --once` and `run --dry-run`), it SHALL print a static banner once, on standard output, immediately before the configuration summary that begins the start output. The start output after the banner SHALL be the same lines in the same order as without it. In run and once mode the banner SHALL reach `console.log` like every other console line; dry-run writes no `console.log`, as before.

#### Scenario: Banner at the start of a run
- **WHEN** the owner starts `run` with a valid configuration and a compatible `ho`
- **THEN** standard output begins with the banner, followed by the configuration summary and the same lines in the same order as without the banner

#### Scenario: Banner in dry-run
- **WHEN** the owner runs `dry-run`
- **THEN** its output begins with the banner once, followed by the summary and the dry-run lines as before, and the hub, the state, the run log and `console.log` are unchanged

#### Scenario: Banner in console.log
- **WHEN** the owner starts `once` and the session ends
- **THEN** `console.log` has the header line of this start followed by the banner lines and then the summary, the same text as the window

### Requirement: Form of the start banner
The banner SHALL show the lettering `RA DARK FACTORY` in big block letters, with the space between `RA` and `DARK`, and a drawing of a factory building with chimneys and smoke coming out of them. Every line SHALL consist of printable ASCII characters only (0x20 to 0x7E), be at most 80 characters long and not end with a space; the banner SHALL have at most 25 lines and use no colours and no cursor control.

#### Scenario: Banner renders in any console
- **WHEN** the banner is printed in Windows PowerShell 5.1 with a legacy code page, or `console.log` is read with any editor
- **THEN** it shows the same characters, since every line is printable ASCII of at most 80 characters without trailing spaces

### Requirement: Banner only at a start
The banner SHALL NOT be printed by any other command (`plan`, `status`, `cockpit`, `escalations`, `clear`, `keep`, `note`, `test-slot`), nor when a start ends before the configuration summary (configuration error, incompatible `ho`, machine error). There SHALL be no option to turn it off.

#### Scenario: No banner for other commands
- **WHEN** the owner runs `plan`, `status`, `cockpit` or `escalations`
- **THEN** the output has no banner line

#### Scenario: No banner on a refused start
- **WHEN** the owner starts `run` and the configuration file has an error
- **THEN** only the configuration error is printed, without the banner
