# Proposal: the work process is a setting (workflow profiles)

Handover: **HO-20261114-du6k** (RB-012, "the work process is a setting (workflow profiles)"), from `radark-product`.
Builds on the archived change `machine-wide-instances` (HO-20261114-cda3); not in scope: renaming `harness.toml` /
`.harness/` (RB-013).

## Why

The engine hardcodes OpenSpec as the only way of working: the phases propose → apply → review → archive, their
prompts (`/opsx:propose`, `/opsx:apply`, `/opsx:archive`, the `CHANGE:` line, `tasks.md`) and the dispatcher's checks
(propose must create `openspec/changes/<name>/`, progress counts checked tasks and commits outside the change folder,
archive means the change folder is gone). A one-line fix or an archive-only task still costs a full propose session,
and a team that uses another spec tool, or none, cannot be run at all.

## What Changes

- **Workflow profile setting** in `harness.toml`: `[workflow] profile = "<name>"` is the pipeline-wide default, and
  `profile = "<name>"` in a `[[teams]]` entry overrides it for that team. An unknown profile, or a profile whose files
  are broken (missing prompt, unknown template variable, bad `profile.toml`), is refused at start with a clear message
  (exit 2). `dry-run` and the start lines show each team's profile.
- **Built-in `openspec` profile, the default.** With no new setting every pipeline behaves exactly as today: same
  phases, the same rendered prompts (the text moves into template files in the package and renders byte-for-byte the
  same), the same checks.
- **Built-in `plain` profile, without SDD**: a technical team gets one work session per handover: do the task, test it,
  commit locally, report with `ho done`. No propose and no archive session, no change folder. Progress = new commits in
  the team's repository or the team's hub activity on the handover (the no-progress limit and loop protection work as
  before); the work is done when the team's part reaches `done`; after the author closes the handover the record is
  finished without an archive session. A return (`ho return`) gives another work session in the same profile.
- **Phase prompts from files**: each built-in profile ships its prompt templates (`propose.md`, `apply.md`,
  `apply-returned.md`, `review.md`, `archive.md`, `act.md`, `wrap-up-apply.md`, `standing-rule.md`) and its
  `profile.toml` in `radark/workflows/<profile>/`. A user can override single prompt files of a built-in profile, or
  define a new profile (phases, wording, checks, prompt files), in a directory next to the configuration
  (`[workflow] dir`, default `workflows/`). Templates use `$name` variables (Python `string.Template`); the README
  documents every variable.
- **Checks belong to the profile**: "the propose phase produced its artefact", "progress" and "archived" are hooks of a
  profile (`radark/workflow.py`): built-in implementations for `openspec` (today's checks, moved) and `plain`, and a
  small declarative set for a user-defined profile (`artifact_dir = "<pattern with {name}>"`: created by propose,
  removed by archive; without it the plain checks). The core loop (selection, sessions, limits, wrap-up, escalation,
  parallel sessions, machine layer) no longer names OpenSpec or `openspec/changes/`.
- **Wording**: consult, escalation and goal-check texts take the profile's wording (`OpenSpec change` for `openspec`,
  nothing extra for `plain`); with only `openspec` teams they render as today.
- **Docs**: the README's configuration reference and the team `CLAUDE.md` template describe the setting, both built-in
  profiles, overriding prompts, user-defined profiles and when to choose `plain` (small or routine tasks, a team
  without SDD). `harness.toml.example` gets a commented `[workflow]` section.

Nothing changes for a running pipeline that does not opt in. Not a breaking change.

## Capabilities

### New Capabilities

None. Workflow profiles are dispatcher behaviour, like the requirements of `parallel-sessions` and
`machine-wide-instances`.

### Modified Capabilities

- `harness-dispatcher`: new requirements for the workflow profile setting, the built-in `openspec` and `plain`
  profiles, prompt templates from files and their override, user-defined profiles, profile checks, profile wording and
  the profile shown by `dry-run`; the existing OpenSpec-specific requirements (Phase prompts, Archive only after the
  author closes, Archive gate, Session outcome) are stated to describe the `openspec` profile.

## Impact

- Code: new `radark/workflow.py` (profile loading, validation, template rendering, check hooks); new package data
  `radark/workflows/openspec/*` and `radark/workflows/plain/*`; `radark/prompts.py` (phase, wrap-up, standing-rule,
  consult, escalation and goal-check texts render through the team's profile); `radark/config.py` (`[workflow]`,
  per-team `profile`, validation, summary line); `radark/select.py` (first phase and archive per team from its
  profile); `radark/__main__.py` (propose/progress/archive checks through profile hooks, closing a record without an
  archive phase, `dry-run`); `radark/forecast.py` (predicted phases follow the profile); `pyproject.toml`
  (package data `workflows/*/*`).
- Files: README (root and `radark/README.md`), `harness.toml.example`, team `CLAUDE.md` template in the README,
  sandbox (`radark/sandbox/make_sandbox.py`: one team on `openspec`, one on `plain`).
- Tests: golden test that every `openspec` prompt renders as before; new `radark/tests/test_workflow.py` (profile
  selection, unknown profile → exit 2, prompt override, user-defined profile) and dispatcher tests of the `plain`
  sequence with fake `ho` / `claude`.
- No change to `ho`.
