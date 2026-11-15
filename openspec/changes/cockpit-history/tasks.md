# Tasks

Change for HO-20261115-u25v (RB-022, cockpit part 2: history of finished work). Tests use fake `ho` / `claude`, a
temporary `RADARK_MACHINE_DIR`, invented `runs.jsonl` files and, in one module, the installed `ho` on a throw-away
hub made with `ho init` (design H9); never the owner's hub, never a browser. Neutral names only (`product`, `app`,
`owner`, pipelines `alpha` / `beta`), invented IDs `HO-…`. Commits stay local: no push, tag, release or reinstall.

## 1. History data (pure functions)

- [ ] 1.1 New `radark/cockpit_history.py`: tolerant run-log parsing and `LogCache` keyed by size + `st_mtime_ns`
  (design H2). Verify in new `radark/tests/test_cockpit_history.py`: a non-JSON line, a non-object line, a line
  without `time` and a half-written last line are skipped and counted; a missing file gives no records; a second
  read with an unchanged file does not re-parse (patched parser call count); an appended line is seen on the next
  read.
- [ ] 1.2 Session building (H3): FIFO pairing by team / handover / phase, unmatched `session_end`, `interrupted`,
  open sessions closed by a later `dispatcher_start`, running sessions, timed-out outcome, missing fields. Verify
  with tests for each case, including two pipelines' logs and a session of the same team on two handovers at once.
- [ ] 1.3 Rows, totals and order (H4): one row per (pipeline, handover), sessions in time order, working time and
  wall time, newest first, sessions without a handover counted apart. Verify: propose / apply / archive in order;
  30 min + 35 min sessions at 09:00 and 11:00 → working 3900 s, wall 9300 s; same handover in `alpha` and `beta`
  → two rows.
- [ ] 1.4 Results and escalated badge (H5): the result table from `ho list` items and the row's teams; unknown for
  a missing item or a failed hub. Verify every kind (accepted, in review, returned, open, declined, unknown) and the
  escalated badge from `escalation`, `escalation_sent` and `session_end.escalations`.
- [ ] 1.5 Periods, filters, summary (H6): `last-run` per pipeline (no `dispatcher_start` → whole log), `24h`,
  `7d`, `all`, overlap rule incl. a session spanning the window start and a running session, pipeline filter,
  summary counts incl. sessions without a handover. Verify with a fixed `now` in tests.

## 2. Server and page

- [ ] 2.1 `radark/cockpit.py`: `Cockpit.history(pipeline, period)` (run directories from the loaded
  configurations, one `ho list --status all` per hub in parallel after the contract check, the shared `LogCache`)
  and the route `GET /api/history` with the part-1 request checks and headers; 400 on an unknown period; no paths,
  prompts or session result texts in the JSON (H7). Verify in `radark/tests/test_cockpit_history.py` with the
  part-1 server harness and fake `ho` (extend `radark/tests/fakes/fake_ho.py` with `list --status all` without
  `--to` if needed): filtered answer, 400, 403 on a foreign Host, two pipelines on one hub → one `list` call in the
  `.calls` file, no write `ho` call, no file changed in the run directories.
- [ ] 2.2 `radark/cockpit_page.html` (H8): History tab enabled (third tab still a placeholder), pipeline select,
  period buttons, summary line, rows with labelled totals, result and escalated badges, expandable sessions,
  "running since …", local times, `H h MM min` durations, expanded rows kept across refreshes, refresh only while
  the tab is active; hub text through `textContent` only. Verify with tests on the served page: no external
  resource reference, the History tab button is not disabled, the history render code uses no `innerHTML`; plus
  the manual check in 3.3.
- [ ] 2.3 End-to-end with the installed `ho` (H9): in `radark/tests/test_cockpit_history.py` (or a new
  `test_cockpit_history_ho.py`), `ho init --teams product=Product,app=App,owner=Owner` in `tmp_path`, invented
  handovers driven to accepted, in review, returned, open and declined with `ho new` / `ack` / `done` / `return` /
  `decline` / `close`, two configurations `alpha` and `beta` on that hub with invented `runs.jsonl` (plus an ID the
  hub does not know); check each result through `GET /api/history`. Fails with a clear message when `ho` is not on
  `PATH` (no skip).

## 3. Docs and checks

- [ ] 3.1 README "Cockpit" section: what the History tab shows, the filters, and where it reads from (each
  pipeline's `runs.jsonl`, the hub through `ho list`); `radark/README.md`: the `/api/history` route and the new
  module. Neutral names only. Verify by reading the sections against the spec requirement "Cockpit documentation".
- [ ] 3.2 Full suite: `python -m pytest radark/tests` (through `radark-test-slot` when run by a pipeline); all pass.
  Failing or flaky tests follow hub `AGENTS.md` §10 and are reported in the result, including whether the known
  RB-024 / RB-025 ones still occur.
- [ ] 3.3 Manual check in the sandbox: `python radark/sandbox/make_sandbox.py <tmp dir>`, `python -m radark
  --config <tmp dir>/radark.toml dry-run` (or invented records appended to the sandbox `runs.jsonl`), then
  `python -m radark --config <tmp dir>/radark.toml cockpit --no-browser`; request `/api/history?period=all` and
  compare with the sandbox `runs.jsonl` and `ho show`. Record the result in the `ho done` message. Nothing from the
  sandbox is committed.
- [ ] 3.4 Public-repository check: `git diff` of the change contains no owner path, product or company name, hub or
  run excerpt; IDs are invented.
- [ ] 3.5 Commit locally (no push, tag, release or reinstall), `ho sync`, then
  `ho done HO-20261115-u25v -m "<commits, test counts, how to see the History tab (npm run cockpit / radark cockpit
  → History), decisions that differ from the handover (design Assumptions: H2 full re-read, H3 FIFO pairing and
  running sessions not in totals, H5 result from ho list recipient states without ho show, H6 rows keep all
  sessions while the summary counts the window)>"` and `ho sync`. This is the last step of apply.

## Notes

- Archiving this change and syncing its specs are not tasks of apply: they run in a separate archive phase after
  `radark-product` closes HO-20261115-u25v.
