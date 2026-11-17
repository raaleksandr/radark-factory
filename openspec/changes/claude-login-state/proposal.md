# Proposal: start summary reports the Claude Code login state (HO-20261117-7h24)

Handover: HO-20261117-7h24 ("RB-030: dry-run/run report the Claude Code login state"), from the product team.

## Why

`radark dry-run` prints only `claude --version`. A missing or expired Claude Code login shows only when the first
real session starts, often after the owner has walked away from the computer. `docs/setup.md` says so explicitly
("`dry-run` does **not** check the Claude Code login").

## What Changes

- The `Claude Code:` line of the start summary of `run`, `once` and `dry-run` (also `run --once`, `run --dry-run`)
  gets the login state after the version, from one read-only probe `claude auth status --json` (no session, no
  tokens, 10 s limit):
  ```
  Claude Code: 2.1.326 (Claude Code); logged in
  Claude Code: 2.1.326 (Claude Code); NOT logged in - run `claude` and log in (sessions would fail)
  Claude Code: 2.1.326 (Claude Code); login state unknown (`claude auth status` not available)
  ```
- It is a **warning**, not a start check: exit codes and the rest of the start are unchanged; a missing login does
  not stop `run`. A missing, failing, silent or unreadable status command prints the "unknown" form and the start
  goes on.
- One probe per start; no repeated checks during a run.
- Only the `loggedIn` field of the status output is used; nothing else of it (account, organisation, e-mail) is
  printed, logged or stored.
- `docs/setup.md`: drop the "does not check the login" sentence; add the "NOT logged in" line with its fix to the
  "Common errors" table (marked as a warning that does not stop the start); the healthy example shows `; logged in`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirements "Reporting the Claude Code login state" (the three line forms), "Login
  probe" (command, limit, one probe per start, privacy of the status output) and "Login state is a warning".
- `setup-guide`: "Configuration and first dry run in the guide" — the dry-run example shows the login state, and the
  common errors list the "NOT logged in" warning with its fix.

## Impact

- Code: `radark/config.py` (`claude_login()` probe next to `claude_version()`, `summary()` takes the login text),
  `radark/__main__.py` (one probe at the start summary).
- Tests: fake `claude` learns `auth status --json` (driven by an environment variable); new
  `radark/tests/test_claude_login.py`.
- Docs: `docs/setup.md`, `radark/README.md` (start summary description).
- No new dependency, no configuration key, no change to sessions or their environment.
