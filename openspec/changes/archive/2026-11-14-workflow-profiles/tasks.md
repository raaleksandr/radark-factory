# Tasks

Change for HO-20261114-du6k (RB-012). Tests use fake `ho` / `claude` only. Groups 1–5 are the handover's minimum
(setting, `openspec` default unchanged, `plain` end to end, checks as hooks); group 6 adds user-defined profiles. If
the apply phase runs out of time after group 5, group 6 is the named remainder in the `ho done` summary (design,
Risks). Assumptions are marked in `design.md`.

## 1. Golden prompts and the profile skeleton

- [x] 1.1 Before changing any prompt code, add `radark/tests/test_workflow_golden.py` with a generator that renders,
  with the current code, a fixed set of inputs: propose, apply (new; returned with a multi-line and an empty comment;
  with and without a recorded change), review (plain; with denials; with time limits), archive, act, `wrap_up_message`
  (apply and review), `timeout_resume_message` (same phase and next phase), `consult_prompt`, `escalation_body`,
  `goal_check_prompt`, each with and without a goal / no-goal block. Store the output in
  `radark/tests/golden/openspec_prompts.json` and commit it. Verify: the test passes on the unchanged code.
- [x] 1.2 New `radark/workflow.py` (design D2–D4): `Profile`, template lookup (override dir → package → `based_on`),
  `string.Template` rendering with the documented variables (D3 table), trailing-newline rule, validation of unknown
  identifiers; `pyproject.toml` package data `workflows/*/*`. Verify: unit tests in `radark/tests/test_workflow.py`
  — every built-in profile loads through `importlib.resources`; a template with `$unknown` is refused naming file and
  variable; `$$` renders `$`.

## 2. Built-in openspec profile (no behaviour change)

- [x] 2.1 Move the phase texts of `radark/prompts.py` into `radark/workflows/openspec/` (`propose.md`, `apply.md`,
  `apply-returned.md`, `review.md`, `archive.md`, `act.md`, `wrap-up-apply.md`, `standing-rule.md`, `profile.toml`
  with `[closing]`, noun, label `OpenSpec change`, finished words `archived OpenSpec changes`); `phase_prompt`,
  `wrap_up_message`, `timeout_resume_message`, `_closing`, `_change_ref` render through the candidate team's profile
  (D3); core-owned parts appended as today. Verify: the golden test of 1.1 passes unchanged and the existing
  `test_prompts.py` passes.
- [x] 2.2 Profile wording in `consult_prompt`, `escalation_body`, `goal_check_prompt` (D8). Verify: golden test
  unchanged; new tests that a `plain` team's escalation and consult texts name no OpenSpec change and that the goal
  check with only `plain` says `closed handovers`, with both profiles both phrases.

## 3. Configuration and dry-run

- [x] 3.1 `radark/config.py`: `[workflow] profile` / `dir`, `[[teams]] profile`, loading and validating every used
  profile at load (D1); `ConfigError` (exit 2) for an unknown profile (message lists built-in and found names), an
  explicit missing `dir`, a broken template. Verify: tests in `test_workflow.py` for default (no section →
  `openspec`), pipeline default, per-team override, unknown profile → `dry-run` and `run` exit 2 naming team and
  profile, explicit missing dir → exit 2.
- [x] 3.2 `config.summary` team line with the profile column and the `Workflow profiles:` line (D9). Verify: dry-run
  test shows `openspec` and `plain` for two teams; existing tests that match the team line updated; the line change
  recorded under "Apply results".
- [x] 3.3 Docs for groups 1–3: README configuration reference (`[workflow]`, `profile`), `harness.toml.example`
  commented `[workflow]` section. Verify: the example still loads in `test_config.py` (or the existing example test).

## 4. Checks as profile hooks

