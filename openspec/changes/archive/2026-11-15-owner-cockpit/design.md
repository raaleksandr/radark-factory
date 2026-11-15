# Design: owner cockpit, part 1

Handover HO-20261115-kgop (RB-021). The product decisions of the handover (2026-11-15) are taken as given; the
decisions below fill in what it leaves open. Assumptions taken without asking (the session runs unattended) are
marked **Assumption**.

## Context

- The dispatcher already talks to a hub only through `radark/hub.py` `Hub`, which runs `ho … --json` with `HO_HUB`
  and `HO_TEAM` in the environment, with awake-time timeouts and exit-code → exception mapping. It never edits hub
  files.
- The machine layer (`radark/machine.py`, change `machine-wide-instances`) owns a per-user machine directory with
  `machine.toml`, OS file locks and atomic JSON records. It stores no hub path and calls no `ho` (its D11).
- `ho` contract 1 gives everything needed: `ho list --to <team> --status all` (items with `id`, `title`, `from`,
  `to`, `expects`, `status`, `my_state` for the acting team, `tags`, `created`, `last_activity`, `archived`),
  `ho show <ID>` (`body`, `events`, `allowed_actions` for the acting team), `ho respond|done|ack|decline <ID>
  --body -` and `ho sync`. No handover to `radark-handover` is needed.
- The configuration has `owner_team` (default `owner`) and no pipeline name.

## Goals / Non-Goals

**Goals:** one command opens a page that lists everything addressed to the owner in all pipelines on this PC and
answers short items through `ho`; safe against other websites in the same browser; clean enough for a webinar;
standard library only; testable without a browser.

**Non-Goals:** history of finished work (RB-022) and running-pipeline state (RB-023) — only empty tabs reserve their
place; no login, no remote access, no HTTPS; no push notifications or file watchers; no editing of hub files; no
attachments; telling apart items that need repository work (a fixed note on every item instead).

## Decisions

### D1. Module layout and command

New `radark/cockpit.py` (server, API handlers, data gathering) and `radark/cockpit_page.html` (the whole page:
HTML, inline CSS and JS), shipped as package data and read with `importlib.resources`. The subcommand is parsed in
`radark/__main__.py` and handled **before** the configuration is loaded (like `status`): the cockpit does not need a
`radark.toml` in the current directory. Options: `--port N`, `--config PATH` (repeatable, `action="append"`; the
global `--config` before the subcommand counts as one too), `--no-browser`, `--forget PATH`.
`--forget` edits the registry, prints one line and exits 0 (1 when the path is not registered) without starting a
server.

Server: `http.server.ThreadingHTTPServer` bound to `("127.0.0.1", port)`; `serve_forever()` until Ctrl+C (exit 130
quietly, like `run`). On start it prints `Cockpit running at http://127.0.0.1:<port>/ (Ctrl+C to stop)` and, unless
`--no-browser`, calls `webbrowser.open(url)`. Request logging goes to a quiet one-line format on stderr only for
errors (no hub content in the console).

### D2. Port and busy-port behaviour

Port order: `--port`, else `[cockpit] port` from `machine.toml`, else 7391. `[cockpit] port` must be an integer
1–65535 (bool refused); a wrong value → exit 2 naming the file and key, like the machine limits. Reading it is a new
`machine.load_cockpit_port(directory)`; `load_limits` stays as it is.

**Assumption** — the server class sets `allow_reuse_address = False` on every platform (on Windows `SO_REUSEADDR`
would let a second server bind the same port, defeating the busy-port check); a restart right after stopping may hit
`TIME_WAIT` on POSIX, which the "port busy" line covers.
On `OSError` at bind: `GET http://127.0.0.1:<port>/api/health` with a 2 s timeout; a JSON answer
`{"app": "radark-cockpit", ...}` → print `Cockpit already running at http://127.0.0.1:<port>/`, open the browser
(unless `--no-browser`) and exit 0; anything else → exit 2 with `Port <port> is busy; use --port N or set
[cockpit] port in <machine.toml path>.` No other port is tried.

`/api/health` answers `{"app": "radark-cockpit", "version": <package version>, "pid": <pid>}`.

### D3. Pipeline registry

File `<machine dir>/pipelines.json`, written by `machine.Registry` under `<machine dir>/pipelines.lock` (the existing
`FileLock`, retried for a short bound like a claim) with the existing atomic `write_record`:

```json
{"schema_version": 1, "pipelines": [{"config": "<resolved path>", "name": "app-pipeline", "last_seen": "<local ISO>"}]}
```

