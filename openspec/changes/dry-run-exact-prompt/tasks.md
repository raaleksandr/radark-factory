# Tasks: dry-run prints the exact prompt a session gets (HO-20261117-6i2k)

## 1. Prompt helper

- [ ] 1.1 `radark/__main__.py`: give `Dispatcher.work_prompt` a `consume: bool = True` parameter; with
  `consume=False` read the record's `unescalated_denials` without popping them (design D2)
- [ ] 1.2 Add `Dispatcher.start_prompt(cand, rec, goal, *, lock, dry=False)`: the timeout-resume message or the work
  prompt, followed by `parallel_note()` (design D1)
- [ ] 1.3 `run_candidate`: use `start_prompt` for the new-session start and the time-limit resume; keep the
  fresh-session fallback and the owner-answer prompts as they are (they already append the note)
- [ ] 1.4 `dry_run`: print `"Prompt:\n" + d.start_prompt(c, d.state.get(c.handover) or {}, goal, lock=lock, dry=True)`
  instead of building the prompt itself; no other dry-run line changes

## 2. Tests

- [ ] 2.1 `radark/tests/test_parallel.py`: dry-run with `parallel_sessions = 2` prints `prompts.PARALLEL_NOTE` in the
  prompt; with `1` it does not (no other instance on the machine)
- [ ] 2.2 The prompt printed by dry-run equals the `-p` prompt the fake `claude` receives from `once` on the same hub
  and state, for `parallel_sessions` 1 and 2
- [ ] 2.3 Same for a candidate that resumes after a time limit (`parallel_sessions = 2`)
- [ ] 2.4 Dry-run of a review candidate with stored not-escalated denials leaves the state file unchanged, and the
  denials still reach the next real review prompt (design D2, D3)
- [ ] 2.5 Run the existing dry-run tests; adjust only those that change because of the note, and list them in the
  notes

## 3. Docs and checks

- [ ] 3.1 `radark/README.md`: if it describes the dry-run prompt, say that it is exactly the session's prompt,
  including the parallel note
- [ ] 3.2 Sandbox check: `python radark/sandbox/make_sandbox.py <tmp>`, set `parallel_sessions = 2` in
  `<tmp>/radark.toml`, run `python -m radark --config <tmp>/radark.toml dry-run` and see the parallel note at the
  end of the prompt; with `1` it is absent; record the result in the notes
- [ ] 3.3 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped
- [ ] 3.4 Check that nothing private is in the diff (no owner paths, product names, hub or run excerpts)
- [ ] 3.5 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-6i2k -m "<summary>"`, naming the review-prompt assumption (design D3)

## Notes

- Assumption (unattended propose, 2026-11-17): the review prompt in dry-run becomes exact too (stored denials and
  time limits shown), read as part of "the printed prompt is exactly the session's prompt" (design D3). Posted as a
  comment on HO-20261117-6i2k.
