# Tasks

## 1. Moment covered by the end time

- [ ] 1.1 In `harness/__main__.py`, after `--until` and `--keep-awake` are read for `run` and `dry-run`, replace a keep-awake moment at or after the end time with the whole run, keeping the given moment (design D1); verify with tests in `harness/tests/test_keep_awake.py`: equal moment → mode `on`, later moment → mode `on`, earlier moment → unchanged, no end time → unchanged, a range → unchanged
- [ ] 1.2 Start line, `keep_awake_setting` record and `dry-run` text for the replaced setting (design D2); verify with tests that the start shows `Keep awake: whole run (until 12:00 given, the run ends at 12:00)`, the record has `mode: "on"` and the given moment, and `dry-run` prints `Would keep awake: whole run (...)`
- [ ] 1.3 Verify with a dispatcher test (fake clock and keeper state) that with end time 12:00 and keep-awake 12:00 a session still running at 12:00 keeps the computer awake until the run ends and no "Keep awake ended" line is printed at 12:00

## 2. Documentation and check

- [ ] 2.1 Update `harness/README.md` "Keep awake" and "Pause / stop" (design D3); verify the text matches the new scenarios in the delta spec
- [ ] 2.2 Run the full test suite (`python -m pytest harness/tests -q`) and verify it passes
- [ ] 2.3 Check `python -m harness dry-run --until 12:00 --keep-awake 12:00` and verify it prints the whole-run text

## Workflow follow-up

- Sync the delta spec into `openspec/specs/harness-dispatcher/spec.md` and archive the change after the owner accepts it.
