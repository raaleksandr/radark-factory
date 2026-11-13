# Design: rename the Python package `harness` to `radark`

Handover: HO-20261113-6cg3 (RB-002).

## Context

- All code lives in the package `harness/` (`__main__.py` with the CLI and the loop, `config`, `hub`, `runner`,
  `prompts`, `select`, `state`, `clock`, `awake`, `forecast`), plus `hooks/` (scripts run by Claude Code, loaded
  from their own directory, not through the package), `sandbox/make_sandbox.py`, `README.md` and `tests/` (with
  `fakes/`). Modules import each other relatively (`from . import ...`); tests import `harness.<module>` and patch
  `harness.__main__.<name>` by string.
- Hook commands are built per session in `runner.write_session_settings` from `HOOKS_DIR = Path(__file__).parent /
  "hooks"` and passed with `--settings`; team repositories hold no hook path. The move therefore changes hook paths
  automatically and the owner has nothing to update in team settings.
- `pyproject.toml` already declares the console script `radark`, but points it at `harness.__main__:main`.
- Texts that name the command: argparse `prog="python -m harness"`, the module docstring, the `clear` hint in
  `prompts.py` (two places), the hooks-not-loaded hint (`harness/README.md`), the `--goal`/`--once` error
  (`harness/README.md`), the usage line of `sandbox/make_sandbox.py`, the sandbox's printed hints; docs: `README.md`,
  `harness/README.md`, `CLAUDE.md`, `docs/`.
- Constraints: standard library only; Python 3.11+; public repository; no install, tag, push or release from a
  session.

## Goals / Non-Goals

**Goals:**
- `radark` is the real package; `python -m radark` and the `radark` script run it.
- `python -m harness` gives the same stdout and exit code for at least one release; old `import harness...` works.
- Every engine text and doc names `python -m radark`, with one sentence about the deprecated alias.

**Non-Goals:**
- Renaming `harness.toml`, `harness.toml.example`, `.harness/`, configuration keys, or the spec capability names
  `harness-dispatcher` / `orchestration-harness` (spec IDs, not commands). A rename of the config and run-directory
  names may be proposed as a separate idea in the `ho done` result.
- Removing the alias (a later release).
- Rewriting history: archived changes and research/decision records under `openspec/changes/archive/` and
  `docs/research/`, `docs/decisions/` that describe the past keep their wording, unless they give a command the
  reader is meant to run today.

## Decisions

### D1. Move with `git mv`, keep relative imports

