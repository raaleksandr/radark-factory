## MODIFIED Requirements

### Requirement: Phase prompts
For each selected candidate the dispatcher SHALL choose a phase and send the team agent a prompt that names the handover ID, the phase and the expected next step:
- a technical team's new handover → **propose**: read the handover, acknowledge it, create an OpenSpec change citing the handover ID;
- a technical team's handover whose change is proposed → **apply**: implement the change; report `ho done` when finished, or send a handover to another team if it needs one;
- a handover returned to a technical team → **apply** on the same change, following the return comments;
- an author's `to_review` item → **review**: close the handover if the result is accepted, or return it with the request;
- an approved change → **archive**: archive the OpenSpec change;
- a product team's `action_required` item → **act** on the handover per the hub guide, without creating an OpenSpec change for routine work.
A technical handover's change counts as proposed only when the dispatcher knows it: the propose session named it, or a change in the team repository cites the handover ID. A propose session after which no such change is known, whatever its outcome, MUST leave the handover new, so that its next session is propose again; the dispatcher SHALL log this and show it on the console. The no-progress rule of *Session outcome* still applies to these repeated propose sessions.
Every prompt MUST also carry the standing rule: never ask the user; choose the best variant, record the assumption in the change, and continue; stop only when the phase is complete or blocked by something outside the repository.
Every session the dispatcher starts, new or resumed, MUST also carry the long-wait rule in its system prompt: do not wait silently on a command or a background task for longer than the check interval; check its progress at least once per interval (its latest output, a progress counter, whether the process is alive); if two checks in a row show no progress, treat it as hung: stop it, record what was seen, and continue another way or report it. The check interval SHALL be half the configured inactivity limit (`loop.session_idle_minutes`), rounded down to whole minutes, and at least 1 minute (10 minutes with the default 20-minute limit), and the rule SHALL state both the interval and the inactivity limit. The inactivity limit and what counts as activity are unchanged.

#### Scenario: New task goes to propose
- **WHEN** `app` has a new `action_required` handover `HO-20261016-ab12` with no change recorded for it
- **THEN** the session prompt asks the agent to read `HO-20261016-ab12`, acknowledge it and create an OpenSpec change citing that ID

#### Scenario: Returned task continues the same change
- **WHEN** the author returns a handover whose change `add-export` is recorded for `app`
- **THEN** the prompt asks the agent to continue `add-export` according to the return comments, and not to create a new change or archive

#### Scenario: Propose cut before the change exists
- **WHEN** the propose session for `HO-20261026-47ch` acknowledges the handover and then ends with an API error, and no change in `app` cites `HO-20261026-47ch`
- **THEN** the console shows that propose created no change, and the next session for `HO-20261026-47ch` is propose, not apply

#### Scenario: Propose that failed after creating the change
- **WHEN** a propose session ends with an error and gives no `CHANGE:` line, but a change `fix-scroll` in the team repository cites the handover ID
- **THEN** `fix-scroll` is recorded for the handover and the next session is apply on `fix-scroll`

#### Scenario: Repeated propose without progress stalls
- **WHEN** two consecutive propose sessions for the same handover end with no change, no hub activity, no commits and no checked tasks
- **THEN** the item is marked stalled and escalated to the owner, as for any item without progress

#### Scenario: Record from an older dispatcher
- **WHEN** a stored record says phase `propose` with no change, the handover is not returned and the hub shows no `done` by the team
- **THEN** the next session for that handover is propose

#### Scenario: Long-wait rule with the default limit
- **WHEN** the dispatcher starts or resumes any session with the default inactivity limit of 20 minutes
- **THEN** the session's system prompt carries the standing rule and the long-wait rule with a check interval of 10 minutes, and names the 20-minute limit

#### Scenario: Long-wait rule follows the configured limit
- **WHEN** `loop.session_idle_minutes` is 30
- **THEN** the long-wait rule names a check interval of 15 minutes and the 30-minute limit

#### Scenario: Non-integer limit rounds the interval down
- **WHEN** `loop.session_idle_minutes` is 25, or 2.5
- **THEN** the long-wait rule names a check interval of 12 minutes, or of 1 minute with the 2.5-minute limit
