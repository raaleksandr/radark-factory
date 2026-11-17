# Design: start summary reports the Claude Code login state (HO-20261117-7h24)

## Context

The start summary (`config.summary`) prints `Claude Code: <claude --version>`; `__main__.main` calls
`config.claude_version(cfg)` once before the summary of `run`, `once` and `dry-run`. Sessions run on the owner's
Claude Code login; `runner.session_env` removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from their
environment. Nothing checks the login before the first session.

The installed Claude Code (2.1.326 on 2026-11-17) has `claude auth status [--json | --text]`, "Show authentication
status", JSON by default. Its JSON object has a boolean `loggedIn` (plus `authMethod`, `apiProvider` and account
fields such as e-mail and organisation). It runs no model and spends no tokens.

## Goals / Non-Goals

**Goals:** one line about the login in the start summary of `run`, `once`, `dry-run`; no session, no tokens; a
warning only; one probe per start.

**Non-Goals:** refusing to start without a login; re-checking during a run; reporting the account, plan or auth
method; changing the `plan`, `status` or `--version` output; a configuration key to turn the probe off.

## Decisions

### D1: Command `claude auth status --json`, 10 s limit

The probe runs `cfg.claude + ["auth", "status", "--json"]` (the configured `claude` command, like the version
probe) with `capture_output`, `text` and a 10 s timeout, in the process environment without `ANTHROPIC_API_KEY`
and `ANTHROPIC_AUTH_TOKEN` (the same two keys `runner.session_env` drops), so the answer matches what a session
would see. `--json` is passed explicitly even though it is the default, so a future default change does not break
parsing.

Alternatives: `claude -p "ping"` (starts a session and spends tokens - ruled out by the handover); reading Claude
Code's credential files (undocumented, private, platform-specific).

### D2: Interpretation

- stdout parses as a JSON object with a boolean `loggedIn`: `true` -> `logged in`; `false` -> `NOT logged in`,
  whatever the exit code.
- anything else -> `unknown`, with a short reason in parentheses:
  - the command cannot be started (`OSError`), or it exits non-zero without such JSON (e.g. an older Claude Code
    that rejects `auth`) -> ``(`claude auth status` not available)``;
  - no answer within 10 s -> ``(`claude auth status` timed out)``;
  - exit 0 but no JSON object with a boolean `loggedIn` -> ``(`claude auth status` gave no readable answer)``.

The exit code alone never decides the state: only the JSON field does. An unknown output is never reported as a
login or as a missing login.

### D3: Line format - extend the existing `Claude Code:` line

The handover's examples use `claude: <version>; ...`. The summary already has `Claude Code: <version>`, and
`test_ho_check`, `radark/README.md` and `docs/setup.md` refer to it, so the login state is appended to that line
after `; ` instead of renaming it:

```
Claude Code: 2.1.326 (Claude Code); logged in
Claude Code: 2.1.326 (Claude Code); NOT logged in - run `claude` and log in (sessions would fail)
Claude Code: 2.1.326 (Claude Code); login state unknown (`claude auth status` not available)
```

A plain ASCII hyphen replaces the handover's em dash, so a Windows console with a legacy code page prints it
cleanly. The `ho:` line stays right after it (requirement "Reporting the ho version").

`summary(cfg, version, ho=None, login=None)`: `login` is the text after `; `; with `None` the line is as before, so
existing callers and tests keep their output.

### D4: Where and how often

`__main__.main` calls `config.claude_login(cfg)` once, next to `claude_version(cfg)`, right before printing the
summary (after the banner, i.e. after every check that refuses a start, so a refused start does not wait for the
probe). The result is not stored and not repeated during the run; in `run`/`once` mode it reaches `console.log`
with the rest of the summary. No separate run-log event.

### D5: Warning, not a check

No exit code changes: `dry-run` and `run` exit as before in every login state, and `run` goes on to its loop when
not logged in (another setup, e.g. an `apiKeyHelper` in Claude Code settings, may still work). The line is the only
effect.

### D6: Privacy

Only `loggedIn` is read from the JSON. The rest of the status output (e-mail, organisation, plan, directories) is
never printed, logged, stored in state or put into a reason; an unreadable output is reported by its kind, not by
its text.

### D7: Tests

The fake `claude` answers `auth status --json` before it records calls or reads scenarios, from
`FAKE_CLAUDE_AUTH`: `in` (default; `{"loggedIn": true, ...}` with made-up account fields, exit 0), `out`
(`{"loggedIn": false}`, exit 1), `missing` (an "unknown command" error on stderr, exit 1), `garbage` (non-JSON
stdout, exit 0), `sleep` (sleeps longer than the limit). Each probe is counted in a side file so a test can check
"once". The probe limit is a module constant (`CLAUDE_LOGIN_TIMEOUT`) that tests lower. A `claude` that is not
found is tested with a command that does not exist. The default `in` keeps every existing test's output unchanged
apart from the appended `; logged in`.

## Risks / Trade-offs

- An older or newer Claude Code may change `auth status` -> reported as `unknown`, never as a wrong state (D2).
- The probe can add up to 10 s to a start when Claude Code hangs; normally it answers in well under a second.
- `loggedIn: true` does not prove the token is still accepted by the server; it is what Claude Code itself
  believes, the best read-only signal available without spending tokens.

## Assumptions (unattended propose, 2026-11-17)

- The login state is appended to the existing `Claude Code:` line instead of a new `claude:` line (D3).
- ASCII `-` instead of the em dash in the "NOT logged in" line (D3).
- `once` shares the summary, so it gets the line too.
- The probe environment drops the same two credential variables as sessions (D1).
- Only the JSON `loggedIn` field decides, not the exit code (D2). The installed version's not-logged-in output could
  not be observed without logging the owner out; the fake follows the same shape with `loggedIn: false`.
