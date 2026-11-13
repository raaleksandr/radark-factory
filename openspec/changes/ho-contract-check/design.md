# Design: check `ho` compatibility at start

Handover HO-20261113-k2wq (RB-003). The `ho` side is requested from `radark-handover` in HO-20261113-cbcj.

## Context

`radark/hub.py` wraps every `ho` call (`Hub._run` adds `--json`, maps exit codes to `HoError` subclasses).
`radark/__main__.py` `main()` builds the `Dispatcher`, prints `config_mod.summary(cfg, claude_version(cfg))`, then
calls `check_owner(cfg, d.hub.teams())` — the first hub call — before `dry_run` or the loop; `plan` calls
`check_owner` too. Every `ho --json` output today carries `"schema_version": 1`. `ho` has no `--version` yet.

## Goals / Non-Goals

- Goal: a missing, old or incompatible `ho` stops `run` / `once` / `dry-run` / `plan` before any hub read and any
  session, with one message naming found and needed versions and what to do.
- Goal: one start line with the `ho` version and contract.
- Non-goal: checking `schema_version` on every later `ho` answer (possible follow-up item); checking `claude`'s
  version; the `ho` side itself (radark-handover's own change).

## Decisions

### D1. Probe: `ho --version --json`
Run `cfg.ho + ["--version", "--json"]` with `subprocess.run` (capture output, bytes decoded as UTF-8, `timeout=60` s
like `claude_version`), env = `os.environ` with `HO_HUB` set and `HO_TEAM` removed (as `Hub._run` does). Parse
stdout as a JSON object; read `version` (string) and `contract` (int).
- **Assumption (recorded):** the shape proposed to radark-handover is
  `{"schema_version": 1, "version": "<package version>", "contract": <int>}`. radark-handover has the last word;
  apply follows the shape it reports in its `ho done` of HO-20261113-cbcj (only D1's parsing and the fake change).
  If its answer has no `contract` but has `schema_version`, apply uses `schema_version` as the contract.
- Not through `Hub._run`: that path raises on any non-zero exit and re-runs reads after a sleep; the probe needs its
  own classification (D3) and is a one-shot call at start.

### D2. Supported contracts: one constant
`SUPPORTED_HO_CONTRACTS = (1,)` in `radark/hub.py`. A tuple, so a future engine can support `(1, 2)` during a
migration. Messages list the needed contract(s) as `1` or `1 or 2`.

### D3. Outcomes and messages
`check_ho(cmd, hub) -> HoVersion | str` (a small dataclass `HoVersion(version, contract)` or the stop message).
`<cmd>` is the configured command joined with spaces; `<needed>` from D2.
- process cannot be started (`OSError`) → **missing**:
  `ho not found: cannot start '<cmd>' (<reason>). This radark-factory needs an ho with JSON contract <needed>: install radark-handover with that contract, or fix 'ho' in harness.toml.`
- timeout → **no answer**:
  `ho '<cmd>' did not answer '--version --json' within 60 s. This radark-factory needs an ho with JSON contract <needed>.`
- non-zero exit, or stdout not a JSON object with a string `version` and an integer contract → **too old**:
  `ho '<cmd>' has no --version (exit <n>): it is older than this radark-factory supports. Found: no version; needed: JSON contract <needed>. Install a radark-handover release that has 'ho --version' with contract <needed>.`
- contract not supported → **unsupported**:
  `ho '<cmd>' is version <version> with JSON contract <n>; this radark-factory needs contract <needed>. Install a radark-handover release with contract <needed>, or a radark-factory release that supports contract <n>.`
Printed to stderr with the prefix `ho incompatible: ` (assumption: a distinct prefix so the owner sees it is the
`ho` check, not the config file). Apply may tune the wording; each message must keep the command, found, needed and
remedy.

### D4. Where in `main()`
For `plan` and for `run` / `once` / `dry-run`: right after the configuration and `Dispatcher` are built and before
the first hub call (`check_owner`) and before the summary is printed. On failure: print the message, `return 2`
(same code as a broken configuration: an environment problem found before start). No lock, no `dispatcher_start`,
no keep-awake, no goal start. On success `run` / `once` / `dry-run` print the summary with the line
`ho: <version> (contract <n>)` right after `Claude Code: ...` (`summary()` gets an optional `ho` argument so other
callers stay valid). `plan` prints no summary today and stays so (assumption). `escalations`, `clear`, `keep`,
`note` do not touch the hub and skip the check.

### D5. Fake `ho`
`radark/tests/fakes/fake_ho.py`: when the first argument is `--version`, answer from data key `"_version"`:
absent → `{"schema_version": 1, "version": "0.2.0", "contract": 1}` (so every existing test keeps working); a dict
with `"exit"` → exit with that code and print nothing on stdout (an old `ho`, like argparse's usage error); any
other dict → print it as the JSON answer. The call is logged in `.calls` like every call. The "missing" case uses a
non-existent command in the test config.

### D6. Apply notes (decided in apply)
- **Shape confirmed:** radark-handover's `ho done` of HO-20261113-cbcj (commit 50901f1, change
  `add-version-command`): `ho --version` → `ho 0.2.0 (contract 1)`; `ho --version --json` →
  `{"schema_version": 1, "version": "0.2.0", "contract": 1}`; `contract` always equals `schema_version`; an old `ho`
  exits 1 with no JSON. D1 holds unchanged.
- **Missing command found earlier:** `config.load` already refuses an `ho` / `claude` command that is not on `PATH`
  or not a file (`Configuration error: ...`, exit 2) before `main()` reaches the check. Instead of moving that check,
  its message for `ho` now carries the same hint as D3's "missing" case (needed contract, install radark-handover or
  fix `ho` in harness.toml). `check_ho`'s own "missing" message stays for a command that exists but cannot be
  started.
- A JSON answer with exit 0 but no usable `version` / contract is reported as "too old" with
  `(no version in its answer)` instead of an exit code.
- The fake also takes a string `"_version"`, printed as is (a non-JSON answer).

## Risks / Trade-offs

- Until radark-handover's release with `--version` is installed, a real run stops as "too old". Intended: the owner
  installs both releases together; the README says so.
- One extra short process at start.
- Tests that inspect `.calls` of the fake may now see a `--version` call first; apply checks and adjusts them
  (ignore that call where the test is about other calls).

## Open questions

- The final JSON shape is decided by radark-handover in HO-20261113-cbcj (D1 assumption until then). The dispatcher
  holds HO-20261113-k2wq while HO-20261113-cbcj is unfinished, so apply runs after the shape is known.
