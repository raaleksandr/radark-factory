## ADDED Requirements

### Requirement: Workflow profile setting
The dispatcher SHALL run every team through a workflow profile. `[workflow] profile` in the configuration SHALL name the pipeline-wide default profile (default `openspec`), and `profile` in a `[[teams]]` entry SHALL override it for that team. A profile name SHALL be a built-in profile (`openspec`, `plain`) or a user-defined profile found in the profile directory (`[workflow] dir`, relative to the configuration file, default `workflows`). An unknown profile name, a profile directory named in the configuration that does not exist, or a profile whose files are invalid (a missing prompt template, a template variable that is not documented, an invalid `profile.toml`) MUST be refused by `run`, `once` and `dry-run` with exit code 2 and a message naming the team, the profile and the problem, before any session starts.

#### Scenario: No workflow setting
- **WHEN** the configuration has no `[workflow]` section and no team sets `profile`
- **THEN** every team runs on the `openspec` profile

#### Scenario: Per-team override
- **WHEN** `[workflow] profile = "openspec"` and the `[[teams]]` entry of `backend` sets `profile = "plain"`
- **THEN** `backend` runs on `plain` and every other team on `openspec`

#### Scenario: Unknown profile
- **WHEN** the `[[teams]]` entry of `app` sets `profile = "kanban"` and no profile `kanban` exists in the profile directory
- **THEN** `run` and `dry-run` exit with code 2 with a message naming `app`, `kanban` and the built-in and found profile names, and no session starts

### Requirement: Profile shown at start
`dry-run` and the start lines of `run` and `once` SHALL show each team's workflow profile next to the team, and, when a user-defined profile or a prompt override is in use, the profile directory and the overridden prompt files.

#### Scenario: Dry run with two profiles
- **WHEN** `dry-run` runs with `app` on `openspec` and `backend` on `plain`
- **THEN** the team list shows `openspec` for `app` and `plain` for `backend`

### Requirement: Built-in openspec profile
The built-in `openspec` profile SHALL be the behaviour that the other requirements of this specification describe in terms of OpenSpec (phases propose → apply → review → archive, the propose, apply, archive and act prompts, the `CHANGE:` line, the change recorded for a handover, progress by checked tasks and by commits outside the change's directory, archive done when the change's directory is gone). For a team on `openspec` every prompt the dispatcher sends SHALL be identical to the prompt sent before workflow profiles existed, and every check SHALL give the same result.

#### Scenario: Existing pipeline unchanged
- **WHEN** a configuration without any workflow setting runs a new handover of `app` through propose, apply, review and archive
- **THEN** the sessions, their prompts, the recorded change, the progress decisions and the console lines are the same as before this change

### Requirement: Built-in plain profile
The built-in `plain` profile SHALL run a technical team's handover without a spec-driven process: its only work phase is apply (shown as `apply`), started directly for a new handover; the prompt asks the team to read and acknowledge the handover, do the task, test it, commit locally and report with `ho done`; it names no change, no `tasks.md` and no OpenSpec workflow. There is no propose and no archive session. A session SHALL count as progress when the team's repository has new commits since the item's work began or the team acted on the handover in the hub (or sent a new handover); commits are not filtered by any folder. The team's part SHALL be done when it reaches `done` in the hub; after the author closes the handover the dispatcher SHALL finish the item without a session and log it. A handover returned to the team SHALL get an apply session in the same profile with the return comment. The no-progress limit, the stall escalation, the one-session-per-return rule, time limits, wrap-up, owner answers and parallel sessions SHALL work as for `openspec`.

#### Scenario: New handover on plain
- **WHEN** `backend` runs on `plain` and has a new `action_required` handover `HO-20261114-ab12`
- **THEN** the dispatcher starts an apply session whose prompt asks to read and acknowledge `HO-20261114-ab12`, do and test the task, commit locally and report with `ho done`, and no propose session runs

#### Scenario: Progress by commits
- **WHEN** a `plain` apply session ends without `ho done` but with a new commit in the `backend` repository
- **THEN** the session counts as progress and the no-progress counter is reset

#### Scenario: No progress on plain
- **WHEN** two consecutive `plain` apply sessions for the same handover end with no commit and no hub activity of the team
- **THEN** the item is marked stalled and escalated to the owner

#### Scenario: Closed without archive
- **WHEN** `backend` on `plain` reported `done` and the author closed the handover
- **THEN** no archive session starts; the item is finished and the console and the run log say it was closed without an archive phase

#### Scenario: Return on plain
- **WHEN** the author returns a `plain` handover to `backend` with a comment
- **THEN** the next session of `backend` for it is an apply session in the `plain` profile whose prompt quotes the return comment

