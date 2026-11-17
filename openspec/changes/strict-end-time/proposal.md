# Proposal: opt-in strict end time for `--until`

Handover: **HO-20261117-aor7** (RB-020, "opt-in strict end time for --until (wrap up at the end time, no
extension)"), from `radark-product`.

## Why

`--until` only stops new steps: a session running at the end time runs to its end, and a work session's limit
checks can even extend it after the end time has passed. In a real run (neutral form) the end time was 12:00, the
last apply session started at 11:02, at 14:02 its limit check gave it +60 min, and it ran to 14:47. The owner had
planned the computer for 12:00 and found it busy hours later. The owner decided (2026-11-17) on a new opt-in mode in
which the end time holds: end time + wrap-up time at most. The default stays as it is.

## What Changes

- New opt-in **strict end time**: CLI flag `--until-strict` (with `--no-until-strict` to turn a configured default
  off for one run) on `run` (also `--once`, `--goal`, `--dry-run`) and `dry-run`, and config key
  `[loop] until_strict = false` (a boolean, validated like the other `[loop]` keys). It only matters together with
  `--until`.
- With strict mode, at the end time every running session of the run (also parallel ones):
  - a **work session** is stopped and at once resumed with an end-time **wrap-up** prompt (the existing wrap-up
    mechanism, its own text: commit what works, record what is left, report `done` only if the phase is complete),
    limited to `wrap_up_minutes`; then it is stopped. A session already in a wrap-up keeps its grace period, capped at
    end time + `wrap_up_minutes`. With `wrap_up_minutes = 0` the session is stopped at the end time;
  - **no limit check and no extension** is given after the end time; a limit check running at the end time ends with
    its session;
  - a **non-work session** (triage consultation, limit check, goal check, idle ask) gets the same grace period
    without a prompt and is then stopped;
  - a stopped session is `interrupted` with cause **`end_time`** (not an error, not "no progress"); the next run
    resumes it in its own context with a message naming the end time, as after any interruption. An end-time
    wrap-up that completes its phase keeps its normal outcome;
  - the run then ends as it does today at the end time (exit 0; a goal run ends with `limit`).
- Without strict mode (default) nothing changes for sessions, but the first time the end time passes while a session
  is still running, the console and `console.log` print one line, once per run:
  `Note: the end time 12:00 has passed; the running session finishes. To end on time, use --until-strict.`
  (logged as `end_time_passed`).
- The start line, `run_until` in `runs.jsonl`, `goal_start` and `dry-run` show the mode, e.g.
  `Run ends at 12:00 today, in 118 min (strict: running sessions wrap up at 12:00, stopped by 12:15)` or
  `(running sessions finish first)`.
- `--until-strict` / `--no-until-strict` without `--until` is refused (exit 2, a message naming both options) before
  any session; the config key without `--until` has no effect and no message.
- `radark/README.md`: `[loop]` table, **Pause / stop** (`--until`) and **Time limits** / **Wrap-up** updated.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Ending a run at its end time* (a running session is stopped in strict mode), *Reporting an
  end time* (the mode in the start line and `dry-run`); new requirements *Strict end time*, *Validating the strict
  end time option*, *Stopping sessions at a strict end time*, *No extension after a strict end time*, *End-time
  wrap-up prompt*, *Outcome of a session stopped at a strict end time* and *Hint when a session runs past a
  non-strict end time*.

## Impact

- `radark/runner.py`: `Runner.run` gets a wall-clock moment `end_at` and a callback asked once when it passes (stop
  the session with cause `end_time`, or go on); an injectable wall clock for tests.
- `radark/__main__.py`: `Dispatcher.until_strict`; `session()` passes `end_at` and resumes a stopped work session
  with the end-time wrap-up; `limit_watch` gives no check after the end time; the hint; start line, `dry-run`,
  `run_until` / `goal_start` fields; `--until-strict` parsing; `INTERRUPT_CAUSE` gets `end_time`.
- `radark/prompts.py`: end-time wrap-up message; `INTERRUPT_LABELS["end_time"]` for the next run's resume.
- `radark/config.py`: `until_strict` key.
- Tests: new `radark/tests/test_until_strict.py`; start-line expectations in `test_until.py` / `test_keep_awake.py`.
- No change to the hub, the `ho` contract, selection or the state format beyond the new `end_time` cause.
