# Tasks: neutral examples (HO-20261114-flmx)

The list of private data to remove is in the handover body (`ho show HO-20261114-flmx --json`); never copy it into a
committed file, a commit message or the `ho done` summary.

## 1. Inventory and mapping

- [x] 1.1 Run the handover's grep (its 15 IDs, private item IDs, the two product titles) and an owner-path / user-name
      grep over all tracked files; record the hit list in session scratch space (not committed). Verify: hit list
      covers at least the 16 files named in design.md.
- [x] 1.2 Build one old → new mapping per design.md decisions 1 and 3 (same date part, invented suffix; neutral item
      IDs and titles); check every new ID with `ho show <ID>` against the radark hub (must be not found). Verify: no
      new ID is in the handover's list or the radark hub.

## 2. Replace in docs and specs

- [x] 2.1 `radark/README.md`: rewrite the `dry-run` / goal-plan example and the console example with invented IDs and
      neutral item texts (e.g. "Add a health check endpoint"); replace all other real IDs. Verify: grep from 1.1 has
      no hit in the README and the examples read consistently.
- [x] 2.2 `openspec/specs/harness-dispatcher/spec.md`: replace example IDs, item IDs and titles in the affected
      scenarios in place (data only, no requirement text change). Verify: grep has no hit; `openspec validate --specs`
      passes.
- [x] 2.3 Archived change specs (`2026-11-13-check-long-waits`, `2026-11-14-wrap-up-at-time-limit`,
      `2026-11-14-fewer-owner-waits`) and `docs/research/workflow-today.md`: same mapping. Verify: grep has no hit
      in `openspec/` or `docs/`.

## 3. Replace in tests

- [x] 3.1 Apply the mapping in `test_unconfigured.py`, `test_console.py`, `test_forecast.py`, `test_select.py`,
      `test_waiting.py`, `test_prompts.py`, `test_dispatcher.py`, `test_escalation.py`, `test_hub.py` (keep the
      invented pricing-page and sandbox examples). Verify: each edited test file passes alone
      (`python -m pytest radark/tests/<file>`).
- [x] 3.2 Update any golden file that contains a replaced ID (design.md decision 4). Verify:
      `python -m pytest radark/tests/test_workflow_golden.py` passes.

## 4. Sweep and spec

- [x] 4.1 Repository-wide sweep per design.md decision 6 (other real IDs, owner paths, user names, product names, in
      README, docs, `openspec/` incl. archive, tests, sandbox, code); fix what is found with the same rules. Verify:
      the sweep's greps have no hits other than radark-hub provenance IDs and the dependency URL (decision 5).
- [x] 4.2 Confirm the change's own artifacts (proposal, design, specs, tasks) quote none of the private data. Verify:
      the grep from 1.1 over `openspec/changes/neutral-examples/` has no hit; `openspec validate neutral-examples`
      passes.

## 5. Verify and report

- [x] 5.1 Run the full suite `python -m pytest radark/tests` (about 5 minutes); all must pass. Failing or flaky tests
      follow hub `AGENTS.md` §10 (fix quick real failures, report others and flakes by name; no retries or skips).
- [x] 5.2 Final grep for the handover's list and owner paths over all tracked files: no hits outside `.git`. Commit
      locally (no push, tag, release or reinstall); commit messages name no private data.
- [x] 5.3 `ho done HO-20261114-flmx -m "<summary: what was replaced, files, test result, assumptions>"` (summary
      without private data), then `ho sync`.

## Workflow follow-up

- Archive (with spec sync) is a separate phase that runs only after `radark-product` closes HO-20261114-flmx.
