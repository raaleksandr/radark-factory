# Design: workflow profiles

Handover HO-20261114-du6k (RB-012). The dispatcher was run unattended for the propose phase; every choice the handover
left open is decided here and marked **Assumption** where it is a judgement call.

## Context

OpenSpec is built into three places:

- `radark/prompts.py`: `phase_prompt` (propose/apply/returned apply/review/archive/act), `_change_ref`, `_closing`,
  `STANDING_RULE` ("record the assumption in the change (design or tasks notes)"), `APPLY_NO_ARCHIVE`,
  `wrap_up_message` (apply: "check off the finished tasks in the change's `tasks.md`"), `consult_prompt`,
  `escalation_body` ("OpenSpec change `x`"), `goal_check_prompt` ("archived OpenSpec changes").
- `radark/select.py`: `work_phase` (propose when no change is recorded), the archive candidates for technical teams.
- `radark/__main__.py`: `session_change` / `find_change` (propose artefact), `change_archived`, `phase_complete`,
  `after_session` ("propose created no OpenSpec change"), `made_progress` with `snapshot`, `checked_tasks` and
  `commits_outside(..., "openspec/changes/<change>/")`; `radark/forecast.py` predicts propose → apply → review →
  archive.

## Goals / Non-Goals

Goals: the setting; `openspec` as the default with byte-identical prompts and the same checks; `plain` end to end;
prompts from files with overrides; user-defined profiles with declarative checks; profile wording; docs.

Non-goals: renaming `harness.toml` / `.harness/` (RB-013); executable (Python) hooks in user profiles; changing the
product team's `act` / `review` flow; changing `[answers] default` (it is already configurable and pipeline-wide).

## Decisions

### D1. Configuration

```toml
[workflow]
profile = "openspec"   # default for every team; built-in: openspec, plain
dir = "workflows"      # profile directory, relative to harness.toml (default "workflows"; may be absent)

[[teams]]
id = "backend"
repo = "..."
kind = "technical"
profile = "plain"      # optional override
```

`Config.workflow_default`, `Config.workflow_dir`, `Team.profile` (resolved name). The default `dir` may be missing
(then only built-ins exist); a `dir` given explicitly that does not exist is a `ConfigError`. Profiles are loaded and
validated in `config.load` (all of them that any team uses), so every failure is exit 2 before anything starts, and
`dry-run` reports it the same way. **Assumption:** the key names `[workflow] profile`, `[workflow] dir` and
`[[teams]] profile`.

A profile applies to product teams too, but a product team only ever uses `act`, `review` and the standing rule
(its kind decides the phase, as today).

### D2. Profile model (`radark/workflow.py`)

```python
@dataclass(frozen=True)
class Profile:
    name: str
    phases: tuple[str, ...]        # subset of ("propose", "apply", "archive"); "apply" required
    noun: str                      # "change", "task", ...: wording
    artefact_label: str            # "OpenSpec change" / "" : how texts name a recorded artefact
    finished_words: str            # goal check: "archived OpenSpec changes"
    checks: Checks                 # D5
    templates: dict[str, Template] # D3
    sources: dict[str, Path|None]  # where each template came from (None = built-in), for dry-run
```

`load_profile(name, dir) -> Profile` and `resolve(cfg)` -> `dict[team_id, Profile]`. The dispatcher keeps
`self.profiles` and every place listed in Context asks the team's profile.

### D3. Templates

Files `radark/workflows/<profile>/<template>.md` shipped as package data (`pyproject.toml`
`radark = [..., "workflows/*/*"]`), read with `importlib.resources`. Template names: `propose`, `apply`,
`apply-returned`, `review`, `archive`, `act`, `wrap-up-apply`, `standing-rule`. Rendering: `string.Template`
`substitute` with the variables below; a file's single trailing newline is dropped (so files can end with a newline
and still render byte-identical prompts). Validation at load: every `$name` / `${name}` in a template must be a
documented variable (checked with `Template.get_identifiers`), `$$` is a literal `$`.

Variables (all strings; empty when not applicable):

