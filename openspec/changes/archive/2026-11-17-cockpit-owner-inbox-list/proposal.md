# Proposal: cockpit Owner tab as a two-level inbox list

Handover: **HO-20261117-t3ub** (RB-026, "cockpit Owner tab as a two-level inbox list"), from `radark-product`.
Builds on the cockpit changes `owner-cockpit`, `cockpit-history` and `cockpit-now` (archived).

## Why

The cockpit's **Owner** tab shows every handover addressed to the owner as a large card with its full body,
history and answer controls. With several waiting items the owner has to scroll through whole bodies to see what
is there at all. The owner wants the tab to read like an email inbox: a compact list first, details on demand.

## What Changes

- **Level 1 — the list.** In both sections (Pending and Done) each owner handover becomes one compact line:
  title, arrival date and time (the handover's `created`, in the browser's local time), the pipeline name(s), and
  its importance at a glance — an escalation line keeps the red mark (`--esc` left border and the `escalation`
  chip). The order stays as today: by last activity, newest first; escalations are not pulled to the top.
- **Level 2 — the details.** Clicking a line, or Enter / Space while it has keyboard focus, expands the item in
  place with exactly what the card shows today: sender, `expects`, both times, ID, tags, body (or "Load the text"
  for a partial item), history of events, the note and the answer controls. Clicking it again collapses it;
  opening another line collapses the open one (one item open at a time).
- **Refresh keeps state.** The open item stays open across the periodic 30 s refresh and the "Refresh" button,
  and a half-typed answer (in the open item or in a collapsed one) is never lost.
- Unchanged: the answer actions and their checks, the Pending / Done split and the "Show all" of Done, the
  History and Now tabs, the server and its API (`/api/items`, `/api/item`, `/api/action`, ...), and security (Host
  and Origin checks, no CDN or external resource, all hub text escaped, `innerHTML` only from `md()`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `owner-cockpit`: the requirement "Owner item details" changes from an always-open card to details shown when
  the item's line is opened; new requirements describe the inbox line, opening and closing a line, and keeping
  the open item and a typed answer across a refresh.

## Impact

- `radark/cockpit_page.html` only (CSS and the Owner-tab rendering in its inline JavaScript); no Python server
  code, no API change, no new dependency.
- Tests: new page tests in `radark/tests/test_cockpit.py` (the existing static page-source style); existing
  cockpit tests must keep passing.
- Docs: the README "Cockpit" section describes the list and the details.
