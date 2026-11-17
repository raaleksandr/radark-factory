## MODIFIED Requirements

### Requirement: Dry run with parallel sessions
With more than one session allowed, dry-run SHALL print, after the session it would start, the further sessions it would start at the same time by *Number of parallel sessions*, or that nothing else could start and why. With one session allowed its output SHALL be as before. The plan mode SHALL stay a sequential prediction.

The prompt dry-run prints for the session it would start SHALL be exactly the prompt that session would receive when started now: the phase prompt (or the resume message after a time limit) followed by the parallel note when more than one session is allowed, and by the test-slot note whenever the real prompt would carry it. With one session allowed and no other session running on the computer, the prompt SHALL carry no note, as before. Building the printed prompt MUST NOT change the state.

#### Scenario: Two teams in a dry run
- **WHEN** `parallel_sessions` is 2 and `app` and `backend` have unrelated candidates
- **THEN** dry-run names the `app` session it would start and a line naming the `backend` session it would start in parallel

#### Scenario: Parallel note in the printed prompt
- **WHEN** `parallel_sessions` is 2 and `app` has a candidate HO-20261117-ab12 in phase `propose`
- **THEN** the prompt dry-run prints ends with the parallel note, and it is the same text a real start of that session passes to Claude Code

#### Scenario: One session, no note
- **WHEN** `parallel_sessions` is 1, no other dispatcher's session runs on the computer, and `app` has a candidate
- **THEN** the prompt dry-run prints carries no parallel note and no test-slot note, and equals the prompt a real start passes

#### Scenario: Resume after a time limit
- **WHEN** `parallel_sessions` is 2 and the next candidate resumes a session after its time limit
- **THEN** dry-run prints the resume message followed by the parallel note, the same text the real resume passes

#### Scenario: Dry run leaves the state unchanged
- **WHEN** dry-run prints the prompt of a review candidate whose record holds denials that were not escalated
- **THEN** the state file is unchanged afterwards and a later real review session still gets those denials
