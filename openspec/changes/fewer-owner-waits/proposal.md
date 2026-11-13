# Proposal: fewer and shorter owner waits

Handover: **HO-20261113-armh** (backlog item RB-014, from `radark-product`).

## Why

Sessions end waiting for the owner far more often than they need to. Two causes:

1. **Denials that end a session silently.** Routine commands — discarding a working-tree edit (`git restore <file>`,
   `git checkout -- <file>`), stopping the session's own test server (`Stop-Process`), writing a temporary script
   outside the allowed directories — are denied by the permission mode. The session gets no hint of an allowed way
   to do the same thing, so the work stops; and when it stops after the phase signal appeared it is logged
   `denial_not_escalated` and nobody is asked. When it is escalated, the owner sees only `permission denied: Bash`,
   not what was denied, why it was needed, or what the team suggests.
2. **Questions a team could decide itself.** The triage consultation and the `BLOCKED: owner` rule send the owner
   decisions that the deciding team's own instructions already allow it to take (e.g. picking an option it already
   recommended), because nothing in the engine's prompts tells it to decide what its policy allows.

Which decisions a team may take and which only the owner may take is each pipeline's own policy (its teams'
`CLAUDE.md`, the goal file), not the engine's. The engine only has to tell teams to apply that policy and to give
denied sessions an allowed way forward.

## What Changes

- **Guard hook for routine denials.** A new `PreToolUse` hook (`guard.py`, on `Bash`, `PowerShell`, `Write`,
  `Edit`) recognises the three routine command kinds and either allows a narrow, safe form or denies with a reason
  that names the allowed way:
  - discarding working-tree edits of **named files inside the team repository** (`git restore [--staged|--worktree]
    [--] <file>…`, `git checkout -- <file>…`) is allowed; broad forms (`.`, directories, wildcards, pathspec magic,
    `--source`) are denied with the message to name the files or re-write them;
  - stopping processes **by ID that descend from the session's own Claude Code process** (`Stop-Process -Id`,
    `taskkill /PID`, `kill <pid>`) is allowed; by name or of other processes is denied with the message to stop
    only its own processes by ID, or to run servers as background tasks and stop them with the task tool;
  - a write to the system temporary directory is denied with the message to use the session's temp directory.
  Every other tool call is left to the permission mode, as now. Nothing that pushes, publishes, deletes outside the
  repository or spends money becomes allowed.
- **Session temp directory.** Each session gets `<run_dir>/tmp/<team>/` as an extra working directory
  (`--add-dir`), with `TEMP`, `TMP` and `TMPDIR` pointing to it.
- **Denial rule in every session's system prompt:** when a command is denied, do the same another allowed way (the
  three ways above); if the phase cannot be completed without it, end with one line
  `BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <what the team proposes>`.
- **One clear question for a denial.** A work session that ends on a denial without completing its phase is
  escalated exactly once, in every work phase; the escalation names each denied command (tool and shortened input)
  and carries the session's `BLOCKED: owner` text as the question when it gave one.
- **Teams decide what their policy lets them decide.** The triage consultation prompt (`consult_prompt`) and the
  blocked-on-owner note (`BLOCKED_NOTE`) tell the deciding team: decide everything your instructions allow, record
  the decision, inform the owner without blocking, and escalate only what your instructions reserve for the owner;
  without such a policy the rule is the same as now. The triage verdict gets an optional `note_for_owner`; when it
  is non-empty the dispatcher sends the owner a non-blocking handover (`--expects ack --auto-close`, tag
  `team-decision`) from the triage team.
- **Docs.** The root README part that says what a team's `CLAUDE.md` holds gets an "Owner-only actions / decisions
  the team takes" section with neutral examples; `radark/README.md` documents the guard hook, the temp directory,
  the denial rule and the informing handover.
- No new setting.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirements for the guard hook, the session temp directory, the denial rule and the
  team-decision notice; changed requirements for the worker blocked on the owner, product triage of questions and
  escalation of a denial in an incomplete phase.

## Impact

- Code: `radark/hooks/guard.py` (new), `radark/hooks/hookcommon.py`, `radark/runner.py` (settings, `--add-dir`,
  environment, system prompt), `radark/prompts.py` (denial rule, `BLOCKED_NOTE`, `consult_prompt`,
  `VERDICT_SCHEMA`, escalation body), `radark/__main__.py` (denial escalation text, team-decision notice).
- Tests: new `radark/tests/test_guard.py`; additions to `test_denial.py`, `test_escalation.py`, `test_prompts.py`,
  `test_hooks.py`; the exact system-prompt assertion in `test_runner.py` is extended by the new rule.
- Docs: `README.md`, `radark/README.md`.
- Hub: one new kind of dispatcher-sent handover (`team-decision`, to the owner, non-blocking).
- No change to `ho`; no new dependency.
