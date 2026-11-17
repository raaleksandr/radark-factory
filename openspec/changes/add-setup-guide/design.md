# Design: "Setup from zero" guide

Handover HO-20261117-d7uw (RB-009).

## Context

The facts a new user needs already exist but are scattered: the install line and Quick start in `README.md`; setup,
configuration keys, `ho` compatibility, commands, console, owner workflow and run-time files in `radark/README.md`;
keys in `radark.toml.example` and `machine.toml.example`; a ready-made scratch setup in
`radark/sandbox/make_sandbox.py` (shipped as package data); hub setup in the radark-handover README. The engine has
no `--version` flag; `dry-run` prints the Claude Code and `ho` versions in its start summary, and
`ho --version --json` reports the JSON contract.

## Decisions

### D1. A separate file `docs/setup.md`, linked from the top of the README and from "Quick start"
Product prefers a separate file. `docs/` already holds `decisions/` and `research/`; `docs/setup.md` sits next to
them. The README gets one line under the title (e.g. "New here? Start with [Setup from zero](docs/setup.md).") and
the Quick start says that its lines assume an existing setup and points to the guide. The Quick start stays short.

### D2. Link, do not repeat
The guide gives the minimal steps and the "why", and links to the reference for details: `radark/README.md`
"Configuration (`radark.toml`)", "Compatibility of `ho`", "Workflow profiles", "Several pipelines on one computer",
"Commands", "Console", "Owner workflow (escalations)", "Run-time files (`run_dir`)", "Tests and sandbox"; the
`README.md` sections "Owner-only actions / decisions the team takes", "Workflow profile", "Cockpit"; the
radark-handover README "Set up a hub shared through git". Tables of keys and error messages are not copied; the
guide quotes only the few lines a user must recognise (the start line `ho: <version> (contract 1)`, the starts of
the error messages).

### D3. Versions without a new command
There is no `radark --version`, and this task adds no command. The guide checks the install with
`pip show radark-factory` (or `uv tool list`), `radark --help`, `ho --version` / `ho --version --json` (contract
number) and `claude --version`, and points out that `radark dry-run` prints the Claude Code and `ho` versions in its
start summary. Assumption (unattended session): this is the "or equivalent" the handover allows; a `--version` flag
would be a separate backlog item for product, mentioned in the `ho done` summary.

### D4. The sandbox section uses the shipped script
The engine has a sandbox: `radark/sandbox/make_sandbox.py` creates a scratch hub, an `app` (openspec), a `backend`
(plain) and a `product` repository and a `radark.toml`. The guide shows how to run it from a clone
(`python radark/sandbox/make_sandbox.py <dir>`) and from an installed package (the script is package data; the apply
phase checks the exact invocation that works from an installed release, e.g. `python -m radark.sandbox.make_sandbox
<dir>` or the path under `site-packages`, and documents only what works). If neither works from an installed
package, the guide describes the manual way (a copy of the configuration, `ho init` of a scratch hub, scratch
repositories) and the gap is reported in the `ho done` summary for product; no new command is added.

### D5. Local hub without a remote
Minimal commands: `ho init <hub-dir> --teams product=...,app=...,owner=...` (exact syntax checked against
`ho init --help`), as a plain folder or a local git repository without a remote; `ho sync` then says there is no
upstream and commits locally, which is fine. `HO_HUB` / `HO_TEAM` are set per team repository in
`.claude/settings.json` (`env`) and, for manual use, in the shell (POSIX and PowerShell forms). Product's decision:
the ho README covers the shared-through-git case; if the apply phase finds the local-only case missing there, it
sends a handover to `radark-handover` instead of documenting a workaround.

### D6. Team repository template
A copy-paste `CLAUDE.md` block with placeholders: role (team id, technical or product), hub and team (`HO_HUB`,
`HO_TEAM`), `ho sync` first and last, read `$HO_HUB/AGENTS.md`, owner-only actions / decisions the team takes (as in
the README example), work process (`openspec` or `plain` profile), tests. A `.claude/settings.json` example with
`env` `HO_HUB` / `HO_TEAM` and a small `permissions.allow` list (mirroring what the sandbox writes).
`openspec init --tools claude` only for the `openspec` profile. The product team: `kind = "product"`; its
`CLAUDE.md` says it sends tasks to the technical teams with `ho new` and reviews their results (`close` / `return`);
`[triage] team`.

### D7. Healthy dry-run output and common errors
A short invented example of a healthy `dry-run` start (banner abbreviated, summary lines, `ho: 0.2.0 (contract 1)`,
"no work" or one candidate), produced by running the guide's own steps and then neutralised by hand. Common errors,
each with the real message start (taken from the code, not invented) and the fix: hub not found / no `hub.json`;
team `repo` path wrong; `ho` not found or incompatible; `owner_team` not in the hub; Claude Code not found or not
logged in. What the user actually sees for a missing login is checked during apply; if `dry-run` does not detect it,
the guide says so and tells the user to run `claude` once interactively and log in before the first real run.

### D8. Windows vs POSIX
Only the differences that matter: path quoting in TOML (single-quoted literal strings for `D:\...`), `copy` vs `cp`,
environment variables in PowerShell vs POSIX shells, `.radark\` vs `.radark/`. Commands are otherwise shown once.

### D9. Verification
The apply phase follows the guide literally in a scratch directory under the session's temporary directory (not in
this repository): install check, local hub, two team repositories made from the template, `radark.toml` from the
example, `radark dry-run` until green; also the sandbox section. It uses the installed `radark` / `ho` found on
`PATH` (it does not install or reinstall anything; CLAUDE.md reserves that for the owner) and, where the working
tree's behaviour is what the guide documents, `python -m radark` from the working tree. The `ho done` summary says
which steps were run and with which result.

## Risks / Trade-offs

- Docs drift from the code: mitigated by linking the reference instead of copying, and by quoting only stable
  message starts.
- No automated test for the guide: accepted; the handover asks for a manual literal run, and the full suite is run
  to confirm nothing else changed.
- Public repository: the guide must contain no owner paths, product, pipeline or company names and no hub or run
  excerpts; the healthy-output example is invented / neutralised.

## Open questions

None blocking. Assumptions made unattended: D3 (no `--version` flag; equivalent checks), D4 (sandbox invocation
decided by what works from an installed release), D7 (login detection checked during apply).
