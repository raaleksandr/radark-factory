# Tasks

Handover: HO-20261113-bo4f. Assumptions made without the author (unattended propose): see design.md
"Deviations from the draft" and D7. Archive and spec sync are a separate phase after the author closes the handover;
they are not tasks here.

## 1. Configuration

- [x] 1.1 Add `idle_reask_minutes: int = 60` to the loop config in `radark/config.py` (read from `[loop]`, integer ≥ 0, else `ConfigError` naming the key), with tests in `radark/tests/test_config.py` (default 60, 0 accepted, negative / non-integer refused)
- [x] 1.2 Document it in `harness.toml.example` (next to `idle_ask`, with a comment) and in the `[loop]` row of `radark/README.md`

## 2. Prompts (`radark/prompts.py`)

- [x] 2.1 Replace `IDLE_PROMPT` with `idle_prompt(blocked, notice)`: the whole choice (backlog, technical debt, the team's own regular tasks by the rule and schedule its own instructions name); overdue or due-within-a-day regular task first, done by the team itself, verdict `did_regular`; keep the one-item-per-handover text and `STANDING_RULE` (D0)
- [x] 2.2 Add `did_regular` to `IDLE_SCHEMA` (D0)
- [x] 2.3 Blocked-items section in `idle_prompt`: one bullet per item (handover, team, kind, reason) and the "do not wait on a blocked item / `none` only when…" instruction; left out when the list is empty (D3)
- [x] 2.4 Add `NO_GOAL_NOTICE` and `ended_goal_notice(path, status, ended)` (status "ended without a report" and no time for a leftover `running`) (D1, D2)
- [x] 2.5 Let `phase_prompt`, `consult_prompt` (via `_with_rule` or an extra parameter) carry the no-goal block in place of the goal block (D1)
- [x] 2.6 Add the sentence "Only this run's goal sets the order of work; goals of earlier runs have ended." to `goal_check_prompt` (D6)
- [x] 2.7 Tests in `radark/tests/test_prompts.py`: idle prompt names regular tasks and the "overdue first, do it yourself" rule; blocked section present / absent; both notices; goal-check sentence; schema enum

## 3. Dispatcher (`radark/__main__.py`)

- [x] 3.1 `parse_idle_verdict` accepts `did_regular`; after it the next idle ask is due at once; `meta.idle_regular_streak` counts consecutive `did_regular` (reset by another verdict or a work session); at 3, wait as after `none` and log `idle_regular_limit` (D0)
- [x] 3.2 `end_goal()` writes `ended` (local ISO time) into `goal.json`; a helper reads the previous goal run for a run without a goal (path, status, ended, key = path + started) with the fallback for older files and for a leftover `running` (D2)
- [x] 3.3 `no_goal_for(team)`: for the product team in a run without a goal, the no-goal notice plus the ended-goal notice while `meta.goal_cleanup_done` differs from the ended run's key; pass it to the idle, phase (review/act) and triage-consultation prompts; not to resumes, limit checks or wrap-ups (D1, D7)
- [x] 3.4 Set `meta.goal_cleanup_done` after a product session that carried the ended-goal notice and did not end `interrupted` or `usage_limit` (D2)
- [x] 3.5 Pass `goal_blocked_items()` into `idle_prompt` (D3)
- [x] 3.6 Re-ask timing: in-memory `awake()` mark at the end of every session and at process start; `idle_ask()` runs when the hub moved or `awake() - mark >= idle_reask_minutes * 60` (never by time with 0); store `meta.idle_reask_at` for display (D4)
- [x] 3.7 Skip the idle escalation when the sorted `waiting_for_owner` items equal `meta.idle_escalated_items`; log `idle_escalation_skipped`; store the set when an escalation is sent (D5)
- [x] 3.8 Console line of an idle verdict: verdict and reason; for `none` (and `handed_over`) `next ask ~HH:MM` when the re-ask by time is on
- [x] 3.9 `dry-run`: in the idle state with `idle_ask` on, say when the next idle ask would come (on hub activity, or ~HH:MM / after N awake minutes); show the no-goal / ended-goal notice that the next product prompt would carry

## 4. Tests (`radark/tests`, fake `ho` and `claude` only)

- [x] 4.1 `did_regular` re-asks in the next loop without hub activity, and stops after 3 in a row with `idle_regular_limit`
- [x] 4.2 Blocked item named in the idle prompt; same owner items on a re-ask → no new escalation and `idle_escalation_skipped`; a different set → one new escalation (`test_escalation.py` / `test_dispatcher.py`)
- [x] 4.3 Re-ask timing with a fake awake clock: asked again after 60 quiet awake minutes; not before; not by time with 0; a sleep does not count (`test_sleep.py` style)
- [x] 4.4 No-goal notice in product idle / review / act / consult prompts of a run without a goal; absent in a goal run and in technical prompts (`test_goal.py`)
- [x] 4.5 Ended-goal notice: given once; kept after an interrupted session; not repeated after a note appended to the goal file; leftover `running` goal named as ended without a report; older `goal.json` without `ended`
- [x] 4.6 Run the full suite `python -m pytest radark/tests`; all green; failing or flaky tests handled per hub `AGENTS.md` §10 and listed in the result

## 5. Docs

- [x] 5.1 `radark/README.md`: idle ask (full choice incl. regular tasks, `did_regular` and its limit, blocked items, re-ask by awake time, no duplicate escalation, console line) and the goal-run section (a goal binds only its run; ended-goal notice in the next run without a goal)

## 6. Hand back

- [x] 6.1 Commit locally (no push, tag, release or reinstall); `ho done HO-20261113-bo4f` with: change name, commits, test count, `idle_reask_minutes` and its default, the exact new prompt texts (idle prompt, no-goal notice, ended-goal notice, goal-check sentence), the verdict `did_regular`, the log events `idle_regular_limit` and `idle_escalation_skipped`, and every deviation from the draft (design.md); then `ho sync`

Note (apply): the new tests are in `radark/tests/test_goal_ends_with_run.py` (prompts, `did_regular`, re-ask timing
with a fake awake clock, blocked items, duplicate escalation, no-goal and ended-goal notices, `ended`, dry-run) and
`radark/tests/test_config.py`; `test_prompts.py` only follows the rename of `IDLE_PROMPT`.
