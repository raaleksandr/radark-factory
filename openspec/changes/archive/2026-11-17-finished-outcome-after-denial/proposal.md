# Proposal: a finished session with a non-escalated denial is logged `finished`

Handover: **HO-20261117-mw63** (RB-019, "a finished session with a non-escalated denial is logged 'finished', not
'waiting_for_owner'"), from `radark-product`.

## Why

A work session that completes its phase despite a permission denial is not escalated (spec: *Permission denial in a
completed phase*), and the dispatcher handles it as `finished`. But the decision is taken in `after_session`, after
`session()` has already printed the end line, written `session_end` to the run log, stored the session in the item's
record and added the end line to the goal report's steps — all with the raw classification `waiting_for_owner`. The
owner reads:

```
05:03  ! app HO-20261101-aaaa: permission denied: Bash
05:03  app · apply · HO-20261101-aaaa → waiting_for_owner (2 h 15 min)
05:03  ! app HO-20261101-aaaa: phase completed despite the permission denial (Bash); not escalated
```

and takes it for a stop that needs them, although nothing was sent to them and the run goes on.

## What Changes

- The "completed phase, only denials, not escalated" decision moves before the session's end is reported: every
  place that shows or stores the session's outcome — console end line (and so `console.log`), `session_end` in
  `runs.jsonl`, the session entry in the item's record (`state.json`, read by the cockpit) and the goal report's
  steps — says `finished`.
- The end line names the denials: `→ finished (2 h 15 min; 1 permission denial, not escalated)` (plural
  `2 permission denials`).
- `session_end` and the stored session entry get a field `unescalated_denials` with the count of those denials (only
  when non-zero); `denials` keeps the count of all denials as today.
- `waiting_for_owner` stays for every session that really waits for the owner: an escalation marker, a denial in a
  phase that was not completed, or a `BLOCKED: owner` line in an apply/act session that did not complete its phase.
- Unchanged: the `denial` events and their `!` lines, the `denial_not_escalated` event and its `!` line
  ("phase completed despite the permission denial …; not escalated"), the hand-on of `unescalated_denials` to the
  next review prompt and the goal report's "Permission denials not escalated" section.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Permission denial in a completed phase* — the `finished` outcome is the one printed, logged
  and recorded, with the denial count in the end line and an `unescalated_denials` field in the session's records.

## Impact

- `radark/__main__.py`: `Dispatcher.session()` decides the completed-phase denial case before `session_end` and the
  end line; `after_session` uses that decision instead of re-deriving it; `end_line` gets the denial note;
  `phase_complete` can be called from `session()`.
- `radark/README.md`: the outcome paragraph no longer says that `session_end` keeps the raw `waiting_for_owner`.
- Tests: `radark/tests/test_denial.py` (expectations updated, new cases), possibly a cockpit-history test.
- No change to the hub, the `ho` contract, the state format beyond the new optional field, or selection.
