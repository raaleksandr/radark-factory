# Design: opt-in strict end time for `--until`

Handover: HO-20261117-aor7 (RB-020).

## Context

- `--until WHEN` sets `Dispatcher.until` (epoch seconds, wall clock, sleep counted). `ending()` / `until_end()`
  refuse new steps from that moment; waits are capped by `nap()` and `wait_workers()`. A running session is never
  touched (spec: *Ending a run at its end time*, scenario *Session running at the end time*).
- `Runner.run` measures its limits on the **awake** clock (`self.clock = clock.awake`): `max_s` (deadline), the
  inactivity limit, the wake grace. At the deadline it asks `on_deadline` in a thread; the dispatcher's
  `limit_watch` answers with seconds (an extension after a `progressing` limit check), `None` (cut by `max_time`) or
  `WRAP_UP` (stop with `interrupt_cause = "wrap_up"`; `session()` then resumes the session with
  `prompts.wrap_up_message`, `timeout_s = wrap_up_minutes * 60`, no limit check, no second wrap-up).
- An `interrupted` session (any `interrupt_cause`) is classified `interrupted`; `after_session` stores
  `resume_after_timeout = {reason: interrupt_cause, ...}` and the item's next session resumes it with
  `prompts.timeout_resume_message`, which uses `INTERRUPT_LABELS[reason]` for interruptions. The no-progress counter
  stays.
- The deadline is relative to the session's start on the awake clock; the end time is an absolute wall-clock
  moment. The end time can therefore not be expressed as a deadline: it needs its own check in the runner loop.

## Decisions

### D1. Names: `--until-strict` / `--no-until-strict` and `[loop] until_strict`

- CLI: `argparse.BooleanOptionalAction` on the `run` and `dry-run` parsers (the ones that take `--until`):
  `--until-strict` and `--no-until-strict`, default `None` (not given).
- Config: `[loop] until_strict`, default `false`. Validated: it must be a TOML boolean; anything else is a
  `ConfigError` "loop.until_strict must be true or false, not …" (like the other `[loop]` keys, before any session).
- Effective mode: the flag when given, else the config key. `Dispatcher.until_strict: bool`, set in `main()` next to
  `d.until`; never stored in state.
- **Flag without `--until`** (team decision asked for in the handover): refused, exit 2, before the `ho` check and any
  session: `--until-strict needs --until (an end time); without --until the run has no end time.` (the same for
  `--no-until-strict`, naming it). Reason: the flag alone does nothing, and a silent "accepted" would make the owner
  believe the run ends on time. There is no config end time, so the **config key without `--until`** is simply a
  default for runs that give one: no effect, no message.

### D2. The runner checks a wall-clock moment

`Runner.run(..., end_at: float | None = None, on_end_at=None)` and `Runner.wall = time.time` (injectable, as
`Runner.clock` is). In the poll loop, once per session, when `end_at is not None and self.wall() >= end_at` and the
session is not already being ended (`timeout_reason is None and interrupt_cause is None`), the runner calls
`on_end_at(r)` in the loop thread (it is quick: no consultation):

- `"stop"`: `r.interrupt_cause = "end_time"`, end the process tree (`self._end()`), mark the deadline handling
  `expired` so no limit check starts afterwards; a limit check thread already running is handled as today when the
  session ends (`on_deadline_abort`, its verdict ignored);
- anything else: go on as before (the default mode, D6).

`end_time` is a new interrupt cause; `classify` already turns every interrupt cause into `interrupted`.

### D3. Which moment each session gets

`G = wrap_up_minutes * 60`, `U = Dispatcher.until`. In `session()`:

| session | `end_at` (strict) | at `end_at` |
|---|---|---|
| work session, not a wrap-up | `U` | stop; resumed with the end-time wrap-up (D4) when `G > 0` |
| wrap-up session (time limit or end time) | `U + G` | stop (its own `timeout_s = G` on the awake clock also applies) |
| non-work session (triage consultation, limit check, goal check, idle ask) | `U + G` | stop, no prompt |

So every session of the run ends by `U + G` at the latest, and a work session gets the grace period after `U` to
wrap up. Non-work sessions are short and have no wrap-up prompt (they cannot "commit what works"); they get the same
grace period to finish their answer, then are stopped. An interrupted idle ask, goal check or triage consultation is
handled as any interrupted one today (asked again later / the asking session is resumed), i.e. by the next run.

In the default mode every session gets `end_at = U` too, but `on_end_at` only reports it (D6). Without `--until`
`end_at` is `None` and nothing changes.

With `G = 0` a work session is stopped at `U` without a wrap-up, as `wrap_up_minutes = 0` turns the time-limit wrap-up
off too.

### D4. End-time wrap-up of a work session

When a work session (not a wrap-up) returns with `interrupt_cause == "end_time"` and `G > 0`, `session()` handles it
like the `WRAP_UP` stop (log, console, then resume in the same step), with differences:

- prompt: new `prompts.end_time_wrap_up_message(cand, until_text, grace, index_lock, goal, profile)`: "The run's end
  time HH:MM was reached and the dispatcher stopped this session in the <phase> phase of <ID>. You have G min to wrap
  up; then the session is stopped. The step that was running was cut off … check `git status` … Start no new work.
  Commit what works. For apply: check off finished tasks and write the open ones under a `Left for a later run` note
  in `tasks.md`. Do not report the handover as done unless the phase is complete; the next run resumes this session."
  The time-limit wrap-up asks for `ho done` with `Left:`, because a too-big task is handed back to the author; an
  end time is not a sign of a too-big task, so the work continues in the next run instead.
