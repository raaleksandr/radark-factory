# Tasks

Change for HO-20261117-t3ub (RB-026, cockpit Owner tab as a two-level inbox list). Page-only change in
`radark/cockpit_page.html`; tests use the existing page-source checks and the fake `ho` server harness of
`radark/tests/test_cockpit.py`, never the owner's hub or a real browser in the suite. Neutral names only
(`product`, `app`, `owner`, pipelines `alpha` / `beta`), invented IDs `HO-…`. Commits stay local: no push, tag,
release or reinstall.

## 1. Inbox line and details

- [x] 1.1 `radark/cockpit_page.html`: split `card(it)` into an item node `div.item[data-key]` (`.escalation` when
  `it.escalation`) with `itemLine(it)` and `itemDetails(it)` (design D1–D3): the line has the `escalation` chip
  (escalations only), title (`it.title || it.id`), pipeline chips and `created` as a local date and time (`-` when
  missing); the details have today's `.meta` row, `renderBody()` and, for pending items, `answerArea()`, unchanged.
  CSS: compact line, hover, focus outline, `--esc` left border kept on `.item.escalation`. Verify with new tests in
  `radark/tests/test_cockpit.py`: the line code uses `it.title`, `it.created` with a local date-time format and
  `it.pipelines`; the escalation class / chip is applied only from `it.escalation`; the details contain
  `renderBody(` and `answerArea(`; `test_page_escapes_before_markdown` and `test_page_served_self_contained` still
  pass (no new `innerHTML`, no external resource).
- [x] 1.2 Open / close (design D4): module-level `ownerOpen` (one key or `null`); the line is `role="button"`,
  `tabindex="0"`, `aria-expanded`; click and `keydown` Enter / Space (Space `preventDefault`) toggle; opening a line
  hides the previously open item's details in the DOM without a re-render; clicks inside the details do not toggle.
  Verify with tests on the page source: the attributes are set on the line, the key handler handles `"Enter"` and
  `" "`, details are created `hidden` unless their key equals `ownerOpen`, and opening one item closes the other.

## 2. Refresh keeps state

- [x] 2.1 `renderList()` (design D5): reuse a busy node (current `busyCard` rule) as is, build others anew; set
  every node's details `hidden` / `aria-expanded` from `ownerOpen`; reset `ownerOpen` to `null` when its item is no
  longer shown; the Done "Show all" and the Pending / Done counts unchanged. Verify with tests on the page source:
  `renderList` keeps busy nodes, applies `ownerOpen` to reused and new nodes and clears a vanished key; the existing
  `/api/items` tests (`test_pending_and_done_split_newest_first_with_names` and the others) still pass unchanged.

## 3. Docs and checks

- [x] 3.1 README "Cockpit" section: the Owner tab is a compact list (title, arrival time, pipeline, escalation
  mark), a click or Enter / Space opens the details with the text, history and answer controls, one at a time, and
  the open item and a typed answer survive the refresh. Neutral names only. Verify against the spec requirements
  "Owner inbox line" and "Opening and closing an owner line".
- [x] 3.2 Manual check on a sandbox hub: `python radark/sandbox/make_sandbox.py <tmp dir>`, then with the sandbox's
  `ho` create one escalation (tag `escalation`, expects `response`) and two normal handovers to `owner`; start
  `python -m radark --config <tmp dir>/radark.toml cockpit --no-browser`. When the session can drive a browser,
  walk through every scenario of `specs/owner-cockpit/spec.md` (lines, mark, open / close by click and keyboard, one
  open at a time, type part of an answer and wait for a refresh, answer one item); otherwise check `/api/items` and
  the served page and say in the `ho done` message that the in-browser walk-through is left to product. Nothing
  from the sandbox is committed.
- [ ] 3.3 Full suite: `python -m pytest radark/tests` (through `radark-test-slot` when run by a pipeline); all
  pass. Failing or flaky tests follow hub `AGENTS.md` §10 and are reported in the result.
- [x] 3.4 Public-repository check: `git diff` of the change contains no owner path, product or company name, hub or
  run excerpt; IDs are invented.
- [ ] 3.5 Commit locally (no push, tag, release or reinstall), `ho sync`, then `ho done HO-20261117-t3ub -m
  "<commits, test counts, how to see it (npm run cockpit / radark cockpit → Owner), result of the manual check
  3.2, decisions that differ from or add to the handover (design D2 arrival time = created; D6 static page tests,
  no JS engine)>"` and `ho sync`. This is the last step of apply.

## Notes

- Archiving this change and syncing its specs are not tasks of apply: they run in a separate archive phase after
  `radark-product` closes HO-20261117-t3ub.
- Propose notes (2026-11-17, unattended): open points of the handover were decided in `design.md` without asking
  — arrival time is the handover's `created` (D2); other tags appear only in the details (D3); a collapsed item
  with a typed answer keeps its text across refresh (D5); behaviour tests are static page-source checks plus a
  manual sandbox walk-through, because the suite is standard library only (D6).

- Apply notes (2026-11-17, unattended):
  - 2.1: the vanished-key reset sits in `render()` (before both `renderList` calls), because only there both the
    Pending and the shown Done items are known; `renderList` applies `ownerOpen` to reused and new nodes.
  - The line also shows a ▸ / ▾ arrow, as the History rows do; the former `.card.escalation` CSS rule is now
    `.item.escalation` (the Now tab's `.card` is unchanged).
  - 3.2 result: on a sandbox hub with one escalation (`expects response`) and two normal owner handovers,
    `/api/items` lists the three, and the live page rendered in headless Chrome shows three closed lines (title,
    pipeline, local arrival time), only the escalation with the mark and badge. The interactive scenarios were
    walked through in headless Chrome on a copy of the page with a mocked `fetch` (outside the repository): open by
    click, Enter, Space closes; one open at a time; clicks inside the details do not toggle; the open item shows
    body, history, text field and Respond / Decline; after a refresh the open item stays open and typed text is
    kept in the open and in a collapsed item (same node); an open item that vanished leaves all lines closed, no
    error. A walk-through by a person in a real browser is left to product.
