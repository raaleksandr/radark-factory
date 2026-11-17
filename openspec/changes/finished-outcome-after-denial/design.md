# Design: a finished session with a non-escalated denial is logged `finished`

Handover: HO-20261117-mw63 (RB-019).

## Context

`runner.classify` gives every session with a denial the outcome `waiting_for_owner`. `Dispatcher.session()` then,
in this order, logs `session_end` with that outcome, prints the end line (`end_line`), appends it to
`goal.steps` (the goal report's step list) and appends the session to `rec["sessions"]` (state, read by the
cockpit). Only afterwards `finish()` → `after_session()` checks *denial only + normal end + phase complete*
(escalate-denial D1/D2, `denial_only`, `normal_end`, `phase_complete`), calls `denial_not_escalated` and sets
`r.outcome = "finished"`. The rest of `after_session` (no escalation, phase bookkeeping, progress) already treats the
session as finished; only the reports made earlier carry the wrong word. The archived README even documents it
("its `session_end` keeps the raw `waiting_for_owner`").

Consumers of the outcome were checked:

- console end line / `console.log` / goal report steps — all from `end_line(...)` in `session()`: wrong today;
- `session_end` in `runs.jsonl` — read by `cockpit_history` (session rows, outcome column): wrong today;
- `rec["sessions"][*].outcome` in `state.json` — wrong today;
- `after_session` and everything after it (escalation, progress, archive gate, `no_progress`) — already `finished`;
- selection (`radark/select.py`) and `cockpit_now` do not branch on a session's outcome word; "escalated" counts in
  the goal report come from blocked records (`goal_blocked_items`), which this case never creates. No change there.

## Decisions

### D1. Decide before reporting, in `session()`

For a work session (`work` in `session()`: a handover and not `consult`) whose classified outcome is
`waiting_for_owner`, `session()` evaluates the same condition `after_session` uses today —
`denial_only(r) and normal_end(r) and phase_complete(...)` with `since or r.started` — right after the denial
events are logged and before `session_end`. If it holds, it sets `r.outcome = "finished"` and
`r.unescalated_denials = len(r.denials)` (a new `SessionResult` field, default 0). Everything `session()` reports
after that point then carries `finished`.

`phase_complete` takes a `Candidate` today but uses only its team, handover and phase; it gets a small change so
that `session()` can call it with those values (a `Candidate` built from them, or the three values as arguments —
implementer's choice, recorded in the tasks notes). `rec` is already available in `session()`.

The `BLOCKED: owner` check in `after_session` does not interfere: it is overridden anyway when the phase is
complete ("a completed phase is handled as before, whatever its last line says"), which is exactly the case decided
here.

*Alternative considered:* print and log the end only after `after_session`. Rejected: it reorders many console lines
(time-limit, wrap-up, error lines) and touches every caller of `session()`, not only work sessions.

*Alternative considered:* log a second, corrected event. Rejected: two outcomes for one session in the run log and
the cockpit would have to reconcile them.

### D2. `after_session` uses the decision

`after_session` replaces its own D1 check with `if r.unescalated_denials: self.denial_not_escalated(cand, rec, r)`
(the outcome is already `finished`). `denial_not_escalated` is unchanged: same `denial_not_escalated` event, same
`!` line, same `unescalated_denials` hand-on to the next review and the goal report. A test that calls
`after_session` directly on a raw `waiting_for_owner` result (the time-limit case) still escalates, since that
session is not a normal end.

Console order therefore becomes: `! … permission denied: Bash`, the end line `→ finished (…; 1 permission denial,
not escalated)`, then `! … phase completed despite the permission denial (Bash); not escalated` — the same order as
today, with the right word.

### D3. Wording and field names

- End line: `end_line` appends `; N permission denial(s), not escalated` inside the parentheses after the duration
  when `r.unescalated_denials` is non-zero:
  `app · apply · HO-20261101-aaaa → finished (2 h 15 min; 1 permission denial, not escalated)`. No time-limit or
  interrupt cause can appear together with it (a normal end has neither).
- `session_end` gets `unescalated_denials=<count>` only when non-zero (`denials` stays the count of all denials, so
  cockpit history keeps showing the denial count). The session entry in `rec["sessions"]` gets the same key, also
  only when non-zero. The state format stays readable by older code (an extra optional key).
- The record field is named `unescalated_denials` like the existing list on the item record and the goal report
  key; on a session entry and in `session_end` it is a count, on the item record it stays the list of denials.

### D4. What stays `waiting_for_owner`

An escalation marker (also together with a denial), a denial in a session that did not complete its phase or did not
end normally (time limit, error, interrupt), and an apply/act `BLOCKED: owner` line without a completed phase. No
change to `runner.classify`; the raw classification is only corrected for the one case above.

## Risks / Trade-offs

- `phase_complete` calls `ho show` for apply/act/review. It ran in `after_session` anyway; it now runs once in
  `session()` instead (not twice): `after_session` must not call it again for this case.
- Locking: `self.lock.released()` covers only `runner.run`, so the new check runs with the dispatcher lock held,
  where the denial events are logged today — as `after_session` did.
- Existing test `test_console_and_run_log` asserted the raw outcome in `session_end` (old README note); it is updated
  to expect `finished` and `unescalated_denials == 1`.

## Assumptions (unattended propose)

- The handover leaves the field name and wording to the team; chosen as in D3.
- A wrap-up session (`wrap_up=True`) follows the same rule: its own `session()` call decides for its own result.
- The owner-answer resume path (`session(..., since=...)`) uses `since` for `phase_complete`, as `after_session` did.
