## RENAMED Requirements

- FROM: `### Requirement: One agent at a time`
- TO: `### Requirement: One agent per repository at a time`

## MODIFIED Requirements

### Requirement: One agent per repository at a time
The harness SHALL run at most one team agent session in a repository at any moment, and at most the configured number of sessions across all repositories (one by default). Sessions of different repositories MAY run at the same time only for unrelated work: work that waits for another team's result MUST wait until that result is there. Further work MUST wait in order until a place is free. A dispatcher session that only reads the hub and wakes teams, and does no work in a team repository, is not a team agent session. Team sessions left open between phases but idle do not count either; only a session currently working counts.

#### Scenario: Two teams have work
- **WHEN** both `app` and `backend` have `action_required` items and one session is allowed
- **THEN** the harness runs one of them, and starts the other only after the first session has ended

#### Scenario: Two teams have unrelated work and two sessions are allowed
- **WHEN** both `app` and `backend` have unrelated `action_required` items and two sessions are allowed
- **THEN** the harness runs both at the same time

#### Scenario: Same repository
- **WHEN** `app` has two `action_required` items and two sessions are allowed
- **THEN** the harness runs one of them, and starts the other only after the first session has ended
