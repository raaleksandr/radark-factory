# Tasks

Change for HO-20261115-xspc (RB-023, cockpit part 3: current state of running pipelines, Now tab). Tests use fake
`ho` / `claude`, a temporary `RADARK_MACHINE_DIR`, invented instance records, `goal.json` and `runs.jsonl` files,
helper subprocesses that hold instance locks and, in one module, the installed `ho` on a throw-away hub made with
`ho init` (design N10); never the owner's hub or machine directory, never a browser. Neutral names only
(`product`, `app`, `owner`, pipelines `alpha` / `beta`), invented IDs `HO-…`. Commits stay local: no push, tag,
release or reinstall.

## 1. Now data

- [ ] 1.1 `radark/machine.py`: `probe_readonly(lock_path) -> bool | None` (design N2): no `O_CREAT`, nothing
  unlinked or written; `probe` unchanged. Verify in new `radark/tests/test_cockpit_now.py`: a lock held by a helper
  subprocess → `True`; a free lock → `False` and the lock file and its `.json` still exist; no lock file → `False`
  and no file created; existing machine tests still pass.
- [ ] 1.2 New `radark/cockpit_now.py`: read-only instance scan (`instances/*.lock` + records, unknown probes kept
  apart, records without a lock ignored, no directory created) and matching to pipelines by normalized config, else
  run directory (N2, N3); instance `started` parsed as local time. Verify: live vs. stale vs. no record; two live
  instances for one pipeline; match by run directory; an unshown config counted as other instance; `started`
  converted to UTC.
- [ ] 1.3 Card state, goal, sessions, facts (N4–N6): `unknown` for a broken configuration and an unreadable log (not
  for a missing log); goal run only with status `running` and a live instance's PID, goal file name only;
  `last_goal` for a card not running; running sessions from `build_sessions` shown as running with a live instance
  and as interrupted without one; titles from hub items, `unknown` when not listed or the hub failed; last event,
  last session, last start, last stop only after the last start. Verify each case with a fixed `now`.
- [ ] 1.4 Machine line (N7): slots used summed from live instance records, limit from `machine.toml`, invalid file
  → defaults and a note, running pipelines and other / unknown instance counts. Verify with two live instances
  holding 1 and 2 slots and a limit of 3.

## 2. Server and page

- [ ] 2.1 `radark/cockpit.py`: `Cockpit.now(now=None)` (reuses `_load()`, the shared `LogCache`, `_list_all` with a
  30 s per-hub cache for Now, hubs listed in parallel) and route `GET /api/now` with the existing request checks and
  headers; no paths, prompts or result texts in the JSON (N8). Verify with the part-1 server harness and fake `ho`:
  the answer shape, 403 on a foreign Host, no write `ho` call, two pipelines on one hub → one `list` call, a second
  request within 30 s → no new `list` call.
- [ ] 2.2 Read-only check (spec "Now is read only"): with live, stale and orphan instance records, `goal.json` and
  logs present, a snapshot of every file (path, size, `st_mtime_ns`) in the machine directory and run directories
  before and after two `/api/now` requests is identical.
- [ ] 2.3 `radark/cockpit_page.html` (N9): third tab renamed **Now** and enabled, placeholder removed; machine line;
  cards with state badge, instances (local start, PID), goal / regular run, running or interrupted sessions table
  (Team, ID, Title, Phase, Since, For), last event, last session / start / stop on cards not running; local times,
  `H h MM min` durations; 10 s refresh while the tab is active, other tabs unchanged; text via `textContent` only.
  Verify with tests on the served page: Now button enabled, no "coming later" placeholder, no external resource,
  the Now render code uses no `innerHTML`; plus the manual check in 3.3.
- [ ] 2.4 End-to-end with the installed `ho` (N10): new `radark/tests/test_cockpit_now_ho.py`, `ho init --teams
  product=Product,app=App,owner=Owner` in `tmp_path`, an invented handover, configurations `alpha` and `beta` on
  that hub with invented `runs.jsonl`, an instance record for `alpha` whose lock a helper subprocess holds, a stale
  record for `beta`; check through `/api/now`: `alpha` running with the session's title, `beta` not running with
  interrupted session and last-run facts, an ID the hub does not know → `unknown` title. Fails with a clear message
  when `ho` is not on `PATH` (no skip).

## 3. Docs and checks

- [ ] 3.1 README "Cockpit" section: what the Now tab shows and where it reads from (instance records in the machine
  directory, each run directory's `runs.jsonl` and `goal.json`, the hub through `ho list`), that it changes nothing
  and refreshes every 10 s; `radark/README.md`: `/api/now`, `cockpit_now.py`, `machine.probe_readonly`. Neutral
  names only. Verify against the spec requirement "Cockpit documentation".
- [ ] 3.2 Full suite: `python -m pytest radark/tests` (through `radark-test-slot` when run by a pipeline); all pass.
  Failing or flaky tests follow hub `AGENTS.md` §10 and are reported in the result, including whether the known
  RB-024 / RB-025 ones still occur.
- [ ] 3.3 Manual check in the sandbox: `python radark/sandbox/make_sandbox.py <tmp dir>`; start `python -m radark
  --config <tmp dir>/radark.toml cockpit --no-browser`; request `/api/now` with no instance running, then while a
  sandbox dispatcher instance runs (e.g. `dry-run` in a loop, or `run` against the sandbox's fake setup) and compare
  the card with `instances/*.json`, `goal.json` and `runs.jsonl`; confirm the machine directory's file list is
  unchanged by the cockpit. Record the result in the `ho done` message. Nothing from the sandbox is committed.
- [ ] 3.4 Public-repository check: `git diff` of the change contains no owner path, product or company name, hub or
  run excerpt; IDs are invented.
- [ ] 3.5 Commit locally (no push, tag, release or reinstall), `ho sync`, then
  `ho done HO-20261115-xspc -m "<commits, test counts, how to see the Now tab (npm run cockpit / radark cockpit →
  Now), decisions that differ from the handover (design Assumptions: N2 read-only lock probe, slots counted from
  instance records; N4 unknown wins over a live instance; N5 goal only with matching PID; N6 hub list reused 30 s on
  Now, stop shown only when recorded), anything left out as too expensive>"` and `ho sync`. This is the last step of
  apply.

## Notes

- Archiving this change and syncing its specs are not tasks of apply: they run in a separate archive phase after
  `radark-product` closes HO-20261115-xspc.
- Propose notes (2026-11-15, unattended): every open point of the handover was decided in `design.md` (marked
  **Assumption**); nothing in the handover looked too expensive at propose time. If the sandbox check in 3.3 cannot
  keep a dispatcher instance alive long enough, a helper process holding an instance lock with an invented record in
  the sandbox machine directory is an acceptable stand-in; say so in the result.
