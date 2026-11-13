# Tasks

## 1. Long-wait rule

- [ ] 1.1 Add `long_wait_rule(idle_minutes)` to `harness/prompts.py`: interval = max(1, floor(idle / 2)); the text names the interval and the limit, says to check progress at least once per interval, and says that two checks without progress mean hung (stop it, record what was seen, continue another way or report it). Verify: unit test for 20 → 10, 30 → 15 and 1 → 1.
- [ ] 1.2 In `harness/runner.py`, append the rule to `STANDING_RULE` in `--append-system-prompt`, using `cfg.session_idle_minutes`. Verify: unit test on `command()` that the system prompt holds both rules with the configured numbers.
- [ ] 1.3 Run the harness test suite (`python -m pytest harness/tests -q`); all pass.

## 2. Docs

- [ ] 2.1 Mention the long-wait rule in `harness/README.md` where the inactivity limit is described. Verify: the section names the rule and the interval formula.

## Workflow follow-up

- After owner acceptance: archive the change and sync the `harness-dispatcher` spec.
