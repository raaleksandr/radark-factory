# Tasks: add-setup-guide (HO-20261117-d7uw, RB-009)

## 1. Facts from the current code

- [ ] 1.1 Collect what the guide states from the code, not from memory: the Python requirement (`pyproject.toml`),
      the tested Claude Code version (README), the install line, the `ho --version --json` answer and contract, the
      start-check messages (`radark/hub.py`, `radark/config.py`), the `ho init` syntax (`ho init --help`), the
      minimum `radark.toml` keys, the run directory default, `run --until`, the console / `console.log` / cockpit,
      the escalation answer path (`radark/README.md` "Owner workflow (escalations)").
- [ ] 1.2 Decide how the sandbox script runs from an installed release (design D4): try
      `python -m radark.sandbox.make_sandbox <dir>` and the package-data path; document only what works, else the
      manual way, and note the gap for the `ho done` summary.
- [ ] 1.3 Check what a user sees when Claude Code is not found and when it is not logged in (design D7); note
      whether `dry-run` detects a missing login.

## 2. The guide

- [ ] 2.1 Write `docs/setup.md` "Setup from zero" with the eight sections in order (spec *Sections of the guide*):
      Prerequisites, Install, Hub, Team repositories, Configuration, First dry run, The sandbox, First real run.
- [ ] 2.2 Team repositories: the copy-paste `CLAUDE.md` template (role, hub / team, `ho sync` first and last,
      `$HO_HUB/AGENTS.md`, owner-only actions / decisions the team takes, work process / profile, tests), the
      `.claude/settings.json` example (`env` `HO_HUB` / `HO_TEAM`), `openspec init --tools claude` for the
      `openspec` profile, the product team.
- [ ] 2.3 First dry run: a short neutral example of a healthy output and the common errors with their real message
      start and fix (hub not found, team path wrong, `ho` incompatible, `owner_team` not in the hub, Claude Code not
      found / not logged in).
- [ ] 2.4 Link instead of repeating (design D2); Windows vs POSIX differences only where they matter (design D8).
- [ ] 2.5 `README.md`: a link at the top and in "Quick start"; optionally a one-line link from `radark/README.md`
      "Setup".

## 3. Verification

- [ ] 3.1 Follow the guide literally in a scratch directory under the session's temporary directory (not in this
      repository; install nothing): local hub, two team repositories from the template, `radark.toml` from the
      example, `radark dry-run` until green. Fix the guide where a literal step fails. Record which steps were run.
- [ ] 3.2 Run the sandbox section as written, up to a green `dry-run`.
- [ ] 3.3 Check every command and flag in the guide against `--help` / the code (spec *The guide links instead of
      repeating*).
- [ ] 3.4 Public-repository check: search the diff for owner paths, product / pipeline / company names and real hub
      or run excerpts; only neutral names, made-up IDs, `D:\work\my-factory` / `~/work/my-factory`.
- [ ] 3.5 Full test suite: `radark-test-slot python -m pytest radark/tests`; failing / flaky tests per hub
      `AGENTS.md` §10 (report them, never hide them).
- [ ] 3.6 If the radark-handover README lacks something the guide needs (e.g. a local hub without a remote), send a
      handover to `radark-handover` instead of a workaround (expected: not needed).

## 4. Report

- [ ] 4.1 Commit locally (no push, tag, release or reinstall).
- [ ] 4.2 `ho done HO-20261117-d7uw -m "<summary: guide location, steps run literally and their result, sandbox
      invocation, test result, any gap for product>"`; `ho sync`.

Notes: archiving the change and syncing its specs are not part of these tasks; they run in a separate phase after
`radark-product` closes the handover. Assumptions made unattended are listed in design.md "Open questions".
