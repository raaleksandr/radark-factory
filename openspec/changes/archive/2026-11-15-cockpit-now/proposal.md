# Proposal: cockpit, part 3 — current state of running pipelines (Now tab)

Handover: **HO-20261115-xspc** (RB-023, "Cockpit, part 3: current state of running pipelines (Now tab)"), from
`radark-product`. Builds on the cockpit of part 1 and part 2 (changes `owner-cockpit` and `cockpit-history`,
archived).

## Why

The cockpit shows what the owner is asked for (Owner) and what the pipelines did (History), but not what is
happening right now. To see whether a pipeline is running, in a goal run or a regular one, and which sessions it
has open, the owner today looks at the machine directory's instance records, the run directory's `goal.json` and
the tail of `runs.jsonl` by hand. The owner wants this at a glance in a third, read-only **Now** tab, clean enough
for a webinar.

## What Changes

- The cockpit's third tab (a placeholder "Pipelines status — coming later" until now) becomes the **Now** tab:
  **one card per pipeline the cockpit shows** (the registered ones plus `--config`), running or not, the pipeline
  named on every card.
- Per card:
  - **State** `running` (a live dispatcher instance for this configuration / run directory), `not running`, or
    `unknown` (the run directory or the configuration cannot be read); when running: the instance's start and PID.
    Two live instances for one pipeline (should not happen) are both shown, without an error.
  - **Goal run** (goal file name and start, from the run directory's `goal.json`, only while it is `running` and
    the pipeline has a live instance) or **regular run**.
  - **Sessions running now**: team, handover ID, title (from `ho list`, "unknown" if not listed), phase, start and
    elapsed time — sessions with a `session_start` and no end after the latest `dispatcher_start`, as in History,
    and only while an instance is live; without a live instance they are listed as **interrupted**.
  - **Last event**: time and kind of the newest run-log record.
  - When not running: the time and outcome of the last session and the time of the last `dispatcher_start` and of
    the last stop record, when known.
- A **machine line** on top: session slots in use / the machine limit (from `slots/` and `machine.toml`), plus the
  number of live instances that belong to no shown pipeline.
- **New read-only API** `GET /api/now` with the same request checks as the other routes. It writes nothing,
  claims no lock or slot for longer than a probe, and **removes no stale record** (unlike the dispatcher's own
  probe): liveness is decided by a read-only OS-lock probe.
- The page refreshes the Now tab every 10 s while it is active (other tabs keep 30 s); times in the local time
  zone, durations `1 h 05 min`.
- README "Cockpit" section: what Now shows and where it reads from.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `owner-cockpit`: adds the Now tab (cards, state, goal or regular run, running sessions, last event, last run
  facts, machine line, API, read-only liveness) and updates the page-tabs and documentation requirements.

## Impact

- Code: new module `radark/cockpit_now.py` (pure functions plus the read-only probe), `radark/cockpit.py` (route
  `GET /api/now`, `Cockpit.now()` reusing `_load()`, the History `LogCache` and `_list_all`),
  `radark/machine.py` (a read-only probe helper next to `probe`, which keeps its behaviour),
  `radark/cockpit_page.html` (Now tab), tests in `radark/tests/` (new `test_cockpit_now.py`,
  `test_cockpit_now_ho.py`), README and `radark/README.md`.
- No new dependency (standard library only), no build step, no CDN; no `ho` change needed (`ho list --status all
  --json` already gives titles). No change to what the dispatcher writes (instance records, `goal.json`,
  `runs.jsonl`).