`git mv harness radark`, so history follows the files. Intra-package imports are already relative and need no change.
Absolute `harness.` references (tests, string patch targets, `-c` snippets in `test_goal.py`, `pyproject.toml`) are
replaced by `radark.`. Paths built from `__file__` (`HOOKS_DIR`, `make_sandbox.py`'s `parents[1]`, `ROOT` in tests)
keep working; any path text that spells `harness/` is updated.

### D2. Alias package `harness`: `-m` and imports

Chosen: cover both `python -m harness` and imports, because it is cheap (two small files, standard library):

- `harness/__main__.py`: print one line to stderr — ``note: `python -m harness` is deprecated, use `python -m radark`
  (kept for at least one release)`` — then `raise SystemExit(radark.__main__.main())` with the same `sys.argv`
  handling as `radark/__main__.py`'s own `if __name__ == "__main__"` block. Stdout and the exit code are those of
  `radark`. argparse's `prog` is the fixed string `python -m radark`, so `--help` and usage errors are identical.
- `harness/__init__.py`: re-export `radark`'s public names and install a small `importlib.abc.MetaPathFinder` that
  maps `harness.<sub>` (except `harness.__main__`) to the already-imported `radark.<sub>` module object, so
  `from harness.state import GoalRun` yields `radark.state.GoalRun`. `harness.__main__` is excluded from the finder
  because `python -m harness` must run the alias file (to print the note); when that file is *imported* instead of
  run (`__name__ != "__main__"`), it replaces itself in `sys.modules` with `radark.__main__`, so
  `from harness.__main__ import main, Dispatcher` gives the dispatcher's own objects and does not start a run. No
  warning on import, to keep test output and the hooks quiet.

Alternative rejected: alias only for `-m` — simpler, but old scripts using `from harness.__main__ import main`
(e.g. the `note` one-liners in tests and possibly the owner's scripts) would break.

Alternative rejected: a symlink or a `.pth` trick — not portable on Windows and fragile in wheels.

`console.log` captures stderr, so the deprecation line appears there once per start; this is acceptable and is the
point of the note.

### D3. Packaging

`pyproject.toml`: `radark = "radark.__main__:main"`; `packages.find.include = ["radark", "radark.*", "harness"]`;
`exclude = ["radark.tests", "radark.tests.*"]`; `package-data` keyed `radark` with the same patterns. The version is
not bumped here (release is the owner's step); the apply session may note in the result that a minor bump fits.

### D4. Texts and docs

All engine texts and docs listed in Context switch to `python -m radark` / `radark/`. The deprecation sentence
appears once in `README.md` (where the commands are introduced); `radark/README.md` and `CLAUDE.md` refer to
`python -m radark` and the test command `python -m pytest radark/tests`. Example config/run names
(`harness.toml`, `.harness/`) stay as they are.

### D5. Tests

- Existing tests move to `radark/tests` and import `radark.`.
- New `radark/tests/test_alias.py`:
  - `python -m radark --help` and `python -m harness --help` (subprocess, repository root on `PYTHONPATH`): same
    stdout, both exit 0, the alias's stderr has exactly one deprecation line.
  - `dry-run` on a temp config with the fake `ho`/`claude` (existing conftest helpers): same stdout and exit code via
    both names; an unknown command gives the same exit code via both.
  - `import harness.state` is `radark.state`; `from harness.__main__ import main` gives `radark.__main__.main`
    and starts nothing.
  - `runner.HOOKS_DIR` and the sandbox script path resolve inside the `radark` package directory, and the generated
    session settings name only `radark/hooks/...` scripts.
- Install check (task, not an automated test, because it needs network-free pip in a temp venv and takes time):
  `python -m venv <tmp>` + `pip install --no-deps -e .` (or `pip wheel --no-deps .` and inspect the wheel) shows both
  `radark` and `harness` packages and `radark --help` starts. `--no-deps` avoids fetching radark-handover; the
  result is reported in `ho done`.
- Grep check (task): no `harness.` import, `-m harness`, or `harness/` path in code and docs except the alias package,
  `test_alias.py`, the one deprecation sentence, the unchanged names `harness.toml`/`.harness`/
  `harness.toml.example`, spec IDs, and historical records (Non-Goals).

## Risks / Trade-offs

- [Two packages named in one wheel] → the alias is two tiny files with no logic beyond forwarding; tested.
- [Meta-path finder surprises] → it only handles names starting with `harness.` and returns existing `radark`
  modules; if it proves fragile in apply, fall back to `-m`-only plus a re-exporting `harness/__init__.py`, and say so
  in the `ho done` result (the handover allows either, with the choice stated).
- [Stale installed copy during development] → the pipeline runs an installed release; this working tree is not
  installed by the session. The owner reinstalls after release; nothing else changes for running pipelines.
- [Deprecation line in `console.log`] → one line per start; harmless.

## Assumptions (unattended run)

- Alias covers imports as well as `-m` (D2), since the handover asks for it "if cheap".
- Historical documents are not rewritten (Non-Goals).
- No version bump in this change; release and reinstall are the owner's.

## Apply notes

- D2 was implemented as designed (the meta-path finder works; no fallback was needed): the alias covers both
  `python -m harness` and `import harness...`.
- Historical records keep their wording (`docs/decisions/0001-orchestration-harness.md` "built as `harness/`",
  `docs/research/spikes.md` "created by `harness/sandbox/make_sandbox.py`"); only their pointers to the package README
  (`radark/README.md` → *Verification results*) were updated, so the links resolve today.
- Tests that assert the `clear` hint (`test_escalation.py`, `test_prompts.py`) now assert `python -m radark clear <ID>`;
  `test_alias.py` holds the alias, path and session-settings checks (tasks 2.2 and 3.3).
- Install check (5.2) used `pip wheel --no-deps` on a copy of the tree outside the repository plus a temp venv: the wheel
  holds `harness/__init__.py`, `harness/__main__.py`, `radark/*` with `hooks/*.py`, `sandbox/make_sandbox.py` and
  `README.md`, no tests; `radark --help`, `python -m harness --help` and `import harness.state` work there.