Key: `machine.norm(config)` (case-insensitive on Windows). `record(config, name)` updates name and `last_seen` or
appends; `forget(config)` removes; `entries()` reads. A corrupt file is reported once and treated as empty, and is
replaced on the next write (it is the engine's own file, never a hub file).

Recorded by `run`, `once`, `dry-run` right after the machine directory is prepared (a registry failure is a `!` line,
never a refusal to start), and by the cockpit for each `--config` it is given. `plan`, `status` and the other
commands do not record. This keeps the machine layer free of hub paths (machine D11): the registry stores
configuration paths only; the hub is read from each configuration when the cockpit loads it.

Pipeline name: new optional top-level `name` key in `radark.toml` (non-empty string); else the name of the run
directory's parent folder (the run directory is usually `<pipeline>/.harness`). **Assumption** — a top-level key
next to `hub` / `ho` rather than a new `[pipeline]` table: there is no other pipeline-level setting yet.

### D4. Gathering the data

On each `GET /api/items` (no cache; a refresh every 30 s is cheap enough for a handful of hubs) the server:

1. Builds the pipeline list: registry entries plus the cockpit's `--config` paths (deduplicated by `norm`). Each is
   loaded with `config.load`; a missing file → `{"state": "missing"}`; a load error → `{"state": "error",
   "message": ...}`; otherwise `{"state": "ok", "name", "hub", "owner_team", "ho"}`.
2. Groups the loaded pipelines by (`norm(hub)`, `owner_team`); each group is read once with the first pipeline's `ho`
   command: `ho list --to <owner_team> --status all` with `HO_TEAM=<owner_team>`, then `ho show <ID>` per item for
   body, events and `allowed_actions`. **Assumption** — `show` for every item, pending and done, so the history is
   complete; to bound the cost, done items older than the newest 50 per hub are listed without `show` (title and
   states only, body loaded on demand through `GET /api/item?hub_key=…&id=…`; the item's opaque `hub_key` names the hub, so
   one item shared by two pipelines has one address).
3. Splits items: **Pending** when the owner's `my_state` is `pending`, `acknowledged` or `returned` and the handover
   status is not `closed`; **Done** otherwise. Both sorted by `last_activity`, newest first.
   **Assumption (found in apply)** — `ack` of an `expects ack` handover is its answer: the installed `ho` then
   reports `my_state` `acknowledged` and status `resolved`, so `acknowledged` counts as pending only on a `done` /
   `response` handover (where it means "taken in progress"). Without this an acknowledged note would never leave
   Pending.
4. A hub that fails (`HoError`, `ho` incompatible) yields an error entry shown at the top of the page for its
   pipelines; the others still show.

Before the first read of a hub the server runs `hub.check_ho` (contract check, same as the engine) once per `ho`
command and hub, and refuses that hub with the check's message when it fails.

Item JSON (the page's only data source): `pipelines` (names), `hub_key` (opaque index, not a path), `id`, `title`,
`from`, `expects`, `status`, `my_state`, `tags`, `escalation` (bool), `created`, `last_activity`, `body`, `events`
(`at`, `team`, `type`, `body`), `allowed` (subset of `respond`, `done`, `ack`, `decline`). Hub paths are not sent to
the page; the "pipelines" list shows name, configuration path and state (the owner's own paths on their own PC).

### D5. Answering

`POST /api/action` with JSON `{"hub_key", "id", "action", "text"}`. The server:

1. checks the request (D6), the action is one of `respond`, `done`, `ack`, `decline`, `text` is a string ≤ 20 000
   characters, and `respond` / `decline` have non-empty text;
2. runs `ho show <ID>` as the owner team and refuses (409, `{"error": "not allowed now", "allowed": [...]}`) when the
   action is not in `allowed_actions` — the page's view may be stale;
3. runs `ho <action> <ID> --body -` with the text on stdin (an empty note for `done` / `ack` → no body option), with
   `HO_TEAM=<owner_team>`; a new `Hub.act(action, id, team, body)` method next to `close`;
4. runs `ho sync` on that hub; a sync failure after a successful action is reported as a warning, not an error (the
   owner's hub may have no remote — `ho sync` reports that and exits 0);
5. answers `{"ok": true, "result": <ho JSON>, "warning": ...}` or `{"ok": false, "error": <ho message>, "code": ...}`
   (`ho` exit 3 → 409, others → 502). The page then reloads the items, so the item moves to Done or stays pending as
   the hub says.

A per-hub `threading.Lock` serialises writes of one cockpit to one hub; concurrent writes from a running dispatcher
are handled by `ho` itself (hub lock, contract 1).

**Assumption** — the handover names `ho … --hub <hub> --team owner`; the cockpit uses the existing `Hub` wrapper,
which passes the same values as `HO_HUB` / `HO_TEAM` (identical in `ho`), so there is one way to call `ho` in the
engine. The owner team comes from each configuration's `owner_team` (default `owner`).

### D6. Request checks (security)

For every request: `Host` must be exactly `127.0.0.1:<port>` or `localhost:<port>` (case-insensitive), else 403.
For `POST`: `Origin`, when present, must be `http://127.0.0.1:<port>` or `http://localhost:<port>`, else 403;
`Content-Type` must be `application/json` (this also forces a CORS preflight for cross-site `fetch`, which the server
never answers with CORS headers); the body ≤ 64 KiB. `GET` never changes anything (`/api/items`, `/api/item`,
`/api/health`, `/`); `POST` endpoints: `/api/action`, `/api/forget`. No CORS headers are ever sent. Responses carry
`Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
`Cache-Control: no-store`. `/api/health` answers with the same Host check (a rebinding page cannot probe it either).

### D7. The page

One HTML file with inline CSS and JS, system font stack, light and dark (`prefers-color-scheme`), no external
resources. Header: "radark cockpit", tabs "Owner" (active), "History" and "Pipelines status" (disabled, "coming
later"), a "Refresh" button and the last-refresh time; a collapsible "Pipelines" strip (name, configuration, state;
"Forget" button for missing ones → `POST /api/forget`). Two sections, Pending (count) and Done (count, collapsed
after the first 20). An item card: title, `escalation` badge, other tags, pipeline name chips, `from`, `expects`,
created / last activity (relative and absolute in a tooltip), ID; the body; a collapsible history; for a pending
item the action area with only the allowed actions, and the fixed note "Answer here only if a short answer is
enough; files to place or code to change must be handled outside the cockpit." Result / error line under the
buttons; buttons disabled while a request runs.

Markdown: the JS escapes the text first (`&`, `<`, `>`, `"`, `'`) and only then applies a minimal subset — headings,
`**bold**`, `` `code` ``, fenced code blocks, lists, paragraphs, and links whose target starts with `http://` or
`https://` (rendered with `rel="noopener noreferrer"`); never `innerHTML` of hub text that was not escaped. Data is
fetched every 30 s and on "Refresh"; an open answer box is not re-rendered while the owner types (the refresh skips
cards whose text area has content).

### D8. npm and documentation

`package.json` gets `"cockpit": "python -m radark cockpit"` (**Assumption** — `python -m radark` rather than the
`radark` script: it works when the scripts directory is not on `PATH`, which is common for user installs on
Windows; the README shows both). README "Cockpit" section and `radark/README.md` command list; `machine.toml.example`
gets a commented `[cockpit] port = 7391`; `radark.toml.example` gets the commented `name` key.

### D9. Tests

- `radark/tests/test_cockpit.py`, fake `ho` (extended: `list` honours `--to` / `--status` from `list:<team>` keys or
  computes them from `show:*` entries; `ack`, `done` write the owner's event and state; `show` returns
  `allowed_actions` from the data), a temporary `RADARK_MACHINE_DIR`, the server on port 0 / a free port in a thread,
  requests with `http.client`: list pending/done newest first, escalation flag, pipeline names, two pipelines on one
  hub read once (fake `ho` `.calls` file), every action goes through `ho` with the owner team and `--body -`, then
  `sync`; a not-allowed action → 409 and no write call; foreign `Host` → 403; foreign `Origin` → 403; non-JSON
  content type → 403/415; busy port answering health → exit 0 and no new server; busy port by a plain socket → exit
  2 with the line; `[cockpit] port` and `--port` precedence; registry: record by `dry-run`, name from `name` and from
  the folder, missing configuration listed, `--forget`, corrupt file; the page HTML contains no `http(s)://` resource
  reference.
- `radark/tests/test_cockpit_ho.py`, the **installed `ho`** (the runtime dependency) on a temporary neutral hub made
  with `ho init --teams product=Product,app=App,owner=Owner` in `tmp_path`, with invented handovers made by `ho new`:
  one end-to-end answer per expects (`respond`, `done`, `ack`) and a `decline`, checked with `ho show`.
  **Assumption** — this does not break the rule "never a real hub": the hub is a throw-away directory created and
  removed by the test, like the sandbox; it is the check the handover asks for. If `ho` is not on `PATH` the test
  fails with a clear message (no skip; hub `AGENTS.md` §10).
- No test opens a browser (`--no-browser`, `webbrowser.open` patched where the call itself is checked).

## Risks / Trade-offs

- `show` per item costs one `ho` process each; with tens of items per hub a refresh takes seconds → bounded by the
  "newest 50 done items" rule (D4) and gathering hubs in parallel threads (one per hub).
- Port 7391 may be used by another program → exit 2 with a clear line; no silent switch, as decided.
- The registry holds configuration paths of the owner's PC in the owner's machine directory only; nothing of it lands
  in the repository or in the page beyond the owner's own browser.
- A malicious local process could still call the API — out of scope (same user, same PC; the hub is writable by it
  anyway).

## Migration

None. Existing configurations without `name` get the folder name; the registry fills itself on the next run. No
`ho` change.
