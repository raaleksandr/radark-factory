# Proposal: cockpit, part 2 — history of finished work

Handover: **HO-20261115-u25v** (RB-022, "Cockpit, part 2: history of finished work"), from `radark-product`.
Builds on the cockpit of part 1 (change `owner-cockpit`, archived).

## Why

The cockpit (`radark cockpit`) shows what the owner is asked for, but not what the pipelines actually did. To see
which handovers were worked on, in which phases, how long it took and how it ended, the owner today reads each
pipeline's `runs.jsonl` and runs `ho show` by hand. The owner wants this as a clean, read-only **History** tab in
the same cockpit, for every registered pipeline, good enough to show in a webinar.

## What Changes

- The cockpit's **History** tab (a placeholder in part 1) becomes active: **one row per handover per pipeline** with
  pipeline, ID, title, team(s), first start, last end, total (working time = sum of session durations, wall time =
  first start → last end, both labelled) and result; expanding a row shows its **sessions in time order**: phase,
  start, end, duration, outcome, denial / escalation counts when non-zero; a session still running is shown as
  "running" with its start.
- **Result** from the hub (current state, read through `ho` only): accepted, in review (done / responded, not yet
  closed), returned, open, declined, unknown (handover not in the hub or hub unreadable); an **escalated** badge
  when the run log has an escalation for the handover.
- **Filters**: pipeline (all / one) and period (last run — per pipeline since its latest `dispatcher_start` —, last
  24 h, last 7 days, all); a handover belongs to a period when one of its sessions overlaps it; newest first; a
  one-line summary above the list (handovers, sessions, working time, accepted, plus the count and time of sessions
  without a handover, which are not rows).
- **New read-only API** `GET /api/history?pipeline=...&period=...` with the same request checks as part 1; it
  writes nothing anywhere.
- **Run log reading**: each pipeline's `runs.jsonl` is parsed tolerantly (bad or partial lines skipped, old records
  without some fields accepted) and cached by file size + modification time, so the 30 s refresh stays cheap with
  a few thousand lines. Each hub is read once per refresh (`ho list --status all --json`), even when several
  pipelines share it; rows are never merged across pipelines.
- The page keeps room for a third tab (RB-023, running pipelines — out of scope).
- README "Cockpit" section: what History shows and where it reads from.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `owner-cockpit`: adds the history of finished work (rows, sessions, totals, results, filters, summary, API, run
  log reading and caching) and updates the page-tabs and documentation requirements.

## Impact

- Code: `radark/cockpit.py` (new history route and data gathering, or a new module `radark/cockpit_history.py`
  used by it), `radark/cockpit_page.html` (History tab), tests in `radark/tests/` (new `test_cockpit_history.py`,
  fake `ho` reused), README and `radark/README.md`.
- No new dependency (standard library only), no build step, no CDN; no `ho` change needed (`ho list --status all
  --json` gives status and per-team recipient states). No change to what the dispatcher writes in `runs.jsonl`.
