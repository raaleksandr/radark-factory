# Tasks: dry-run prints the exact prompt a session gets (HO-20261117-6i2k)

## 1. Prompt helper

- [x] 1.1 `radark/__main__.py`: give `Dispatcher.work_prompt` a `consume: bool = True` parameter; with
  `consume=False` read the record's `unescalated_denials` without popping them (design D2)
- [x] 1.2 Add `Dispatcher.start_prompt(cand, rec, goal, *, lock, dry=False)`: the timeout-resume message or the work
  prompt, followed by `parallel_note()` (design D1)
- [x] 1.3 `run_candidate`: use `start_prompt` for the new-session start and the time-limit resume; keep the
  fresh-session fallback and the owner-answer prompts as they are (they already append the note)
- [x] 1.4 `dry_run`: print `"Prompt:\n" + d.start_prompt(c, d.state.get(c.handover) or {}, goal, lock=lock, dry=True)`
  instead of building the prompt itself; no other dry-run line changes

## 2. Tests

- [x] 2.1 `radark/tests/test_parallel.py`: dry-run with `parallel_sessions = 2` prints `prompts.PARALLEL_NOTE` in the
  prompt; with `1` it does not (no other instance on the machine)
- [x] 2.2 The prompt printed by dry-run equals the `-p` prompt the fake `claude` receives from `once` on the same hub
  and state, for `parallel_sessions` 1 and 2
- [x] 2.3 Same for a candidate that resumes after a time limit (`parallel_sessions = 2`)
- [x] 2.4 Dry-run of a review candidate with stored not-escalated denials leaves the state file unchanged, and the
  denials still reach the next real review prompt (design D2, D3)
- [x] 2.5 Run the existing dry-run tests; adjust only those that change because of the note, and list them in the
  notes

## 3. Docs and checks

- [x] 3.1 `radark/README.md`: if it describes the dry-run prompt, say that it is exactly the session's prompt,
  including the parallel note
- [x] 3.2 Sandbox check: `python radark/sandbox/make_sandbox.py <tmp>`, set `parallel_sessions = 2` in
  `<tmp>/radark.toml`, run `python -m radark --config <tmp>/radark.toml dry-run` and see the parallel note at the
  end of the prompt; with `1` it is absent; record the result in the notes
- [x] 3.3 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped
- [x] 3.4 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [x] 3.5 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-6i2k -m "<summary>"`, naming the review-prompt assumption (design D3)

## Notes

- Assumption (unattended propose, 2026-11-17): the review prompt in dry-run becomes exact too (stored denials and
  time limits shown), read as part of "the printed prompt is exactly the session's prompt" (design D3). Posted as a
  comment on HO-20261117-6i2k.
- Apply (2026-11-17): new tests in `radark/tests/test_parallel.py` (`test_dry_run_prints_the_parallel_note`,
  `test_dry_run_prompt_equals_the_real_prompt`, `test_dry_run_prompt_equals_the_real_resume_prompt`,
  `test_dry_run_of_a_review_leaves_the_state_unchanged`); the parallel ones fail against the previous code. No
  existing dry-run test needed a change (task 2.5): none compared the whole prompt with `parallel_sessions > 1`.
- Sandbox check (task 3.2), with one handover for `app` and a sandbox-local machine directory: with
  `parallel_sessions = 2` the printed prompt ends with the parallel note and the test-slot note; with `1` it carries
  neither.
- The real start also passes `lock=False` for a new-session start (the flag is used only by the resume message).
- Full suite (task 3.3): 1019 passed via radark-test-slot.