- [x] 4.1 `Checks` protocol with `DirChecks` / `OpenSpecChecks` and `PlainChecks` in `radark/workflow.py` (D5); move
  `find_change`, `checked_tasks`, `snapshot`, `commits_outside` use and `change_archived` behind the hooks;
  `made_progress` keeps hub progress in the core and asks the hook for repository sources; `after_session`,
  `phase_complete`, `session_change` use the hooks; the problem line uses the profile label. Verify: the existing
  `test_progress.py`, `test_dispatcher.py`, `test_wrap_up.py` pass unchanged; `grep -n "openspec" radark/__main__.py
  radark/select.py radark/forecast.py` finds no OpenSpec path or wording left in the core (comments citing older
  design IDs excepted).

## 5. Built-in plain profile end to end

- [x] 5.1 `radark/workflows/plain/` templates and `profile.toml` (D7). Verify: rendered apply, returned apply,
  wrap-up and act prompts for a `plain` team contain `ho ack`, "commit locally", `ho done` and no `opsx`, `OpenSpec`,
  `tasks.md` or `CHANGE:`; snapshot strings asserted in `test_workflow.py`.
- [x] 5.2 Phase sequence (D6): `select.work_phase` / `candidates` with the profile's phases and the `archives` set;
  the dispatcher finishes a closed `done` record of a team without archive (`closed_without_archive` log event and
  console line); `forecast` follows the profile. Verify: select tests (new `plain` handover → apply; closed done
  `plain` record → no archive candidate); dispatcher test with fake `ho`/`claude`: new handover → one apply session
  → `ho done` → author review closes → record `archived` without a session; prediction test shows apply then review
  and no propose/archive.
- [x] 5.3 `plain` progress and loops: dispatcher tests — an apply session with a commit and no `ho done` is progress;
  two sessions with neither stall and escalate; a return gives one apply session quoting the comment (one session per
  return, no-loop N1 still holds); a time-limit wrap-up in `plain` asks for `ho done` with `Left:` and no `tasks.md`.
- [x] 5.4 Docs for `plain`: README section "Workflow profiles" (both built-ins, when to choose `plain`), team
  `CLAUDE.md` template note on the profile; `radark/README.md` progress paragraph says the folder filter belongs to
  the `openspec` profile. Verify: README examples use only neutral names; read through once.

## 6. Prompt overrides and user-defined profiles

- [x] 6.1 Override of a built-in profile's single template from `<dir>/<profile>/<template>.md` (D4); a
  `profile.toml` in a built-in's override directory refused. Verify: test with `workflows/plain/apply.md` in a temp
  config dir — the apply prompt is the override, the other prompts are built-in; dry-run lists the override.
- [x] 6.2 User-defined profile: `profile.toml` keys (D4) with unknown-key refusal, `based_on`, `artifact_dir` with
  `DirChecks`, propose/archive without `artifact_dir` refused. Verify: tests — a `spec-kit`-style profile with
  `artifact_dir = "specs/{name}"` runs propose (artefact found by citation), apply (commits only inside the
  directory are `change_notes`), closed → archive, done when the directory is gone; a profile without
  `artifact_dir` behaves like `plain`; invalid `profile.toml` → exit 2 naming the file.
- [x] 6.3 Docs: README "Defining a profile" and the full template-variable table (D3). Verify: a test renders a
  template that uses every documented variable without error, and the README table lists exactly the variables the
  code accepts (test reads the README table).

## 7. Finish

- [x] 7.1 Sandbox (`radark/sandbox/make_sandbox.py`): one team on `openspec`, one on `plain`; run `dry-run` and a short
  run with fake `ho` / `claude` and record the console lines under "Apply results". Verify: both teams' profiles
  shown; the `plain` team gets no propose session.
- [x] 7.2 Full suite `python -m pytest radark/tests` green (failing and flaky tests per hub `AGENTS.md` §10: report,
  never hide with retries or skips). Record the test count and every console or prompt difference for `openspec`
  (expected: only the team-line profile column, D9) under "Apply results". Check that nothing private is committed
  (no owner paths, product names, hub or run excerpts). Commit locally; no push, tag, release or reinstall.
