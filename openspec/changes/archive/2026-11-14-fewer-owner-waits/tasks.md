# Tasks

## 1. Verify the hook mechanism

- [x] 1.1 In a sandbox (`python radark/sandbox/make_sandbox.py <dir>`, temporary), check with one real short `claude -p --permission-mode auto` session and a throw-away `PreToolUse` hook that (a) a `deny` with `permissionDecisionReason` shows the reason to the model and is recorded in `permission_denials`, (b) an `allow` lets a command run that the auto mode would deny (e.g. `git checkout -- <file>`). Record the result in design D1 (keep or switch to the fallback). Do not commit the sandbox.

## 2. Session environment and temp directory

- [x] 2.1 `runner.py`: create `<run_dir>/tmp/<team>/` before every session (new and resumed), add `--add-dir <it>` to the command, set `TEMP`/`TMP`/`TMPDIR` to it, and add `HARNESS_REPO`, `HARNESS_TEMP`, `HARNESS_SYSTEM_TEMP` (original values) to `session_env` (design D5, D7). Verify with a `test_runner.py` test on the command line and environment of a new and a resumed session.
- [x] 2.2 `prompts.py`: `denial_rule(temp_dir)` with the text of design D6; the runner appends it after the long-wait rule. Extend the exact system-prompt assertion in `test_runner.py` by the rule and add a test that the rule names the team's temp directory and the `BLOCKED: owner — denied: …` format.

## 3. Guard hook

- [x] 3.1 `radark/hooks/guard.py` (+ helpers in `hookcommon.py`): single-simple-command check (D2); discard rule (D3); stop-process rule with the process tree of `os.getppid()` (D4); temp rule for `Write`/`Edit`/`Bash`/`PowerShell` (D5); exact reason texts from the design; no output when nothing matches.
- [x] 3.2 Register `guard.py` in `write_session_settings` for the matchers `Bash`, `PowerShell`, `Write`, `Edit`; verify in `test_hooks.py` that the settings file lists it in exec form.
- [x] 3.3 New `radark/tests/test_guard.py` (feeding JSON on stdin like `test_hooks.py`): (a) each routine denial yields a deny whose reason names the allowed way — `git checkout -- .`, `git restore ../x`, `Stop-Process -Name node`, `taskkill /IM node.exe`, a foreign PID, `Write` to the system temp dir, a PowerShell command writing to the system temp dir; allowed narrow forms — `git restore -- <tracked file>`, `git checkout -- <file>`, `Stop-Process -Id <pid of a child of the hook's parent>` (spawn a real child process in the test); no decision for `git push`, `git status`, a restore chained with `;`/`&&`, a write into the repository or the session temp dir. Process-table lookup is injectable so the tree test does not depend on PowerShell timing.

## 4. One clear question for a denial

- [x] 4.1 `__main__.py` `after_session`: for an escalated denial session parse the last `BLOCKED: owner — …` in every work phase; reason keeps `permission denied: <tool>`; question = the BLOCKED text or the composed question of design D8; `prompts.escalation_body` gets a `## Denied` section from `denial_entry`. Exactly one `escalate()` per session end.
- [x] 4.2 Tests in `test_denial.py` / `test_escalation.py` with the fake `claude`: (b) an apply session with a denial, not `done`, ending with a `BLOCKED: owner — denied: …` line → exactly one `ho new --tag escalation` whose body has the denied command and the question text; a propose session with a denial and no change and no BLOCKED line → one escalation with the composed question; three denials → one escalation listing all three. Existing denial tests stay unchanged and pass.

## 5. Teams decide what their policy allows

- [x] 5.1 `prompts.py`: extend `BLOCKED_NOTE` and `consult_prompt` with the texts of design D9; add the optional `note_for_owner` to `VERDICT_SCHEMA`. Test (c) in `test_prompts.py`: apply, act and consult prompts contain the "decide what your instructions allow / inform the owner non-blocking (`--expects ack`) / escalate only what is reserved for the owner" text; a verdict without `note_for_owner` still validates.
- [x] 5.2 `__main__.py`: after a valid `technical`/`product` verdict with a non-empty `note_for_owner`, send the team-decision notice (design D10: from the triage team, `--expects ack --auto-close --tag team-decision`, no `--ref`), then `ho sync`; log `team_decision_sent` / `team_decision_send_failed`; resume the asking session either way. Tests in `test_escalation.py` (or a new `test_team_decision.py`): note → one such `ho new` with the exact flags, no item held, session resumed; empty or missing note → no `ho new`; failed `ho new` → logged, `!` line, session still resumed.

## 6. Docs

- [x] 6.1 `radark/README.md`: the guard hook (what is allowed and why it is safe, what is denied with which reason), the session temp directory (`<run_dir>/tmp/<team>/`, never cleaned by the dispatcher), the denial rule, the `## Denied` part of a denial escalation, the team-decision notice and its log events, and that the owner should not keep uncommitted manual work in a team repository while a pipeline runs. Neutral examples only.
- [x] 6.2 Root `README.md`, where it says what a team's `CLAUDE.md` holds: add an "Owner-only actions / decisions the team takes" section with neutral examples (owner-only: publishing, pushing, spending, credentials, legal; team decides: a choice between technical options it already recommended, test strategy, the order of its own work), and that the engine's prompts tell teams to follow it; setting a pipeline's policy is the owner's task.

## 7. Verify and hand back

- [x] 7.1 Run the full suite `python -m pytest radark/tests`; all pass (d: existing tests pass unchanged except the system-prompt assertion extended in 2.2). Note the count and any failing or flaky tests per hub `AGENTS.md` §10.
- [x] 7.2 Check that nothing private landed in the repository (no owner paths, product names, hub IDs other than this handover's in commit messages, run excerpts).
- [x] 7.3 Commit locally (no push, tag, release or reinstall) with messages citing HO-20261113-armh; verify `git status` is clean.
- [x] 7.4 `ho done HO-20261113-armh -m "..."` listing: the change name, the commits, the test count, new settings (none), the exact new prompt and hook texts (denial rule, guard reasons, `BLOCKED_NOTE` addition, consult addition), what is now allowed and why it is safe, the outcome of task 1.1, and any failing or flaky tests; then `ho sync`.

## Notes

- Assumptions (unattended, no user): one change, not split; guard is a `PreToolUse` hook and the allow path depends on task 1.1 (fallback in design D1); narrow allows for named-file discards and own-process stops, deny-with-reason for temp writes; one temp directory per team under the run directory, never cleaned by the dispatcher; no new setting; the owner is informed by a `team-decision` notice only from triage verdicts with `note_for_owner`; work sessions inform the owner with their own `ho new --expects ack --auto-close`.
- Archiving this change and syncing its delta spec happen in the separate archive phase after radark-product closes the handover; they are not tasks of this change.
