# Tasks

## 1. Tests without a real keep-awake request

- [ ] 1.1 In `harness/tests/conftest.py`, make the `env` fixture replace the `Keeper` used by `harness.__main__` with a no-op fake (design D2), leaving `test_keep_awake.py`'s own `FakeKeeper` fixture working; verify `python -m pytest harness/tests -q` still passes with the default still `off`

## 2. Default keeps awake for the whole run

- [ ] 2.1 Check first that `harness-keep-awake-covers-until` is applied (design D3); if it is not, stop and tell the owner
- [ ] 2.2 In `harness/config.py`, change the default of `[loop] keep_awake` and of `Config.keep_awake` to `on` (design D1); verify with tests in `harness/tests/test_keep_awake.py`: no key → mode `on`; `keep_awake = "off"` → mode `off`; a run without the option starts the keeper, prints `Keep awake: whole run` and logs `keep_awake_setting` with mode `on`; `--keep-awake off` and `[loop] keep_awake = "off"` → no line, no record, no keeper; `dry-run` without the option prints `Would keep awake: whole run`; a goal run's `goal_start.keep_awake` is `on`
- [ ] 2.3 Update other tests that compare full start or `dry-run` output for the new `Keep awake: whole run` line; verify `python -m pytest harness/tests -q` passes
- [ ] 2.4 Update `harness/README.md` (`[loop]` table, "Keep awake", "Screen off for the night") and `harness.toml.example` (design D4); verify the text matches the delta spec scenarios "Default keeps awake for the whole run" and "Default does not keep awake"

## 3. Check

- [ ] 3.1 Run `python -m harness dry-run` and `python -m harness dry-run --keep-awake off`; verify the first prints `Would keep awake: whole run` and the second prints no keep-awake line

## Workflow follow-up

- Archive `harness-keep-awake-covers-until` before this change; then sync this delta into `openspec/specs/harness-dispatcher/spec.md` and archive after the owner accepts it.
- Update the assistant memory `harness-keep-awake-only-on-request`: runs keep the computer awake by default; pass `--keep-awake off` only when the owner asks to let it sleep.
