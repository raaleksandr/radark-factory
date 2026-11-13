# Tasks

Change for HO-20261113-aidk (RB-007).

## 1. Moment covered by the end time

- [ ] 1.1 Add the optional given-moment field to `KeepAwake` and a pure helper that replaces a keep-awake moment at or after the end time with the whole run, keeping the given moment; apply it in `radark/__main__.py` `main()` after `--until` and `--keep-awake` are read, for every command (design D1); verify with tests in `radark/tests/test_keep_awake.py`: equal moment → mode `on`, later moment → mode `on`, earlier moment → unchanged, no end time → unchanged, a range → unchanged, `on`/`off` → unchanged
- [ ] 1.2 Start line, `keep_awake_setting` record and `dry-run` text for the replaced setting (design D2); verify with tests that the start shows `Keep awake: whole run (until 12:00 given, the run ends at 12:00)`, the record has `mode: "on"` and the given moment, and `dry-run` prints `Would keep awake: whole run (...)`
- [ ] 1.3 Verify with a dispatcher test (fake clock and keeper state, fake `claude`/`ho`) that with end time 12:00 and keep-awake 12:00 a session still running at 12:00 keeps the computer awake until the run ends and no "Keep awake ended" line is printed at 12:00

## 2. Documentation and checks

- [ ] 2.1 Update `radark/README.md` "Keep awake" and "Pause / stop" (design D3); verify the text matches the new scenarios in the delta spec and names no private data
- [ ] 2.2 On a sandbox config (`python radark/sandbox/make_sandbox.py <tmp>`), run `python -m radark --config <tmp>/harness.toml dry-run --until 12:00 --keep-awake 12:00` and verify it prints the whole-run text; record the exact text for `ho done`
- [ ] 2.3 Run the full suite `python -m pytest radark/tests` and verify it passes; note the count and any failing or flaky tests per hub `AGENTS.md` §10

## 3. Hand back

- [ ] 3.1 Commit locally (no push, tag, release or reinstall) with a message citing HO-20261113-aidk; verify `git status` is clean
- [ ] 3.2 `ho done HO-20261113-aidk -m "..."` listing the change name, the commit(s), the test count, the exact start-line and `dry-run` texts, and any failing or flaky tests; then `ho sync`

## Workflow follow-up

- Archive the change (and sync its delta spec) in the separate archive phase, only after the author closes HO-20261113-aidk. Not a task of this change.
