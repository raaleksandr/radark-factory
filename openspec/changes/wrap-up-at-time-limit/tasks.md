# Tasks

Change for HO-20261113-5lbl (RB-015). Design: W1–W7.

## 1. Setting

- [x] 1.1 In `radark/config.py`, add `wrap_up_minutes: float = 15` read from `[loop]`, validated `>= 0` (message names `loop.wrap_up_minutes`); add it to the sandbox `harness.toml` if that file lists `[loop]` keys. Verify: `radark/tests/test_config.py`: default 15, explicit value read, `-1` → config error naming the key, `0` accepted.

## 2. Runner

- [x] 2.1 In `radark/runner.py`, add the `WRAP_UP` sentinel and `SessionResult.extensions_used: int = 0`; when `on_deadline` answers `WRAP_UP`, end the process tree with `interrupt_cause = "wrap_up"` (no `timeout_reason`), per design W3. `classify` gives `interrupted`. Verify: a runner-level test with a fake `on_deadline` returning `WRAP_UP` → `interrupt_cause == "wrap_up"`, `outcome == "interrupted"`, `timed_out` false; existing `None` / seconds answers unchanged.

## 3. Dispatcher

- [x] 3.1 In `radark/__main__.py` `limit_watch`: return an `on_deadline` for every work session when `wrap_up_minutes > 0` (also without a product team or with `limit_checks = 0`, answering `WRAP_UP` without a check); answer `WRAP_UP` instead of `None` when the extensions are used up; keep `None` for `hung` and for no valid verdict; set `r.extensions_used` (design W2, W3).
- [x] 3.2 In `Dispatcher.session()`, add a `wrap_up` keyword: when `True`, `timeout_s = wrap_up_minutes * 60` and no `limit_watch`. After `runner.run()`, when `r.interrupt_cause == "wrap_up"`, do design W4 steps 1–5 (log `wrap_up_start`, console `!` line, record the first part, run the wrap-up resume with `prompts.wrap_up_message`, log `wrap_up`, return the wrap-up result). Make sure the first part's `interrupted` outcome does not set `resume_after_timeout` or any other item state that the returned result decides.
- [x] 3.3 Keep the item's `time_limits` history (design W6.2): append for each wrap-up (kind `wrap_up`, outcome of the wrap-up session) and for each work session ended by `max_time` or `idle_timeout` (kind `cut`), with extensions used and elapsed time.

## 4. Prompts

- [x] 4.1 In `radark/prompts.py`, add `wrap_up_message(c, minutes, extensions, grace, index_lock=False, goal=None)` with the exact text of design W5 (apply and other-phase parts), and the review paragraph of design W6.3 built from `time_limits` (`phase_prompt` review gets it when the record has history; pass it the same way as `unescalated_denials`). Verify: `radark/tests/test_prompts.py` checks both texts verbatim, the singular/plural of extensions, the lock note, the apply part with `ho done <ID>` and `APPLY_NO_ARCHIVE`, a review prompt without history has no paragraph.

## 5. Tests (fake `claude`, `test_limit_check.py` style) — new `radark/tests/test_wrap_up.py`

- [x] 5.1 (a) progressing session, all extensions used → wrap-up session starts with `--resume` of the same session and the wrap-up prompt; a fake wrap-up that finishes within the grace → step outcome `finished`, no `max_time`, run log `wrap_up_start` / `wrap_up` with extensions used, grace and outcome; console line shown.
- [x] 5.2 (b) wrap-up session that keeps running → ended by `max_time` after the grace; `wrap_up` records it; with progress the item gets `resume_after_timeout` as today.
- [x] 5.3 (c) `limit_checks = 0` → wrap-up at `session_max_minutes`, no limit check session started; also no product team → wrap-up.
- [x] 5.4 (d) check answers `hung` → cut by `max_time`, no wrap-up session; failed check → same.
- [x] 5.5 (e) the signal: after a wrap-up (and after a cut), the review prompt of that handover contains the time-limit paragraph naming it; without history no paragraph. `wrap_up_minutes = 0` → cut as before.
- [x] 5.6 Adjust existing tests in `test_limit_check.py` (and others) that expect a cut after the extensions are used up or with `limit_checks = 0`: set `wrap_up_minutes = 0` there where the test is about the cut, or update the expectation; do not weaken what they check.
- [x] 5.7 Run the full suite `python -m pytest radark/tests`; all pass. Note the count and any failing or flaky tests per hub `AGENTS.md` §10. Result: 584 passed, no failing or flaky test.

## 6. Docs

- [x] 6.1 In `radark/README.md` "Time limits" and "Limit check": the wrap-up (when it happens and when not), `wrap_up_minutes` (default 15, 0 = off), the stop-and-resume mechanism and its limit (the running step is lost), the `wrap_up_start` / `wrap_up` events and console lines, the `time_limits` history and the review paragraph. Add the setting wherever `[loop]` keys are listed. Neutral examples only, no private data.

## 7. Hand back

- [ ] 7.1 Commit locally (no push, tag, release or reinstall) with messages citing HO-20261113-5lbl; verify `git status` is clean.
- [ ] 7.2 `ho done HO-20261113-5lbl -m "..."` listing: the change name, the commits, the test count, the new setting with its default, the exact wrap-up prompt text, how the product team sees the signal (log events, console, review paragraph text), and any failing or flaky tests; then `ho sync`.

## Notes

- Assumptions (no user available): stop-and-resume rather than streaming input (W1); a failed or malformed limit check stays a cut without a wrap-up, like `hung` (W2); work sessions without a product team also wrap up (W2); default grace 15 min, 0 turns it off (W7); the signal is run log + console + a review-prompt paragraph from the item's state history (W6), no `ho` change.
- Apply notes: the sandbox `harness.toml` lists only a few `[loop]` keys (not the limit-check ones), so `wrap_up_minutes` is not added there (task 1.1). The wrap-up session's own cut is recorded in the single `wrap_up` history entry (its `reason` is `max_time`), not as a second `cut` entry. The existing tests in `test_limit_check.py` run with `wrap_up_minutes = 0` (they are about the cut); the wrap-up paths are covered in `test_wrap_up.py`. The review prompt keeps the history (it is not dropped after a review), so a returned and re-reviewed handover names it again.
- Archiving this change and syncing its delta spec happen in the separate archive phase after radark-product closes the handover; they are not tasks of this change.