| variable | value |
|---|---|
| `handover`, `title`, `phase`, `team`, `expects` | from the candidate (`expects` falls back to `see the handover`) |
| `change` | the recorded artefact name (empty if none) |
| `change_ref` | today's `_change_ref` text for `openspec`; for an `artifact_dir` profile: ``the <noun> `<name>` `` or ``the <noun> in `<dir pattern parent>` that cites <ID> (find it first)`` |
| `return_comment` | the return comment quoted with `> ` per line (`> (no comment)` when empty) |
| `hub_sync` | `Start and end with `ho sync`. ` |
| `closing` | the phase's closing sentence (today's `_closing`, per phase, owned by the profile: `closing-<phase>` keys in `profile.toml`, see D6) |
| `apply_no_archive`, `apply_local_todo`, `blocked_note`, `review_local_todo`, `team_decides` | today's constants |
| `noun` | the profile's noun |

The core keeps (and appends exactly as today) the denial and time-limit notes of the review, the goal/no-goal block,
`STANDING_RULE` position, long-wait and denial rules, parallel and test-slot notes. `phase_prompt` becomes:
render the profile's template for the phase (`apply-returned` when `return_comment is not None`) → `head` + body →
review extras → `_with_rule(..., standing_rule=profile)`.

Golden guard: before moving text, task 1.1 records today's rendered prompts for a fixed set of candidates (all
phases, returned apply, review with denials and time limits, wrap-up apply/other, timeout-resume, consult,
escalation, goal check) into `radark/tests/golden/openspec_prompts.json` from the *unchanged* code; the refactored code
must reproduce them exactly. Any difference is a bug, not a justified change. **Assumption:** zero differences is the
target; if one turns out unavoidable it is listed in `tasks.md` "Apply results" with the reason.

### D4. Overrides and user-defined profiles

Lookup for template `t` of profile `p`: `<dir>/<p>/<t>.md` if present, else (built-in `p`) the package file, else
(user profile with `based_on = "<built-in>"`) the base profile's package file, else a `ConfigError` naming the missing
file. A user profile's directory must contain `profile.toml`; a directory under `<dir>` named like a built-in profile
holds only overrides (a `profile.toml` there is refused, to keep one source of truth for built-ins). **Assumption.**

`profile.toml` of a user profile:

```toml
phases = ["propose", "apply", "archive"]   # apply required
noun = "spec"                               # default "task"
artefact_label = "spec"                     # default = noun; "" for none
finished_words = "archived specs"           # default "finished tasks"
based_on = "openspec"                       # optional: missing templates come from this built-in
artifact_dir = "specs/{name}"               # optional; required if propose or archive is declared

[closing]                                   # optional: closing sentences per phase, defaults = based_on's or plain's
propose = "End your final message with one line `CHANGE: <name>` naming the spec you created."
```

Unknown keys are refused (typos fail loudly).

### D5. Check hooks

```python
class Checks(Protocol):
    def artefact(self, repo, handover, result_text, assistant_text) -> str | None: ...   # propose produced
    def archived(self, repo, artefact) -> bool: ...
    def snapshot(self, repo, artefact) -> dict: ...                                     # base for progress
    def progress(self, repo, base, phase) -> tuple[list[str], list[str]]: ...           # (sources, ignored)
```