### Requirement: Phase prompts from template files
Every profile SHALL take its phase prompts from template files: `propose`, `apply`, `apply-returned`, `review`, `archive`, `act`, the apply wrap-up text and the standing rule. The built-in profiles SHALL ship their templates in the installed package. Templates SHALL use `$name` variables; the dispatcher SHALL substitute the documented variables (at least the handover ID, its title, the phase, the team, the expected action, the item's artefact name and reference, the quoted return comment and the shared rule texts used today by the prompts) and SHALL refuse at start a template that uses an undocumented variable. Parts of a prompt that do not depend on the profile (the review's denial and time-limit notes, the goal or no-goal block, the long-wait and denial rules, the parallel and test-slot notes) SHALL be added by the dispatcher as today.

#### Scenario: Built-in templates render today's prompts
- **WHEN** the propose, apply (new and returned), review, archive, act and wrap-up prompts are rendered for a team on `openspec`
- **THEN** each is identical, character for character, to the prompt the dispatcher produced before this change for the same input

### Requirement: Overriding a profile's prompts
A file `<profile directory>/<profile>/<template>.md` SHALL replace that template of the built-in profile `<profile>` for every team on it; templates not present in the directory SHALL stay the built-in ones.

#### Scenario: Override the apply prompt of plain
- **WHEN** `workflows/plain/apply.md` exists next to the configuration and `backend` runs on `plain`
- **THEN** the apply prompt of `backend` is rendered from that file, and its other prompts are the built-in `plain` ones

### Requirement: User-defined profile
A directory `<profile directory>/<name>/` with a `profile.toml` SHALL define a profile `<name>` that is not a built-in name. `profile.toml` SHALL declare the profile's phases (apply is required; propose and archive are optional), its wording (the noun for its artefact, e.g. `change` or `task`) and optionally `artifact_dir`, a repository-relative path pattern containing `{name}`. The profile SHALL provide a template file for every phase it declares plus `review`, `act` and the standing rule; a missing template MAY be taken from the profile named in `based_on` (a built-in profile). Its checks SHALL be:
- with `artifact_dir`: the propose phase produced its artefact when the session named it with a `CHANGE:` line or a directory matching the pattern cites the handover ID; archive is done when that directory is gone; commits in apply count as progress only when they change a file outside that directory;
- without `artifact_dir`: the `plain` checks (progress by commits or hub activity, done by `ho done`), and a profile without `artifact_dir` MUST NOT declare propose or archive.

#### Scenario: Another spec tool
- **WHEN** `workflows/spec-kit/profile.toml` declares phases propose, apply and archive with `artifact_dir = "specs/{name}"` and `app` runs on `spec-kit`
- **THEN** a new handover of `app` goes to propose with the profile's propose prompt, the recorded artefact is the `specs/<name>` directory that cites the handover, and the archive phase is done when that directory is gone

#### Scenario: Propose without artefact_dir
- **WHEN** a user-defined `profile.toml` declares a propose phase and no `artifact_dir`
- **THEN** `run` exits with code 2 naming the profile and the missing `artifact_dir`

### Requirement: Core loop independent of OpenSpec
Selection, sessions, time limits, wrap-up, escalation, product triage, parallel sessions, predictions and the machine layer SHALL take every phase sequence, artefact check, progress check and archive check from the team's profile. A prediction (`dry-run`) SHALL predict the phases of each team's profile: no propose and no archive step for a team on `plain`.

#### Scenario: Prediction for plain
- **WHEN** `dry-run` predicts a new handover for `backend` on `plain`
- **THEN** the predicted steps are apply, then the author's review, and no propose or archive step

### Requirement: Profile wording in shared texts
The consult prompt, the escalation handover, the wrap-up text and the goal-check prompt SHALL name the item's artefact with the profile's wording (`OpenSpec change` for `openspec`; nothing for `plain`, which has no artefact). The goal-check prompt SHALL name the finished work of the profiles in use; with only `openspec` teams it SHALL be identical to the text before this change.

#### Scenario: Escalation from a plain team
- **WHEN** a session of `backend` on `plain` stops for the owner
- **THEN** the escalation handover names the team, the handover and the phase, and does not mention an OpenSpec change

### Requirement: Documentation of workflow profiles
The README's configuration reference and the team `CLAUDE.md` template SHALL describe the `[workflow]` setting and the per-team `profile`, both built-in profiles, when to choose `plain` (small or routine tasks; a team without a spec-driven process), how to override prompt templates, how to define a profile, and every template variable.

#### Scenario: Template variables documented
- **WHEN** a user writes a prompt override using a variable listed in the README
- **THEN** the dispatcher accepts it at start and substitutes it in the prompt
