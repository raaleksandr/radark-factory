# Tasks: wrap up on demand (HO-20261120-z32m)

## 1. Request: command, file, detection

- [ ] 1.1 `wrap-up [--within MIN]` subcommand in `radark/__main__.py` (design D1): live-dispatcher check through the
  run lock's PID, `WRAP_UP` JSON written atomically, messages for written / already pending / no run (exit 1),
  `--within` > 0 (exit 2). Verify: CLI tests in `radark/tests/test_owner_wrap_up.py` (with and without a live lock,
  pending file, `--within 0`, hand-made file with non-JSON content).
- [ ] 1.2 Stale `WRAP_UP` at run start removed with the console note and `owner_wrap_up_stale` (D1). Verify: test.
- [ ] 1.3 `Dispatcher.owner_wrap_up()` detection (D2) in `ending()` (reason `wrap-up requested`), before each start
  of the one-session loop, and in the poll / `PAUSE` / usage / back-off waits. Verify: tests "request while idle"
  (the run ends at once, no session starts) for `parallel_sessions = 1` and `2`.

## 2. Acting on the request and delivery

- [ ] 2.1 `prompts.owner_wrap_up_message()` and its hard variant, sharing the end-time wrap-up's common sentences
  (D7); `INTERRUPT_LABELS["owner_wrap_up"]`. Verify: `radark/tests/test_prompts.py` checks the apply and non-apply
  texts (handover, minutes, no new work, wait for running commands, commit, `Left for a later run`, no `ho done`
  unless complete) and that the end-time text is unchanged.
- [ ] 2.2 Acting once per run (D3): `wrap-up-request.json` keyed by session run ID for running work sessions that
  are not wrap-ups, `owner_wrap_up_requested` event and console line. Verify: test with one and with two running
  sessions.
- [ ] 2.3 Hook `radark/hooks/post_tool_use.py` and the `PostToolUse` entry in `write_session_settings` (D4); `stop.py`
  delivers instead of the nudge without a marker and lets the session stop with one. Verify: hook unit tests in
  `radark/tests/test_hooks.py` (no request file → no output; listed run ID → `additionalContext` once and marker;
  unlisted run ID or `agent_id` set → nothing; `Stop` with and without marker).
- [ ] 2.4 Check the real `PostToolUse` input / output fields (`agent_id`, `hookSpecificOutput.additionalContext`)
  against the Claude Code hooks documentation and record the result in the notes below (design Risks); adjust the
  hook if a field differs. Verify: note written.
- [ ] 2.5 Fake `claude`: `PostToolUse` step that waits for a test-controlled file before running the hook and records
  the hook output as a `fake_hook` line (D10). Verify: used by the tests of group 3.

## 3. Per-session watch, safety limits, outcome

- [ ] 3.1 `Runner.run(on_tick=)` (at most once a second) with answers `OWNER_STOP` / `OWNER_HARD`, cause
  `owner_wrap_up` (D5). Verify: `radark/tests/test_runner.py` with a fake clock.
- [ ] 3.2 `owner_watch` in `session()`: delivery from markers (`owner_wrap_up_delivered`, console line), grace after
  delivery (`wrap_up_minutes`, also 0), `--within` hard stop and resume (`owner_hard_wrap_up()` sharing
  `end_time_wrap_up` code), no limit check / extension after the request, non-work sessions stopped only at
  `--within`, wrap-up sessions left alone. Verify: tests "request during a long tool call" (the fake tool call is not
  killed, the text is delivered after it, the session ends, the run ends), "grace after delivery", "within reached",
  "deadline after the request", "strict end time still applies".
- [ ] 3.3 Outcome rule (D6): keep a completed phase / `usage_limit` / `waiting_for_owner`, otherwise `interrupted` /
  `owner_wrap_up` in the step and the session record; no triage of a question; the next run resumes the item with the
  `owner_wrap_up` label. Verify: tests "phase completed during the wrap-up" and "next run resumes the item" (second
  `Dispatcher` run on the same state).

## 4. Run end and reporting

- [ ] 4.1 Run end (D8): `owner_wrap_up_done`, console line, both files removed, exit 0, goal run `stopped`, `STOP`
  first. Verify: tests for a plain run, a goal run and `STOP` + `WRAP_UP`.
- [ ] 4.2 End line cause `owner wrap-up`; `status` line for a pending request (and for a file without a run) (D9).
  Verify: console / status tests.
- [ ] 4.3 Cockpit Now: `wrap_up_pending` in `cockpit_now` and the card text (D9). Verify: `radark/tests/test_cockpit_now.py`
  cases pending / done / before the last `dispatcher_start`.

## 5. Docs and checks

- [ ] 5.1 `radark/README.md`: commands list (`wrap-up`), **Pause / stop** (request, file, `--within`, what happens,
  the stale file), **Wrap-up** (the on-demand wrap-up and its limits), the `owner_wrap_up` cause and events;
  `README.md` run-control line; `docs/setup.md` only if it lists run controls (it did not when proposed). Verify:
  docs read through; no private paths or names.
- [ ] 5.2 Manual check on a sandbox (`python radark/sandbox/make_sandbox.py <tmp>`): `wrap-up` without a running run
  (message, exit 1) and `dry-run` unchanged; record the output in the notes (no private paths). Verify: note.
- [ ] 5.3 Full suite `python -m pytest radark/tests` passes (count in the notes); failing or flaky tests handled per
  hub `AGENTS.md` §10, never hidden with retries or skips. Verify: suite output.
- [ ] 5.4 Commit locally (no push, tag, release or reinstall); `ho done HO-20261120-z32m -m "<summary with the
  number of tests>"`. Verify: `ho show HO-20261120-z32m --json` shows radark-factory done.

## Notes

- Assumptions made without an owner (see design, *Assumptions*): command `wrap-up` and file `WRAP_UP`; delivery
  through a `PostToolUse` hook (and `Stop` at a turn's end), not by stopping the session between tool calls;
  safety rule = idle / max unchanged + `wrap_up_minutes` after delivery + optional `--within MIN` hard wrap-up + no
  limit check or extension after the request; first request wins; stale file at start removed, not acted on;
  non-work sessions get no text; a goal run ends `stopped`; the cockpit Now line is in scope (simple).
