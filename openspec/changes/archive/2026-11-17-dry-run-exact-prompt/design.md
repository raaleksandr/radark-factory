# Design: dry-run prints the exact prompt a session gets (HO-20261117-6i2k)

## Context

`Dispatcher.run_candidate` (`radark/__main__.py`) starts a work session with
`work_prompt(cand, rec, goal) + parallel_note()`, or, for a resume after a time limit,
`prompts.timeout_resume_message(...) + parallel_note()`. `dry_run` prints
`prompts.timeout_resume_message(...)` or `prompts.phase_prompt(c, goal, no_goal=..., profile=...)` without the note.
Besides the missing note, the review prompt differs: the real path passes the record's stored not-escalated
denials and `time_limits` (and pops the denials), `dry_run` passes neither.

## Decisions

### D1. One helper: `Dispatcher.start_prompt(cand, rec, goal, *, lock, dry=False) -> str`

Returns the full prompt of the first session of a work item:

- `cand.timeout_resume` set: `prompts.timeout_resume_message(cand, cand.timeout_resume, lock, goal, profile)`;
- otherwise `self.work_prompt(cand, rec, goal, consume=not dry)`;

followed by `self.parallel_note()`. `run_candidate` calls it for its new-session start and its time-limit resume
(passing the `lock` it already computes; `False` for the new-session start, which does not use it); `dry_run`
calls it with `dry=True` and prints `"Prompt:\n" + start_prompt(...)`.

The fresh-session fallback after a failed resume (in `run_candidate` and in the owner-answer path) and the
owner-answer resume keep their composition (`... + parallel_note()`); dry-run does not print those prompts, so per
the handover they get no new output.

Alternative rejected: appending `parallel_note()` in `dry_run` only. It fixes the symptom but keeps two places that
build the prompt, which is what let them drift.

### D2. Read-only for dry-run

`work_prompt` gets `consume: bool = True`. With `consume=False` it reads `rec.get("unescalated_denials")` instead
of popping it. `dry_run` passes `d.state.get(c.handover) or {}` (no `state.ensure`, which would add a record), so
dry-run changes neither the state in memory nor the state file.

### D3. Review prompts become exact too (assumption)

Because dry-run now uses the same helper, a review candidate whose record holds not-escalated denials or time
limits shows those blocks in the dry-run prompt, as the real session would get them. The handover says "no other
change to dry-run output"; we read that as "no new lines or sections outside the prompt", while the prompt being
exactly the real one is the handover's goal. Assumption made unattended (2026-11-17), posted as a comment on
HO-20261117-6i2k; if product objects, `start_prompt(dry=True)` can leave those blocks out instead.

### D4. Test-slot note

`parallel_note()` also adds the test-slot note when another dispatcher's session runs on the computer
(machine-wide-instances D8). `main` sets `d.machine` before calling `dry_run`, so the printed prompt carries that
note exactly when the real one would. No separate handling.

## Risks

- Existing dry-run tests that compare the whole prompt with `parallel_sessions > 1` change; tests with
  `parallel_sessions = 1` and no other instance stay byte-for-byte the same.
