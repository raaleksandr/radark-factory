# Tasks

Change for HO-20261113-xk2k (RB-006).

## 1. Tests without a real keep-awake request

- [x] 1.1 In `radark/tests/conftest.py`, make the `env` fixture replace the `Keeper` used by `radark.__main__` with a no-op fake (design D2), leaving `test_keep_awake.py`'s own `fake_keeper` fixture working; verify `python -m pytest radark/tests -q` still passes with the default still `off`

## 2. Default keeps awake for the whole run

- [x] 2.1 Add the `default` field to `KeepAwake` (`radark/awake.py`) and change the default of `[loop] keep_awake` and of `Config.keep_awake` in `radark/config.py` to `KeepAwake("on", text="on", default=True)` (design D1); verify with tests in `radark/tests/test_keep_awake.py`: no key → mode `on` with `default` set; `keep_awake = "on"` → mode `on` without it; `keep_awake = "off"` → mode `off`
- [x] 2.2 In `radark/__main__.py`, add the default note to `keep_awake_text`, and skip the `!` line, the record and the keeper for a default setting on a system without the power API (design D1, D5); verify with tests: a run without the option starts the keeper, prints `Keep awake: whole run (default; --keep-awake off lets the computer sleep)` and logs `keep_awake_setting` with mode `on`; `--keep-awake off` and `[loop] keep_awake = "off"` → no line, no record, no keeper; an explicit `--keep-awake` or `keep_awake = "on"` prints `Keep awake: whole run` without the note; `dry-run` without the option prints `Would keep awake: whole run (default; --keep-awake off lets the computer sleep)` and with `--keep-awake off` no keep-awake line; `--until 12:00` alone prints the default line and `--until 12:00 --keep-awake 12:00` the covered-moment line without the note (design D3); a goal run's `goal_start.keep_awake` is `on`; a default setting with `os.name` not `nt` prints no `!` line and writes no record, while an explicit `on` still prints the `!` line
- [x] 2.3 Update other tests that compare full start or `dry-run` output for the new keep-awake line; verify the full suite `python -m pytest radark/tests` passes and note the count and any failing or flaky tests per hub `AGENTS.md` §10
- [x] 2.4 Update `radark/README.md` (`[loop]` table, "Keep awake", "Screen off for the night") and `harness.toml.example` (design D6); verify the text matches the delta spec scenarios "Default keeps awake for the whole run" and "Default does not keep awake" and names no private data

## 3. Check and hand back

- [x] 3.1 On a sandbox config (`python radark/sandbox/make_sandbox.py <tmp>`), run `python -m radark --config <tmp>/harness.toml dry-run`, then with `--keep-awake off`, with `--keep-awake` and with `--until 12:00`; verify the first and last print `Would keep awake: whole run (default; --keep-awake off lets the computer sleep)`, the second no keep-awake line, the third `Would keep awake: whole run`; record the exact texts for `ho done`
- [x] 3.2 Commit locally (no push, tag, release or reinstall) with a message citing HO-20261113-xk2k; verify `git status` is clean
- [x] 3.3 `ho done HO-20261113-xk2k -m "..."` listing the change name, the commit(s), the test count, the exact start-line and `dry-run` texts (default, explicit `on`, `off`, `--until 12:00` alone), the D3 and D5 decisions, and any failing or flaky tests; then `ho sync`

## Notes

- The draft's task "check covers-until is applied" is dropped: `keep-awake-covers-until` is archived (design D4).
- Archiving this change and syncing its delta spec happen in the separate archive phase, after the author closes HO-20261113-xk2k; they are not tasks of this change.
- Apply notes: 1.1 was checked with `radark/tests/test_keep_awake.py` (92 passed, default still `off`); the full suite
  ran once after 2.1-2.2 (536 passed, 221 s, no failing or flaky tests). No other test compared the full start or
  `dry-run` output, so 2.3 changed only `test_keep_awake.py`. `fake_keeper` now requests `env`, so the recording fake
  is always installed after the no-op keeper. The default is a module constant `radark.awake.DEFAULT`.
- 3.1 sandbox texts: `dry-run` and `dry-run --until 12:00` → `Would keep awake: whole run (default; --keep-awake off
  lets the computer sleep)`; `--keep-awake off` → no keep-awake line; `--keep-awake` → `Would keep awake: whole run`.
