# Tasks

## 1. Hub lock in `ho`

- [ ] 1.1 In `ho.py`, take an exclusive lock on `<hub>/.ho.lock` around write commands and `sync`, bounded wait with a clear error, released on exit (design D6); add `.ho.lock` to the hub's `.gitignore`; verify with a test in that repository that two processes running `sync`/`new` at once both succeed in order, and that read commands do not wait
- [ ] 1.2 Verify by hand in the real hub: two `ho sync` started at the same moment both succeed and the working copy is clean

## 2. Session isolation

- [ ] 2.1 Run each session in a Windows job object with kill-on-close (design D5), keeping `kill_pid_tree` as fallback; verify with a test where a fake session starts a detached background child whose parent exits, and the child is gone after the session ends; and that a second fake session's process is untouched
- [ ] 2.2 Per-session `TEMP`/`TMP` under `<run_dir>/tmp/<session_id>`, kept for a resume, removed after processing, leftovers removed at start (design D5); `HARNESS_PARALLEL` in the environment; verify with tests of `session_env` and of the cleanup
- [ ] 2.3 Parallel note in work prompts when `parallel_sessions > 1` (design D5); verify with prompt tests for 1 (no note) and 2 (note)

## 3. Parallel sessions in the dispatcher

- [ ] 3.1 `[loop] parallel_sessions` (integer ≥ 1, default 1) in `harness/config.py`; verify with config tests (default, 2, 0 refused, "two" refused)
- [ ] 3.2 `sel.pick_free` (design D2); verify with selection tests: two teams → both, same repository → one, same handover → one, held item → not picked
- [ ] 3.3 Running records per session in the state, old single record read as one; `recover()` over all (design D4); verify with recovery tests for zero, one (old format) and two records
- [ ] 3.4 Worker threads, shared lock, runner per session, SIGINT in the main thread (design D1); verify with dispatcher tests using two fake runners: both run at once, end in either order, each `after_session` updates its own record, and the run log and console have complete lines
- [ ] 3.5 Run control (design D1, spec "Run control with parallel sessions"): STOP, PAUSE, until, budget, usage hold, back-off, `--max-sessions` stop new starts and the run ends after the last worker; Ctrl+C once/twice; verify with a test per control
- [ ] 3.6 Idle ask and goal check with running work: start rule, "work in progress" list in the prompt, ending after running sessions (design D3); verify with tests
- [ ] 3.7 Console: handover on end lines, `(N running)` on start lines (design D4); verify with console tests
- [ ] 3.8 `dry-run` prints what would start in parallel ("Would start: … ; in parallel: …"); `plan` unchanged; verify with a dry-run test
- [ ] 3.9 Run the full suite (`python -m pytest harness/tests -q`) with `parallel_sessions` 1 and 2 paths covered; verify it passes

## 4. Documentation and configuration

- [ ] 4.1 `harness/README.md`: parallel sessions, isolation, hub lock, how to go back to one session; verify the text matches the delta specs
- [ ] 4.2 Draft handover from `owner` to `product` (design D7) shown to the owner; send it with `ho new` only after the owner confirms the text; verify it appears in the product team's inbox
- [ ] 4.3 Set `parallel_sessions = 2` in `harness.toml`; verify `python -m harness dry-run` shows the parallel line with the current hub

## 5. Integration

- [ ] 5.1 Visible-mode run with `app` and `backend` work at once (owner present for the start): both sessions run, no interference visible in `console.log`, both items' results processed; record here the run's duration and its flaky/infra failures next to a comparable serial run

## Workflow follow-up

- Sync the delta specs into `openspec/specs/` and archive the change after the owner accepts the integration run.
- Delete the owner's idea note `docs/ideas/parallel-teams-mode.md` (owner, 2026-11-10: not needed once this is done; its facts are in design.md Context).
