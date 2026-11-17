# Design: cockpit Owner tab as a two-level inbox list

See proposal.md for the motivation (HO-20261117-t3ub) and `specs/owner-cockpit/spec.md` for the required
behaviour.

## Context

The Owner tab is rendered in `radark/cockpit_page.html` from `GET /api/items` (`{pending, done, hubs, pipelines,
note}`). `card(it)` builds a `.card` (`.escalation` adds the `--esc` left border) with an `h3` title, a `.meta`
row (pipelines, tags with the `escalation` chip, sender, `expects`, created / last activity as relative times,
ID, state), `renderBody()` (body via `md()`, `details.history` of events, or "Load the text" for a partial item)
and `answerArea()`. `renderList()` rebuilds a section on every `render()`, but keeps an existing card node whose
textarea has text or focus (`busyCard`). The History tab already has expand-in-place rows with a module-level
`histOpen` map kept across refreshes. Page tests are static checks of the page source plus a fetch of the served
page (`test_page_served_self_contained`, `test_page_escapes_before_markdown`); the suite has no JavaScript engine
(standard library only).

## Goals / Non-Goals

**Goals:** compact line per item; details on demand with today's content; one open item; open item and typed
answers survive refresh; keyboard access.

**Non-Goals:** no server or API change; no new sorting, filters, unread state or search; no change to the History
or Now tabs; no change to how answers are sent.

## Decisions

**D1 — Line plus hidden details inside one item node.** Each item becomes
`div.item[data-key]` (`.escalation` when tagged) containing `div.line` and `div.details` (`hidden` unless open).
The line holds: escalation chip (only for escalations), title (`it.title || it.id`), pipeline chips, and the arrival
time. `details` holds the current card content minus the title: the `.meta` row, `renderBody()` and, for pending
items, `answerArea()`. The current `card()` is split into `itemLine(it)` and `itemDetails(it)`; `renderBody` and
`answerArea` are reused unchanged, so the details are "exactly as the card shows them today".
Alternative considered: `<details>/<summary>` — gives keyboard toggling for free, but one-open-at-a-time and
restoring the open state after a rebuild still need script, and the summary's marker styling differs per browser;
an explicit button-like line matches the History rows already in the page.

**D2 — Arrival time.** The line shows `created` as an absolute local date and time (`toLocaleString` with
date, hour and minute; `title` holds the full value), using the page's existing `local()`-style formatting rather
than the relative `when()`; an item without `created` shows `-`. The relative times stay in the details' `.meta`
row as today. Assumption (recorded for product): "date and time it arrived" = the handover's `created`, not its
last activity; the list order stays last activity, newest first, as the spec's "Owner items list" says.

**D3 — Importance at a glance.** The `.item.escalation` keeps `border-left: 4px solid var(--esc)` and the line
shows the `chip esc` "escalation" badge first. Other tags are shown only in the details, to keep the line short.

**D4 — Open state.** A module-level `ownerOpen` holds the `cardKey` (`hub_key|id`) of the one open item, or
`null`. Toggling a line sets / clears it, hides the previously open item's details in the DOM directly (no
re-render, so nothing typed anywhere is lost), and updates `aria-expanded`. The line is `role="button"`,
`tabindex="0"`, `aria-expanded`, with a `keydown` handler for Enter and Space (`preventDefault` on Space so the
page does not scroll). Clicks inside the details never toggle (the handler is on the line only).

**D5 — Refresh.** `renderList()` keeps its keyed rebuild: for each item, an existing node that is busy (textarea
with text or focus — the current `busyCard` rule) is reused as is, otherwise a new node is built, and the new
node's details are visible iff its key equals `ownerOpen`. A reused busy node gets its `hidden` / `aria-expanded`
set from `ownerOpen` too, so a collapsed item with typed text stays collapsed and keeps its text. If `ownerOpen`
names an item no longer in `pending` or `done` (shown part), it is reset to `null`. Moving an answered item from
Pending to Done rebuilds it (its textarea was cleared on success), and it stays open if it was open.

**D6 — Tests in the existing style.** Without a JavaScript engine the tests check the page source and the served
page: an item line carries title, `created` formatted locally and the pipeline chips; the escalation class / chip
is applied only from `it.escalation`; details are created `hidden` unless the key is `ownerOpen`; the line has
`role="button"`, `tabindex="0"`, `aria-expanded` and handles `Enter` and `" "`; the details contain
`renderBody` and `answerArea`; `renderList` reuses busy nodes and applies `ownerOpen`; the existing
`innerHTML`-only-from-`md()` and self-contained checks still pass. The behaviour itself (open, collapse, refresh
with typed text) is verified manually on a sandbox hub with one escalation and two normal owner handovers, as
product will do; the result is recorded in tasks.md. Assumption: this is what the handover means by "existing
cockpit test style"; adding a headless browser or Node would break the standard-library-only rule.

## Risks / Trade-offs

- [Static tests can pass while the toggling is broken in a browser] → the manual sandbox check of task 3.2 is a
  required task, with each scenario of the spec walked through and noted.
- [Owner opens an item, the item is answered elsewhere and moves to Done] → it stays open in Done (same key), which
  shows its new state; acceptable and consistent with "keep the open item open".
- [Partial items (body not loaded)] → "Load the text" stays inside the details; loading it mutates the same `it`
  and re-renders only the body box, as today.

## Migration Plan

Page-only change, shipped with the next release by the owner; no data or configuration migration. Rollback is
reverting `cockpit_page.html`.
