# Tasks: add-setup-guide (HO-20261117-d7uw, RB-009)

## 1. Facts from the current code

- [x] 1.1 Collect what the guide states from the code, not from memory: the Python requirement (`pyproject.toml`),
      the tested Claude Code version (README), the install line, the `ho --version --json` answer and contract, the
      start-check messages (`radark/hub.py`, `radark/config.py`), the `ho init` syntax (`ho init --help`), the
      minimum `radark.toml` keys, the run directory default, `run --until`, the console / `console.log` / cockpit,
      the escalation answer path (`radark/README.md` "Owner workflow (escalations)").
- [x] 1.2 Decide how the sandbox script runs from an installed release (design D4): try
      `python -m radark.sandbox.make_sandbox <dir>` and the package-data path; document only what works, else the
      manual way, and note the gap for the `ho done` summary.
- [x] 1.3 Check what a user sees when Claude Code is not found and when it is not logged in (design D7); note
      whether `dry-run` detects a missing login.

## 2. The guide

- [x] 2.1 Write `docs/setup.md` "Setup from zero" with the eight sections in order (spec *Sections of the guide*):
      Prerequisites, Install, Hub, Team repositories, Configuration, First dry run, The sandbox, First real run.
- [x] 2.2 Team repositories: the copy-paste `CLAUDE.md` template (role, hub / team, `ho sync` first and last,
      `$HO_HUB/AGENTS.md`, owner-only actions / decisions the team takes, work process / profile, tests), the
      `.claude/settings.json` example (`env` `HO_HUB` / `HO_TEAM`), `openspec init --tools claude` for the
      `openspec` profile, the product team.
- [x] 2.3 First dry run: a short neutral example of a healthy output and the common errors with their real message
      start and fix (hub not found, team path wrong, `ho` incompatible, `owner_team` not in the hub, Claude Code not
      found / not logged in).
- [x] 2.4 Link instead of repeating (design D2); Windows vs POSIX differences only where they matter (design D8).
- [x] 2.5 `README.md`: a link at the top and in "Quick start"; optionally a one-line link from `radark/README.md`
      "Setup".

## 3. Verification

- [x] 3.1 Follow the guide literally in a scratch directory under the session's temporary directory (not in this
      repository; install nothing): local hub, two team repositories from the template, `radark.toml` from the
      example, `radark dry-run` until green. Fix the guide where a literal step fails. Record which steps were run.
- [x] 3.2 Run the sandbox section as written, up to a green `dry-run`.
- [x] 3.3 Check every command and flag in the guide against `--help` / the code (spec *The guide links instead of
      repeating*).
- [x] 3.4 Public-repository check: search the diff for owner paths, product / pipeline / company names and real hub
      or run excerpts; only neutral names, made-up IDs, `D:\work\my-factory` / `~/work/my-factory`.
- [x] 3.5 Full test suite: `radark-test-slot python -m pytest radark/tests`; failing / flaky tests per hub
      `AGENTS.md` §10 (report them, never hide them).
- [x] 3.6 If the radark-handover README lacks something the guide needs (e.g. a local hub without a remote), send a
      handover to `radark-handover` instead of a workaround (expected: not needed).

## 4. Report

- [x] 4.1 Commit locally (no push, tag, release or reinstall).
- [x] 4.2 `ho done HO-20261117-d7uw -m "<summary: guide location, steps run literally and their result, sandbox
      invocation, test result, any gap for product>"`; `ho sync`.

## Apply notes (2026-11-17)

- 1.2 / D4: `python -m radark.sandbox.make_sandbox <dir>` works from an installed release (the script is package
  data); the guide documents it, and the clone form `python radark/sandbox/make_sandbox.py <dir>`.
- 1.3 / D7: `dry-run` does not detect a missing Claude Code login (it only prints `claude --version`); the guide
  says so and points to `claude auth status` (exists in Claude Code 2.1.326, exit 0 when logged in) or an
  interactive `claude` login. A missing `claude` gives `Configuration error: '<cmd>' (claude) was not found on PATH`.
- D3: `radark` has no `--version`; the guide uses `pip show radark-factory` / `uv tool list`, `radark --help`,
  `ho --version [--json]`, `claude --version` and the dry-run summary. A `--version` flag is left to product.
- `radark.toml.example` is not package data: the guide says it is in the repository and also gives the minimal
  configuration in full.
- 3.1: followed literally in a scratch directory with the installed `radark` 0.5.0 / `ho` 0.2.0 (contract 1) and
  with `python -m radark` from the working tree (for the start banner): `ho init`, local git hub, `ho sync` without
  a remote ("No upstream to pull from", local commit), `ho teams`, two team repositories with the template
  `CLAUDE.md` and `.claude/settings.json`, `openspec init --tools claude`, the guide's `radark.toml`, `dry-run`
  green (exit 0, "Nothing to do"), then `ho new` as the owner and `dry-run` naming the act session. Error rows
  checked by breaking the configuration: wrong `repo`, wrong `hub`, unknown `owner_team`, `ho` and `claude` not on
  PATH, no `radark.toml` (exit 2 and the quoted message starts). The healthy-output example was neutralised by
  hand. The first scratch dry-run registered the scratch pipeline in the real machine registry; removed again with
  `radark cockpit --forget`.
- 3.2: the sandbox section run as written with the installed release: sandbox made, `machine-env.sh` loaded,
  `dry-run` green with the sandbox machine directory.
- 3.5: full suite via radark-test-slot: 1013 passed (8 min 08 s).
- 3.6: the radark-handover README covers the shared hub and says a plain folder works; a local git hub without a
  remote works with `ho sync` as is. No handover to `radark-handover` needed.

Notes: archiving the change and syncing its specs are not part of these tasks; they run in a separate phase after
`radark-product` closes the handover. Assumptions made unattended are listed in design.md "Open questions".
