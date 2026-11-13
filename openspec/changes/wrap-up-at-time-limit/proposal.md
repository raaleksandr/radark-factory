# Proposal: wrap-up instead of a cut at the last time limit

Handover: **HO-20261113-5lbl** (backlog item RB-015), from `radark-product`.

## Why

A work session that keeps progressing is extended by its limit checks, but when no extension is left it is killed
by `max_time` in the middle of a step. The running step is lost, nothing is committed or reported, a resumed
session then starts all over with full limits, and nobody sees that the task was simply too big for one session.
Today (`radark/runner.py`, `Runner.run()`): when the deadline callback returns `None` or the checks are used up
(`expired`), the next loop iteration sets `timeout_reason = "max_time"` and kills the process tree.

## What Changes

- **Wrap-up at the last limit.** When a work session for a handover reaches its deadline and no extension is left
  (the last limit check was used, `limit_checks = 0`, or there is no product team to check), the dispatcher stops the
  process and at once resumes the same Claude Code session with a **wrap-up prompt**, limited to a grace period:
  commit what works, report what is done the way the phase reports it (apply: check off finished tasks, `ho done`
  with a `Left:` list), and name what is left so it can be handed over as a follow-up. Only a wrap-up session still
  running after the grace period is cut by `max_time`, as today (the existing resume-after-timeout rules then apply).
- **No wrap-up for a hung session.** A session the product team judged `hung` at a limit check, or whose check gave
  no valid verdict, is cut by `max_time` exactly as today.
- **New setting** `[loop] wrap_up_minutes` (default 15; 0 turns the wrap-up off and restores the plain cut).
- **Visible signal of a too-big task.**
  - Run log (`runs.jsonl`): `wrap_up_start` (handover, phase, elapsed, extensions used, grace) and `wrap_up` (the same
    plus the wrap-up session, its outcome and duration); a console `!` line when the wrap-up starts and an end line
    for the wrap-up session.
  - The item's state keeps a short time-limit history (each wrap-up and each cut by a time limit with its extensions
    used); the product team's **review prompt** for that handover gets one paragraph naming it and asking to check
    the `Left:` list and to split or record a follow-up if the task was too big.
- `radark/README.md` "Time limits" / "Limit check" describe the wrap-up, the setting and the signal.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Configuration* (new `wrap_up_minutes`), *Session time limits* and *Verdict of a limit
  check* (the last deadline wraps up instead of cutting), new requirements *Wrap-up at the last time limit* and
  *Signal of a too-big task*.

## Impact

- `radark/config.py`: `wrap_up_minutes` (default 15, `>= 0`).
- `radark/runner.py`: the deadline callback may answer "wrap up"; the runner then ends the process with
  `interrupt_cause = "wrap_up"` instead of `max_time`.
- `radark/__main__.py`: `limit_watch` answers "wrap up" when extensions are used up (and also for work sessions
  without checks); `session()` runs the wrap-up resume with the grace period as its maximum duration and no limit
  check; log events, console lines, state history.
- `radark/prompts.py`: `wrap_up_message(...)`, the review paragraph.
- Tests: new `radark/tests/test_wrap_up.py` (fake `claude`), adjustments in `test_limit_check.py` where a session
  ran out of extensions.
- No `ho` change, no new hub writes.
