# Tasks

Change for HO-20261115-kgop (RB-021, cockpit part 1). Tests use fake `ho` / `claude`, a temporary
`RADARK_MACHINE_DIR` and, in one module, the installed `ho` on a throw-away hub made with `ho init` (design D9);
never the owner's hub, never a browser. Neutral names only (`product`, `app`, `owner`, pipelines `alpha` / `beta`),
invented IDs `HO-…`. Commits stay local: no push, tag, release or reinstall.

## 1. Registry, name and port setting

- [ ] 1.1 `radark/config.py`: optional top-level `name` (non-empty string, else `ConfigError` naming `name`);
  `Config.name` and `Config.pipeline_name()` (the key, else the run directory's parent folder name, D3).
  `radark.toml.example`: commented `name`. Verify with `radark/tests/test_config.py` cases: set, absent (folder
  name), `""` and `5` refused.
- [ ] 1.2 `radark/machine.py`: `Registry` over `pipelines.json` / `pipelines.lock` (`record`, `forget`, `entries`;
  `norm` keys; atomic write; corrupt file → reported, treated as empty, rewritten) and `load_cockpit_port()`
  (`[cockpit] port`, 1–65535, bool refused, default 7391). `machine.toml.example`: commented `[cockpit] port`.
  Verify in `radark/tests/test_machine.py`: record / update / forget, case-insensitive key on Windows, corrupt file,
  port default / valid / `0` / `70000` / `true` refused naming `cockpit.port`, `load_limits` unaffected by a bad port.
- [ ] 1.3 `radark/__main__.py`: `run`, `once`, `dry-run` record the pipeline after `prepare_dir`; a registry error is
  one `!` line, the run continues; `plan` / `status` do not record. Verify with dispatcher tests (fake `ho`):
  `dry-run` records name and path; corrupt registry → line and the run goes on; `plan` leaves the registry alone.

## 2. Server and API

- [ ] 2.1 New `radark/cockpit.py`: `ThreadingHTTPServer` on `127.0.0.1` with `allow_reuse_address = False`; routes
  `/`, `/api/health`, `/api/items`, `/api/item`, `POST /api/action`, `POST /api/forget`; request checks and response
  headers of D6. Verify with `radark/tests/test_cockpit.py` (server on a free port in a thread, `http.client`):
  health JSON; foreign `Host` → 403 on GET and POST; foreign `Origin` → 403; missing / wrong content type → refused;
  body over 64 KiB → refused; no CORS header in any answer; GET never calls a write `ho` command (`.calls` file).
- [ ] 2.2 Data gathering (D4): pipelines from registry plus `--config` (dedup by `norm`, missing / error states),
  grouping by hub and owner team, `check_ho` once per `ho` and hub, `ho list --to … --status all` and `ho show` as the
  owner team, pending / done split, newest first, the "newest 50 done" bound with `/api/item` on demand, hub keys not
  paths in the JSON, one failing hub does not hide the others; hubs read in parallel threads. Extend
  `radark/tests/fakes/fake_ho.py` (`list --to` / `--status`, `allowed_actions`, `ack`, `done`). Verify: pending /
  done split and order, escalation flag, pipeline names, two pipelines on one hub → one `list` call and both names,
  missing configuration listed, failing `ho` for one pipeline.
- [ ] 2.3 Answers (D5): `Hub.act()` in `radark/hub.py`; validation, fresh `show` check, `ho <action> <ID> --body -`
  as the owner team, then `ho sync`, per-hub write lock, status codes 200 / 400 / 409 / 502, sync failure as a
  warning. Verify: each of `respond`, `done` (with and without note), `ack`, `decline` calls `ho` with the owner team
  and the stdin text, then `sync`; not-allowed action → 409 and no write call; empty `respond` / `decline` text →
  400; `ho` exit 3 → 409 with `ho`'s message.
- [ ] 2.4 Command in `radark/__main__.py` (D1, D2): `cockpit` handled before the configuration load; `--port`,
  repeatable `--config` (plus the global one), `--no-browser`, `--forget`; start line; `webbrowser.open`; busy port →
  health probe → exit 0 with "Cockpit already running at …" or exit 2 with the busy line; Ctrl+C → 130. Verify:
  `--forget` registered (0) / unknown (1); port precedence `--port` > `[cockpit] port` > 7391; invalid port → 2; busy
  by a running cockpit → 0 and browser call patched once (and not with `--no-browser`); busy by a plain socket → 2
  with the line; `--config` recorded in the registry.

## 3. Page

- [ ] 3.1 `radark/cockpit_page.html` (D7): inline CSS/JS, light / dark, tabs (Owner active; History and Pipelines
  status disabled placeholders), pipelines strip with Forget, Pending / Done sections, item cards, allowed-action
  forms only, the fixed note, result / error line, 30 s refresh plus "Refresh", no re-render of a card being typed
  in; escape-then-minimal-Markdown renderer with `http(s)` links only. Add to `pyproject.toml` package data. Verify
  with tests: the served page has no `http://` / `https://` resource reference (`src=`, `href=` to stylesheets,
  `@import`, `url(`) and the CSP header; the renderer's escaping checked by a small JS-free check of the page source
  (the escape function is applied before any Markdown replacement) plus the manual check in 4.3.
- [ ] 3.2 End-to-end with the installed `ho` (D9): new `radark/tests/test_cockpit_ho.py` — `ho init --teams
  product=Product,app=App,owner=Owner` in `tmp_path`, invented handovers by `ho new` (expects response with tag
  `escalation`, done, ack, and one to decline), a configuration file pointing at that hub, the cockpit server in a
  thread; answer each through `POST /api/action`, then check the state with `ho show --json` and that the items moved
  to Done. Fails with a clear message when `ho` is not on `PATH` (no skip).

## 4. Docs, npm and checks

- [ ] 4.1 `package.json`: `"cockpit": "python -m radark cockpit"`. README "Cockpit" section (what it shows,
  `npm run cockpit` / `radark cockpit` / `python -m radark cockpit`, `--port`, `[cockpit] port`, `--config`,
  `--forget`, `--no-browser`, the one-line `package.json` script for a pipeline repository, the security note);
  `radark/README.md` command list and registry file; neutral names only.
- [ ] 4.2 Full suite: `python -m pytest radark/tests` (through `radark-test-slot` when run by a pipeline); all pass.
  Failing or flaky tests follow hub `AGENTS.md` §10 and are reported in the result.
- [ ] 4.3 Manual check in the sandbox: `python radark/sandbox/make_sandbox.py <tmp dir>`, then
  `python -m radark --config <tmp dir>/radark.toml cockpit --no-browser`; create an invented owner request with
  `ho new` in the sandbox hub, answer it through the API (or the page), check with `ho show`; run a second
  `cockpit` on the same port (exit 0 line) and one with a busy foreign port (exit 2 line). Record the result in the
  `ho done` message. Nothing from the sandbox is committed.
- [ ] 4.4 Public-repository check: `git diff` of the change contains no owner path, product or company name, hub or
  run excerpt; IDs are invented.
- [ ] 4.5 Commit locally (no push, tag, release or reinstall), `ho sync`, then
  `ho done HO-20261115-kgop -m "<commits, test counts, exact start command, decisions that differ from the
  handover (design Assumptions: D3 name key, D4 show bound, D5 env instead of --hub/--team, D8 python -m, D9 real ho
  on a temporary hub)>"` and `ho sync`. This is the last step of apply.
