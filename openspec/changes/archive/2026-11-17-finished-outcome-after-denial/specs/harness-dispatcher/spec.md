## MODIFIED Requirements

### Requirement: Permission denial in a completed phase
A work-item session whose only reason to wait for the owner is a permission denial SHALL NOT be escalated when it completed its phase: it ended normally (exit 0, a final result, hooks loaded, no time limit, not interrupted) and during it the phase's signal appeared — propose: the change exists; apply or act: the worker marked `done` or `declined`; review: the handover was closed or returned to the worker; archive: the change directory is gone. Such a session SHALL get the outcome `finished`, and that outcome SHALL be the one the dispatcher reports for it everywhere: the console end line (and so `console.log` and the goal report's steps), the `session_end` event in the run log and the session entry in the item's record. Its end line SHALL name the denials after the duration, as `→ finished (<duration>; <N> permission denial(s), not escalated)`, and its `session_end` event and session entry SHALL carry `unescalated_denials` with their count. The outcome `waiting_for_owner` SHALL be reported only for a session that really waits for the owner. Any other denial session SHALL be escalated as before. Sessions without a work item are not affected.

#### Scenario: Agent works around a denial and finishes
- **WHEN** an apply session has a PowerShell `Stop-Process` denied, stops its test run another way, marks its part `done` and exits with code 0 and a final result
- **THEN** the outcome is `finished`, no escalation handover is sent, the console shows the denial line and a line that the phase was completed despite it, and the run log has `denial` and `denial_not_escalated`

#### Scenario: Denial and an escalation together
- **WHEN** a session has a permission denial and also asks a question with an escalation keyword, then marks its part `done`
- **THEN** the item is escalated with both reasons, as before

#### Scenario: Denial in a session cut by a time limit
- **WHEN** a session with a permission denial is ended by the maximum duration
- **THEN** the phase is not complete and the item is escalated, as before

#### Scenario: Outcome line of a completed phase with a denial
- **WHEN** an apply session for HO-20261101-aaaa has one Bash denial, marks its part `done` and ends normally after 2 h 15 min
- **THEN** the console end line reads `app · apply · HO-20261101-aaaa → finished (2 h 15 min; 1 permission denial, not escalated)`, the run log's `session_end` has outcome `finished`, `denials` 1 and `unescalated_denials` 1, the item's session entry has outcome `finished`, and no line or record of that session says `waiting_for_owner`

#### Scenario: Escalated denial still waits for the owner
- **WHEN** a session has a permission denial and an escalation marker, or a denial without completing its phase
- **THEN** its end line, `session_end` and session entry say `waiting_for_owner`, without `unescalated_denials`