Hub progress (team's events on the handover, a new handover sent) stays in the core, because it does not depend on
the profile; the hook adds repository sources.

- `OpenSpecChecks`: today's `parse_change`/`find_change`, `changes/<c>` gone, `snapshot` with `tasks`,
  `commits` with the `commits_outside` filter and `change_notes` ignored, `tasks`. Code moves, behaviour does not.
- `DirChecks(pattern)`: the same with `openspec/changes/{name}` replaced by the pattern; `tasks` source only if the
  directory has a `tasks.md` (checked-box count works for any Markdown checklist). `OpenSpecChecks` is
  `DirChecks("openspec/changes/{name}")` plus the `archive` sub-folder exclusion, so there is one implementation.
  **Assumption:** pattern is a single `{name}` in the last path segment; `find` scans its parent directory.
- `PlainChecks`: `artefact` → None, `archived` → True, `snapshot` → heads only, `progress` → `commits` when
  `new_commits` (no folder filter).

### D6. Phase sequence

- `select.work_phase(kind, item, rec, profile)`: product → `act`; technical → `apply` if `"propose"` not in
  `profile.phases`, else today's rule.
- `select.candidates(...)` gets `archives: set[team]` (teams whose profile has `archive`); a closed `done` record of
  another team is not an archive candidate.
- Dispatcher: in the loop step that already fetches `shows` for `phase == "done"` records, a closed handover of a team
  without `archive` sets `rec["phase"] = "archived"`, logs `closed_without_archive` and prints
  `<team> <ID>: closed by the author; finished (profile <p> has no archive phase)`. **Assumption:** the record keeps
  phase name `archived` so every existing consumer (forecast, goal report, status) treats it as finished.
- `after_session` propose branch: `profile.checks.artefact(...)`; the problem line says
  `propose created no <noun>` — for `openspec` the noun label is `OpenSpec change`, so the text is unchanged.
- `phase_complete` archive: `checks.archived`.
- `forecast.apply_outcome`/candidate generation use the same `work_phase` and `archives` → no propose/archive for
  `plain`.

### D7. Built-in `plain` prompts

`apply.md` (new handover), roughly:

> `$hub_sync`Read the handover with `ho show $handover --json`, acknowledge it with `ho ack $handover`, then do the
> task it asks for: make the change, test it (run the tests that cover it), and commit locally. Do not push. If the
> task turns out too big or unclear for one session, do what is clear, commit it, and say what is left. `$closing`
> `$apply_local_todo` If you need another team, send your own handover with `ho new` and stop that part.
> `$blocked_note`

`apply-returned.md`: return comment + "Continue the task according to the return comment; commit locally." +
same tail. `standing-rule.md`: like `openspec`'s, but "record the assumption in your commit message and in the
`ho done` summary". `wrap-up-apply.md`: "commit, and report with `ho done` whose summary starts with `Wrapped up at
the time limit.` and has a line `Left: ...`" (no `tasks.md`). `act.md`: today's act text with "Routine work needs no
separate task record." `review.md`, `archive.md`: review same as `openspec`'s; `archive.md` absent (no phase).
`closing`: apply → today's `ho done` sentence. Wording: noun `task`, `artefact_label` empty, `finished_words`
`closed handovers`.

**Assumption:** `plain` keeps the phase name `apply` (console, log, state, wrap-up and blocked handling key on it);
no new phase name is introduced.

### D8. Wording in shared texts

`consult_prompt`, `escalation_body`: `f" ({label} `{change}`)"` only when the profile's `artefact_label` is non-empty
and a change is recorded — identical for `openspec`. `goal_check_prompt` gets the deduplicated `finished_words` of
the profiles in use in configuration order: `"closed handovers, archived OpenSpec changes"` with only `openspec`
(today's text); `"closed handovers"` with only `plain`; both joined with `, ` otherwise.
**Assumption:** whole-hub steps (idle ask, goal check, consult, limit check) keep the constant `STANDING_RULE`; only
item sessions (the phase prompts, wrap-up and resume texts) use the team profile's `standing-rule` template.

### D9. dry-run / start lines

`config.summary`: the team line gains the profile column: `  app                    technical openspec  <repo>`.
**Assumption:** this widening of the team line is the one intended difference in console output; tests that match
the team line are updated, and it is listed in "Apply results". With a profile directory in use a line
`Workflow profiles: <dir> (overrides: plain/apply.md; user-defined: spec-kit)`.

## Risks / Trade-offs

- Byte-identical prompts after moving text into files → golden test from unchanged code first (task 1.1).
- `string.Template` and `$` in prompt text (`$HO_HUB`, shell examples): templates write `$$`; the golden test catches
  misses; validation refuses unknown identifiers so a stray `$HOME` fails at start, not mid-run.
- Package data missing in an installed wheel → `pyproject.toml` package-data entry and a test that loads every
  built-in via `importlib.resources`.
- Size: if the apply session runs out of time, the split point is after group 5 (setting, `openspec` default, `plain`
  end to end, checks as hooks); user-defined profiles (group 6) then become the named remainder in the `ho done`
  summary.

## Migration Plan

None for users: no setting → `openspec`. State records need no migration (`change` field kept, phase names kept).
