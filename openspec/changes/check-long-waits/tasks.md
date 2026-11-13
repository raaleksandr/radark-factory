# Tasks

Change for HO-20261113-ln4m (RB-004).

## 1. Long-wait rule

- [x] 1.1 Add `long_wait_rule(idle_minutes: float) -> str` to `radark/prompts.py`: interval = max(1, floor(idle / 2)) whole minutes; the limit written with `:g`; the text per design D5 names the interval and the limit, says to check progress at least once per interval, and that two checks in a row without progress mean hung (stop it, record what was seen, continue another way or report it). Verify: unit tests in `radark/tests/test_prompts.py`: 20 → interval 10 and limit 20 named; 30 → 15; 1 → 1; 25 → 12; 2.5 → interval 1 with limit `2.5` named (non-integer limit).
- [x] 1.2 In `radark/runner.py` `Runner.command()`, pass `STANDING_RULE + "\n\n" + long_wait_rule(self.cfg.session_idle_minutes)` to `--append-system-prompt` (design D1). Verify: unit test in `radark/tests/test_runner.py` that the `--append-system-prompt` value holds both rules with the configured numbers (default 20 → 10, and a configured 30 → 15), for a new session (`--session-id`) and for a resume (`--resume`).
- [x] 1.3 Run the full suite `python -m pytest radark/tests`; all pass. Note the count and any failing or flaky tests per hub `AGENTS.md` §10. Result: 539 passed (223 s), no failing or flaky tests.

## 2. Docs

- [x] 2.1 In `radark/README.md`, "Time limits" (where `session_idle_minutes` / `idle_timeout` is described), mention the long-wait rule every session carries and the interval formula (half the limit, rounded down, at least 1 minute; 10 with the default 20). Verify: the section names the rule and the formula, and the text names no private data.

## 3. Hand back

- [x] 3.1 Commit locally (no push, tag, release or reinstall) with a message citing HO-20261113-ln4m; verify `git status` is clean.
- [x] 3.2 `ho done HO-20261113-ln4m -m "..."` listing the change name, the commit(s), the test count, the exact rule text as sent with the default 20-minute limit, and any failing or flaky tests; then `ho sync`.

## Notes

- The draft's "Workflow follow-up" item is dropped: archiving this change and syncing its delta spec happen in the separate archive phase, after the author closes HO-20261113-ln4m; they are not tasks of this change.
- Paths are updated from the draft's `harness/...` to `radark/...`; the change name drops the `harness-` prefix.
- Rounding for a non-integer `session_idle_minutes` is defined in design D2 (assumption: floor to whole minutes, limit shown as configured).
