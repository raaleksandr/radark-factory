# Tasks: start summary reports the Claude Code login state (HO-20261117-7h24)

## 1. Probe and summary line

- [ ] 1.1 In `radark/config.py`, add `CLAUDE_LOGIN_TIMEOUT = 10` and `claude_login(cfg) -> str`: run
  `cfg.claude + ["auth", "status", "--json"]` with that timeout in `os.environ` minus `ANTHROPIC_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN` (design D1); map the outcome to `logged in` / `NOT logged in - ...` /
  `login state unknown (<reason>)` from the `loggedIn` field only (design D2, D6)
- [ ] 1.2 `summary(cfg, version, ho=None, login=None)`: with `login`, the line is `Claude Code: <version>; <login>`;
  without it, unchanged (design D3)
- [ ] 1.3 In `radark/__main__.py` `main()`, call `claude_login(cfg)` once beside `claude_version(cfg)` and pass it to
  `summary` for `run`, `once` and `dry-run`; no exit code depends on it (design D4, D5)

## 2. Tests

- [ ] 2.1 Fake `claude` (`radark/tests/fakes/fake_claude.py`): answer `auth status --json` from `FAKE_CLAUDE_AUTH`
  (`in` default, `out`, `missing`, `garbage`, `sleep`), before recording calls or reading scenarios; count probes in
  a side file so tests can check "once" (design D7)
- [ ] 2.2 New `radark/tests/test_claude_login.py`: `claude_login` for logged in, not logged in (exit 1), missing
  subcommand, unreadable output, timeout (lowered `CLAUDE_LOGIN_TIMEOUT`), `claude` not found -> the exact texts of
  design D3
- [ ] 2.3 `dry-run` with logged in / not logged in / missing / timeout: the summary line, the exit code the same as
  with logged in, no session started (no scenario call recorded)
- [ ] 2.4 `once` (or `run --once`) not logged in: the run goes on (a session starts), the line is in `console.log`,
  and `auth status` was probed exactly once
- [ ] 2.5 Privacy: the fake's logged-in output carries a made-up e-mail and organisation; neither appears in stdout,
  `console.log`, the run log or the state
- [ ] 2.6 Existing tests that compare the summary (`test_config.py`, `test_ho_check.py`, `test_config_names.py`,
  `test_parallel.py`) still pass; adjust only an exact `Claude Code:` comparison, if any

## 3. Docs and checks

- [ ] 3.1 `docs/setup.md`: the healthy dry-run example shows `Claude Code: ...; logged in`; remove the "`dry-run`
  does **not** check the Claude Code login" sentence (keeping `claude auth status` as a manual check is fine); add a
  "Common errors" row for `Claude Code: ...; NOT logged in` with the fix "run `claude` and log in", noting that it
  is a warning and the start goes on (the table's intro speaks of exit code 2: say this row is the exception)
- [ ] 3.2 `radark/README.md`: where the start summary is described, mention the login state on the Claude Code line
- [ ] 3.3 Manual check: `python -m radark --config <sandbox>/radark.toml dry-run` on a sandbox made with
  `python radark/sandbox/make_sandbox.py <dir>` in the session temp directory; record the Claude Code line (neutral,
  no account details or owner paths) in the notes below
- [ ] 3.4 Full suite: `radark-test-slot python -m pytest radark/tests`; all must pass; failing or flaky tests are
  reported per hub `AGENTS.md` section 10, never retried or skipped; record the number of tests
- [ ] 3.5 Check that nothing private is in the diff (no owner paths, account details, product names, hub or run
  excerpts)
- [ ] 3.6 Commit locally (no push, tag, release or reinstall) and report with
  `ho done HO-20261117-7h24 -m "<summary>"`, naming the test count and the assumptions below

## Notes

- Assumptions (unattended propose, 2026-11-17), recorded in design.md "Assumptions": the login state is appended to
  the existing `Claude Code:` line (not a new `claude:` line); ASCII `-` instead of an em dash; `once` gets the line
  too; the probe drops the same credential variables as sessions; only the JSON `loggedIn` field decides.
- Chosen command (the handover asked to record it): `claude auth status --json`, present in Claude Code 2.1.326 on
  2026-11-17 (JSON by default, boolean `loggedIn`).