- [x] 7.3 `ho done HO-20261114-du6k -m "..."` listing: change name `workflow-profiles`, commits, the new settings with
  defaults (`[workflow] profile = "openspec"`, `[workflow] dir = "workflows"`, `[[teams]] profile`), what changes for
  running pipelines (nothing unless they opt in; the profile column in the team line), any split remainder, test
  counts. This is the last step of apply; archiving and spec sync are a separate phase after the author closes the
  handover.

## Apply results

Apply phase, 2026-11-14. All groups 1–6 done; no split remainder.

- **Golden prompts (1.1, 2.1):** `radark/tests/golden/openspec_prompts.json` holds 77 prompts rendered by the code
  before any prompt change (committed first, separately). The refactored code reproduces all of them byte for byte:
  **zero differences** for `openspec`.
- **Intended console difference (D9):** the team line of the start lines and `dry-run` has the profile column, e.g.
  `  app                    technical openspec  <repo>`. No existing test matched the old team line, so none needed
  updating. With a profile directory in use (an override or a user-defined profile) an extra line
  `Workflow profiles: <dir> (overrides: plain/apply.md; user-defined: spec-kit)`. No other console or prompt change for
  `openspec`.
- **Core without OpenSpec (4.1):** `grep -n "openspec" radark/__main__.py radark/select.py radark/forecast.py` finds
  only a docstring and a comment naming the `openspec` profile; no OpenSpec path or wording. `snapshot()` stays in
  `__main__` as a wrapper of the default profile's check (tests import it). `find_change`, `checked_tasks`, `commits_outside`, `branch_heads`,
  `new_commits`, `git_out` moved to `radark/workflow.py` (`DirChecks` / `PlainChecks`); the git helpers are
  re-imported into `__main__` under their old names.
- **Assumptions taken in apply (beyond design.md):**
  - Template files are read with CRLF normalised to LF, so a Windows checkout with `core.autocrlf` renders the same
    prompts.
  - A `.md` file in a profile directory whose name is not a template name is refused (typo guard, like unknown keys
    in `profile.toml`); unknown keys in `[workflow]` are refused too.
  - `change_ref` of a user profile without `artifact_dir` is ``the <noun> of <ID>``.
  - `dry-run` prints `Would finish: <team> <ID> (closed by the author; profile <p> has no archive phase)` for a
    `plain` record it would finish, and changes nothing; `run`/`once` finish it at selection time (`plan()`), with
    the `closed_without_archive` log event and console line of D6.
  - Not changed (outside the listed texts): the owner-answer resume texts (`Record it in the change ...`) and
    `[answers] default`, which still say "change"; they carry no OpenSpec name and stay pipeline-wide (design
    non-goal for `[answers] default`).
- **Sandbox (7.1):** `make_sandbox.py` now makes `backend` on `plain` (no `openspec init`) next to `app` on
  `openspec`. Run in a temp directory with the `ho` of the radark-handover working tree (the installed `ho` had no
  `--version`) and two handovers, one per technical team:
  - `dry-run` team list: `product  product openspec`, `app  technical openspec`, `backend  technical plain`;
    candidates `app work propose HO-...` and `backend work apply HO-...`.
  - `plan`: `app propose`, `app apply`, `product review`, `app archive`, `backend apply` — no propose/archive for
    `backend`.
  - `once` with the fake `claude`: `backend · apply · HO-...` started directly with the `plain` apply prompt
    (`ho ack`, "commit locally", `ho done`; no `opsx`, `OpenSpec`, `tasks.md`, `CHANGE:`); the empty fake session
    counted `no progress (1 of 2)` as expected.
- **Package data:** `pyproject.toml` adds `workflows/*/*`; the built-ins load through `importlib.resources` in the
  tests. A wheel build could not be checked here (no `setuptools` in this environment).
- **Tests (7.2):** `python -m pytest radark/tests`: **834 passed** in 409 s (801 before this change's new tests plus
  33 in `test_workflow.py`; the golden test counts among the 801). No failing or flaky test seen.
