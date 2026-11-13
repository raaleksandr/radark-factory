# Tasks

Handover: HO-20261113-6cg3 (RB-002). Start and end the session with `ho sync`.

## 1. Move the package

- [ ] 1.1 `git mv harness radark` (code, `hooks/`, `sandbox/`, `README.md`, `tests/` with `fakes/`); verify `git status` shows renames, not deletes and adds
- [ ] 1.2 Replace absolute `harness.` references in `radark/tests` (imports, `monkeypatch` string targets, the `-c` one-liners in `test_goal.py`, `harness.tests.conftest` imports) with `radark.`; verify `grep -rn "harness\." radark/tests` finds only `harness.toml` names
- [ ] 1.3 Update `pyproject.toml` per design D3 (console script `radark.__main__:main`, find include `radark`, `radark.*`, `harness`; exclude `radark.tests*`; package data keyed `radark`); verify `python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['scripts'])"`
- [ ] 1.4 Check every path built to the package, its hooks or sandbox (`runner.HOOKS_DIR`, `make_sandbox.py`, test `ROOT`/`FAKES`) and fix any that spell `harness/`; verify `python -m pytest radark/tests` passes in full (report the count; failing or flaky tests per hub `AGENTS.md` §10)

## 2. Engine texts name `python -m radark`

- [ ] 2.1 Change argparse `prog`, the module docstring, the `clear` hints in `radark/prompts.py`, the hooks-not-loaded and `--goal`/`--once` hints (`radark/README.md`), and the usage line and printed hints of `radark/sandbox/make_sandbox.py` to `python -m radark` / `radark/`; update the tests that assert these texts (`test_prompts.py`, `test_escalation.py`, others found by grep) and add an assertion that the escalation `clear` hint reads `python -m radark clear <ID>`; verify those tests pass
- [ ] 2.2 Add a test that `write_session_settings` names only scripts inside the `radark` package's `hooks` directory and that the sandbox script path is inside `radark/sandbox`; verify it passes

## 3. Compatibility alias `harness`

- [ ] 3.1 Add `harness/__main__.py` per design D2: when run, one deprecation line to stderr then `SystemExit(radark.__main__.main())`; when imported, replace itself in `sys.modules` with `radark.__main__`; verify `python -m harness --help` prints the same stdout as `python -m radark --help`
- [ ] 3.2 Add `harness/__init__.py` with the meta-path finder mapping `harness.<sub>` (not `__main__`) to `radark.<sub>`; verify `python -c "import harness.state, radark.state; assert harness.state is radark.state"`. If the finder proves fragile, fall back to `-m` only plus re-exports and record the choice in design.md and the `ho done` result
- [ ] 3.3 Add `radark/tests/test_alias.py` (design D5): `--help`, `dry-run` on a temp config with the fake `ho`/`claude`, and an unknown command via both names give the same stdout and exit code, the alias adds exactly one stderr line; `harness.state is radark.state`; `from harness.__main__ import main` is `radark.__main__.main` and starts nothing; verify the file passes

## 4. Docs

- [ ] 4.1 Update `README.md` (commands, test command, sandbox instructions) to `python -m radark` / `radark/`, with one sentence that `python -m harness` is a deprecated alias kept for at least one release; keep `harness.toml`, `.harness/`, `harness.toml.example` names; verify by reading the rendered sections
- [ ] 4.2 Update `radark/README.md`, `CLAUDE.md` (test command `python -m pytest radark/tests`, sandbox path `radark/sandbox/make_sandbox.py`, start command) and `docs/` where a reader is told to run a command today (historical records stay, design Non-Goals); verify links in `CLAUDE.md` and `README.md` point to existing files

## 5. Integration checks

- [ ] 5.1 Grep check: `grep -rnE "harness\.[a-z_]|-m harness|harness/" --exclude-dir=.git --exclude-dir=archive .` shows only the alias package, `test_alias.py`, the one deprecation sentence, `harness.toml`/`.harness`/`harness.toml.example` names, spec IDs and historical records; fix anything else
- [ ] 5.2 Install check in a temp venv outside the repository: `pip install --no-deps -e .` (or `pip wheel --no-deps .` and list the wheel) shows both `radark` and `harness` packages and package data (`radark/hooks/*.py`, `radark/sandbox/*.py`, `radark/README.md`); the venv's `radark --help` and `python -m harness --help` start; delete the venv; record the result for `ho done`. Do not install into the owner's environment
- [ ] 5.3 Sandbox check: `python radark/sandbox/make_sandbox.py <tmp>` then `python -m radark --config <tmp>/harness.toml dry-run` and the same with `-m harness`; verify same stdout and exit code
- [ ] 5.4 Full suite `python -m pytest radark/tests` passes; note the count and any failing or flaky tests per hub `AGENTS.md` §10
- [ ] 5.5 Commit locally (no push, tag, release or reinstall), with a message citing HO-20261113-6cg3; verify `git status` is clean
- [ ] 5.6 `ho done HO-20261113-6cg3 -m "..."` listing the commit(s), the test count, that the alias covers `-m` and imports (or what was chosen), that the owner needs no change in team settings (hooks come from the installed package per session) and only reinstalls, optionally the separate idea of renaming `harness.toml`/`.harness/`; then `ho sync`

## Workflow follow-up

- Archive the change (and sync its specs) in the separate archive phase, only after the author closes HO-20261113-6cg3.
