# Proposal: owner cockpit, part 1 — escalations and requests answered in a local web page

Handover: **HO-20261115-kgop** (RB-021, "Cockpit part 1"), from `radark-product`.

## Why

Everything a radark pipeline needs from the human owner arrives as a handover addressed to `owner` (escalations
created by the dispatcher, direct requests from teams). Today the owner reads them with `HO_TEAM=owner ho inbox` and
answers with `ho respond` / `ho done` / `ho decline`, hub by hub, in a console. With several pipelines on one PC
(change `machine-wide-instances`) this is slow, easy to miss and hard to show. The owner wants one command that opens
a clean local page listing everything addressed to them in all pipelines on this PC, where a short answer can be
given right away.

## What Changes

- **New command `radark cockpit`** (`python -m radark cockpit`): a local HTTP server (standard library
  `http.server`, threaded) on `127.0.0.1`, default port **7391**, that opens the default browser on its main page
  (`--no-browser` to skip). Options: `--port N`, repeatable `--config PATH`, `--forget PATH`.
- **Main page**: one self-contained HTML/CSS/JS page (no CDN, no external fonts, no build step), with tabs; part 1
  fills the "Owner" tab, the other tabs are placeholders for RB-022 (history of finished work) and RB-023 (running
  pipelines). It lists every handover addressed to the owner team in the hubs of all known pipelines, split into
  **Pending** and **Done**, newest first, with pipeline name(s), `from`, created / last activity, title, tags (an
  `escalation` badge), `expects`, the body (minimal Markdown rendered from escaped text, never raw HTML) and the
  events. Refresh every 30 s and on a "Refresh" button.
- **Answers through `ho` only**: a pending item offers only the actions `ho show --json` lists in `allowed_actions`
  for the owner — `respond` (text), `done` (optional note), `ack`, `decline` (reason) — run as `ho <action> <ID>
  --body - --json` with the owner team, followed by `ho sync` on that hub. The server never writes hub files. The
  `ho` result or error is shown in the page; each item carries the note that only short answers belong here.
- **Busy port**: if the port answers the cockpit's `/api/health`, open the browser on it and exit 0 ("Cockpit already
  running at …"); otherwise exit 2 with one line naming `--port N` and `[cockpit] port`. No silent port switch.
- **Port setting**: `[cockpit] port` in the machine-wide `machine.toml`; `--port` wins.
- **Pipeline registry**: a machine-wide file `pipelines.json` in the machine directory. `run`, `once`, `dry-run` and
  the cockpit's own `--config` record the configuration path, the pipeline name and the last-seen time. The name is
  an optional new top-level `name` key in `radark.toml`, else the name of the run directory's parent folder. The
  cockpit shows every registered pipeline plus each `--config`; a registered configuration that is gone is listed as
  "missing" and can be forgotten with `radark cockpit --forget PATH` or a page button (both edit only the registry).
  Pipelines sharing one hub: the hub is read once and every pipeline name is shown on its items.
- **Security**: listen on `127.0.0.1` only, no login, nothing sent anywhere; writes only by `POST` with a JSON body;
  requests whose `Host` is not `127.0.0.1:<port>` / `localhost:<port>`, or whose `Origin` (when present) is not the
  cockpit's own origin, are refused (403) — against DNS rebinding and cross-site requests. Everything from the hub is
  escaped in the page.
- **npm**: `package.json` gets `"cockpit": "python -m radark cockpit"`; the README documents the one-line script a
  pipeline repository adds to its own `package.json` to get `npm run cockpit`.
- **README**: a "Cockpit" section (what it shows, commands, port, the `package.json` line, the security note).

## Capabilities

### New Capabilities

- `owner-cockpit`: the `cockpit` command, its page, its API, answers through `ho`, port handling, security, the
  pipeline list it shows.

### Modified Capabilities

- `harness-dispatcher`: the machine-wide pipeline registry recorded by `run` / `once` / `dry-run`, the optional
  `name` key of the configuration, and `[cockpit] port` in `machine.toml`.

## Impact

- Code: new `radark/cockpit.py` (server, API, `ho` calls, registry reading) and `radark/cockpit_page.html` (the page,
  package data); `radark/machine.py` (registry file under an OS lock, `[cockpit] port`); `radark/config.py` (`name`);
  `radark/__main__.py` (subcommand, registry recording); `pyproject.toml` package data; `package.json`.
- Docs: README "Cockpit" section, `radark/README.md`, `machine.toml.example`, `radark.toml.example`.
- Tests: new `radark/tests/test_cockpit.py` (fake `ho`, extended for `list --to`, `ack`, `done`) and
  `radark/tests/test_cockpit_ho.py` (the installed `ho` on a temporary neutral hub made with `ho init`).
- No change to `ho`: `list --to --status all`, `show` (with `allowed_actions`), `respond|done|ack|decline --body -`
  and `sync` of contract 1 suffice.
