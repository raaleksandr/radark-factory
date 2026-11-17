# Design: strict end-time suffix across midnight

## Context

See proposal.md (Why). The strict-mode suffix is built by `Dispatcher.until_mode()` in `radark/__main__.py` and is
printed by `start_until()` (`Run ends at ...`) and by `dry-run` (`Would end: ...`), both after `until_text()`, which
already names the end time's day relative to now (`today`, `tomorrow (date)`, `on date`). `day_clock(ts, now)` next to
it renders `12:00`, `12:00 tomorrow` or `12:00 on 2026-11-20` relative to `now`.

## Goals / Non-Goals

**Goals:** the "stopped by" clock is unambiguous across midnight; the same-day text is byte-for-byte unchanged.

**Non-Goals:** the `wrap up at HH:MM` part (it is the end time itself, whose day `until_text` already gives); the
`run_until` log record; the end line; the default (non-strict) suffix and the no-grace `stop at` suffix.

## Decisions

- **D1 — When the day is shown.** Only when `by.date() != at.date()` (the "stopped by" moment and the end time on
  different calendar days, local time). Otherwise `{by:%H:%M}` as now. Alternative — always use `day_clock(by, now)`:
  rejected, it would add `tomorrow` to a run ending tomorrow at 07:00 (`stopped by 07:15 tomorrow`), changing the
  same-day text the product decision says to keep.
- **D2 — Form and reference day.** Reuse `day_clock(by, now)` with `now = time.time()` (the same reference as
  `until_text` in the same line), giving `00:14 tomorrow` or `00:14 on 2026-11-20`. Alternative — reference the end
  time's day (`day_clock(by, until)`): rejected, `tomorrow` would then mean "the day after the end time" while
  `until_text` in the same line uses "tomorrow" relative to today, which would be contradictory. A consequence
  (accepted): if the end time is today and the grace crosses midnight the text is `tomorrow`; if the end time is on a
  later day the date is shown.
- **D3 — Wording.** Kept as the handover proposes (`stopped by 00:14 tomorrow`); the existing tests and spec
  scenarios suggest no clearer form. `day_clock` returns the clock only for today, which cannot happen under D1
  (by is after the end time, which is not before now in a valid run), so no special case is needed.
- **D4 — Testability.** `until_mode()` reads the current time through `time.time()`, which the tests already
  monkeypatch (`hm.time.time`), so no new parameter is needed.

## Risks / Trade-offs

- [The end time lies in the past at the start line (theoretical)] → `day_clock` would show `on <date>`; harmless and
  not reachable, since an end time in the past is rejected at start.
- [DST transition at midnight] → dates are taken from local `datetime.fromtimestamp`, the same as `until_text`; no
  additional handling.
