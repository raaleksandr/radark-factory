# CLAUDE.md

radark-factory is a deterministic Python dispatcher that runs Claude Code team agents through OpenSpec phases,
driven by a handover hub (the `ho` CLI from radark-handover). Start with [README.md](README.md), then
[harness/README.md](harness/README.md) and the specs in [openspec/specs](openspec/specs).

## Commands

- Tests: `python -m pytest harness/tests` (about 5 minutes; all must pass). They use fake `ho` and `claude`
  (`harness/tests/fakes/`), never a real hub or a real Claude Code session.
- Sandbox for a manual end-to-end check: `python harness/sandbox/make_sandbox.py <dir>` (a real hub and two
  tiny team repositories), then `python -m harness --config <dir>/harness.toml dry-run`.

## Rules

- Python 3.11+, **standard library only**; the only runtime dependency is radark-handover (`ho`), used as a CLI
  through `ho ... --json` and exit codes, never imported.
- Every change is an OpenSpec change (`openspec/changes/<name>/`): proposal, design, specs, tasks; specs in
  `openspec/specs/` are the source of truth and are synced on archive.
- **This repository is public.** Never commit a user's paths, product or company names, hub or run excerpts, or
  personal data. Examples use neutral team names: `product`, `app`, `backend`, `strategy`.
- The dispatcher has no model and no credential of its own; it never passes `ANTHROPIC_API_KEY`, never uses
  `--bare` or `bypassPermissions`.
- **Dogfooding:** this engine may itself be developed by a radark pipeline. A pipeline always runs an *installed*
  release, never this working tree. Do not install, reinstall, tag, push or release from a session — those are
  the owner's steps.
- Docs and code comments in English.

## Working through a handover hub

When a radark pipeline runs you, `HO_HUB` and `HO_TEAM` are set.

- Before the first handover in a session, read `$HO_HUB/AGENTS.md`; run `ho sync` first and last.
- Work a handover asks for becomes an OpenSpec change that cites the handover ID; report it with
  `ho done <ID> -m "<summary>"`, archive the change only after the author closes the handover.
- If the change needs something from the `ho` CLI (a new command, flag or JSON field), send a handover to the `ho`
  team named in `$HO_HUB/AGENTS.md` instead of working around it here.
- Failing and flaky tests: follow `$HO_HUB/AGENTS.md` (if it has a rule for them); never hide a flake with
  retries or skips.
- Unclear question: `ho comment <ID> -m "..."` instead of guessing.