- the resume runs with `wrap_up=True` (no limit check, no second wrap-up), `timeout_s = G`, `end_at = U + G`;
- log: `end_time_stop` (team, handover, phase, session, elapsed_s, until, grace_min) when the session is stopped,
  `end_time_wrap_up` (… wrap_up_session, outcome, interrupt_cause, duration_s) after the resume; console:
  `! app HO-…: end time 12:00 reached; asking the session to wrap up within 15 min`;
- not a `time_limits` entry of the item (that history feeds the review's "task may be too big" note; an end time says
  nothing about the task's size);
- **outcome of the step**: when the wrap-up session ends normally and the phase is complete
  (`phase_complete(cand, rec, w, since)`, the check `finished-outcome-after-denial` already uses), its outcome stays
  (`finished` as usual). Otherwise — it was stopped at `U + G`, or it ended without completing the phase — the step
  result gets `outcome = "interrupted"`, `interrupt_cause = "end_time"`, so `after_session` stores
  `resume_after_timeout` with reason `end_time` and the next run resumes the session in its own context. A wrap-up
  that ended in `usage_limit` or `waiting_for_owner` keeps that outcome (those have their own handling).
- the next run's resume message: `INTERRUPT_LABELS["end_time"] = "The previous run reached its end time and the
  dispatcher stopped this session (it may have wrapped up: see your last messages and tasks.md)"`.
- `INTERRUPT_CAUSE["end_time"] = "end time"` for the end line: `→ interrupted (end time) (1 h 02 min)`.

A time-limit wrap-up (`WRAP_UP`) that is running when `U` passes keeps going until its own grace ends, but no later
than `U + G` (D3); it is not stopped twice and gets no second wrap-up.

### D5. No extension after the end time

In strict mode `limit_watch.deadline()` returns at once, without a limit check, when `time.time() >= U`: `WRAP_UP` if
`G > 0`, else `None`. In practice the runner's `end_at` stop (D2) comes first (the session is stopped at `U`, before
any later deadline); this rule covers a deadline that falls in the same poll step and keeps "no extension after the
end time" true by construction. An extension granted *before* `U` stays, but cannot carry the session past `U`
because `end_at` stops it. The default mode keeps today's behaviour (checks and extensions after `U`).

### D6. The hint in the default mode

`on_end_at` in the default mode: under the dispatcher lock, if the hint was not printed in this run, print
`Note: the end time 12:00 has passed; the running session finishes. To end on time, use --until-strict.` (plural
`the running sessions finish` when more than one runs), log `end_time_passed` (until, sessions running), set the
flag; return `None`. Printed through `self.out`, so it also lands in `console.log`. Once per run: later sessions
(e.g. a time-limit wrap-up that starts after `U`) get `on_end_at` too, but the flag stops a second line. `HH:MM`
gets the date (`12:00 on 2026-11-18`) when the end time is not today, like `day_clock`.

### D7. Reporting the mode

- Start line (`start_until`): `Run ends at 12:00 today, in 1 h 58 min (strict: running sessions wrap up at 12:00,
  stopped by 12:15)`; strict with `G = 0`: `(strict: running sessions stop at 12:00)`; default: `(running sessions
  finish first)`.
- `run_until` gets `strict: true|false`; `goal_start` gets `until_strict`.
- `dry-run`: `Would end: 12:00 today, in 1 h 58 min (strict: …)` with the same suffix.
- The end line `End time 12:00 reached; ending the run.` stays.

### D8. Parallel sessions

Each worker's session gets its own `end_at` and `on_end_at` (D3); stops are per session, so with two running
sessions both are stopped at `U`, both wrap up in parallel, and `drain()` waits for both. `ending()` already starts
no new step after `U`; the end-time wrap-up is part of the running step, not a new step, so it is not blocked. The
hint is printed once per run (D6), under the lock.

## Risks / Trade-offs

- A stopped step loses the tool call that was running (as with any wrap-up): `claude -p` has no channel into a
  running session. Accepted by the owner ("work may stay unfinished").
- The wall-clock check runs in the 0.2 s poll loop: negligible cost.
- A computer that sleeps through `U`: on wake the runner sees `wall() >= end_at` and stops the session at once; the
  wrap-up then gets its grace period up to `U + G`, which may already have passed — then the wrap-up resume is
  skipped and the session is `interrupted` / `end_time` directly (checked in `session()` before resuming: no resume
  when `time.time() >= U + G`). The wake grace rule may also stop it first (cause `sleep`); either way it is resumed by
  the next run.

## Assumptions (unattended session, no owner to ask)

- Names chosen: `--until-strict` / `--no-until-strict`, `[loop] until_strict` (the handover's examples).
- The flag without `--until` is refused (D1), not ignored.
- The end-time wrap-up does not ask for `ho done` unless the phase is complete (D4): the handover says unfinished
  work is "resumed by a later run as today".
- Non-work sessions get the grace period, then are stopped without a prompt (D3).
- The default-mode start line also gets a suffix `(running sessions finish first)` so the mode is visible in both
  cases ("show the mode when `--until` is given"); existing start-line test expectations are updated for it.

## Tests (fake clock / fake claude, no real waits)

The runner's wall clock (`Runner.wall`) and the dispatcher's `time.time` are patched, so the end time is "reached"
inside a fake session without waiting; the fake claude's steps (`sleep`, `wait_for`) keep the session running while
the test moves the clock. Wrap-up grace is made short through `wrap_up_minutes` and the fake clock.
