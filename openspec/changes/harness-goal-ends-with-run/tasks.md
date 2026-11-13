# Tasks

## 1. Configuration

- [ ] 1.1 Add `idle_reask_minutes: int = 60` to the loop config in `harness/config.py` (read from `[loop]`, must be ≥ 0), with a test in `test_config.py`
- [ ] 1.2 Document it in `harness.toml.example` and set `idle_reask_minutes = 60` with a comment in `harness.toml`

## 2. Prompts

- [ ] 2.0 Rewrite the idle prompt as the whole choice: backlog, technical debt and the team's own regular tasks by its usual rule; overdue or due-within-a-day regular task first, done by the team itself; add `did_regular` to `IDLE_SCHEMA` (D0)
- [ ] 2.1 Add `NO_GOAL_NOTICE` and `ended_goal_notice(path, status, ended)` to `harness/prompts.py` (D1, D2)
- [ ] 2.2 Turn `IDLE_PROMPT` into `idle_prompt(blocked, notice)`: blocked-items section with the "do not wait on a blocked item" instruction, left out when empty (D3)
- [ ] 2.3 Add the "only this run's goal counts" sentence to `goal_check_prompt` (D6)
- [ ] 2.4 Tests in `test_prompts.py` for the notices, the blocked section (present / absent) and the goal-check sentence

## 3. Dispatcher

- [ ] 3.0 `parse_idle_verdict` accepts `did_regular`; after it the next idle ask is due at once; after 3 consecutive `did_regular` wait as after `none` and log `idle_regular_limit` (D0)
- [ ] 3.1 `end_goal()` writes `ended` (local ISO time) into `goal.json`; helper reads the ended goal (path, status, ended, hash) with the fallback for older files (D2)
- [ ] 3.2 In a run without a goal, append the no-goal notice to the product team's idle, review and act prompts, plus the ended-goal notice until `meta.goal_cleanup_done` equals that goal's hash; set it after a session that is not `interrupted` or `usage_limit` (D1, D2)
- [ ] 3.3 Pass `goal_blocked_items()` into the idle prompt (D3)
- [ ] 3.4 Track awake idle time since the last session (`meta.idle_awake_s`, reset on session start, slept time not counted) and run the idle ask when the hub moved or the time reached `idle_reask_minutes` (D4)
- [ ] 3.5 Skip the owner escalation when `waiting_for_owner` is the same set as `meta.idle_escalated_items`; log `idle_escalation_skipped` (D5)
- [ ] 3.6 Console line of a `none` verdict: reason and `next ask ~HH:MM` when the re-ask by time is on
- [ ] 3.7 `dry-run` mentions the next idle re-ask time when one is due by time

## 4. Tests

- [ ] 4.0 Idle prompt names regular tasks and the "overdue first, do it yourself" rule; `did_regular` verdict re-asks at once and stops after 3 in a row
- [ ] 4.1 `test_dispatcher.py` / `test_escalation.py`: blocked item named in the idle prompt; same owner items on a re-ask send no new escalation; a different set sends one
- [ ] 4.2 Re-ask timing: asked again after 60 quiet awake minutes; not asked with 0; sleep does not count (`test_sleep.py` style fake clock)
- [ ] 4.3 No-goal notice present in a run without a goal and absent in a goal run; ended-goal notice given once and kept after an interrupted session (`test_goal.py`)
- [ ] 4.4 Run the full harness test suite; all green

## 5. Docs

- [ ] 5.1 `harness/README.md`: idle ask (blocked items, re-ask by time, no duplicate escalation) and goal-run section (a goal binds only its run; cleanup notice in the next run)
