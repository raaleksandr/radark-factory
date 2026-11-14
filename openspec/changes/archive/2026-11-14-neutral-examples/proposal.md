# Proposal: neutral examples, no private run data in the public repository

Handover: **HO-20261114-flmx** (RB-016, "neutral examples, no private run data in the public repo"), from
`radark-product`. Owner's decision of 2026-11-14: the next radark-factory release ships without private data in its
README and docs; this is the only task of that goal run and the owner releases right after it.

## Why

radark-factory is a public repository, but its README, its main spec, three archived change specs, a research note
and about a dozen tests still carry data copied from real runs of the owner's private product hub: real handover IDs
from that hub, real backlog item IDs and item titles of that product. The project rule (CLAUDE.md, "This repository
is public") forbids that; the release must not publish it.

## What Changes

- **README examples** (`radark/README.md`): the `dry-run` / goal-plan example and the console example use invented
  handover IDs and neutral item texts (e.g. "Add a health check endpoint") instead of real IDs and titles from the
  private hub. Every other real ID in the README is replaced too.
- **Real IDs from the private hub** (15 IDs, listed in the handover body, not repeated here) are replaced with
  invented IDs everywhere they appear: `radark/README.md`, `openspec/specs/harness-dispatcher/spec.md`, the archived
  change specs that quote them, `docs/research/workflow-today.md`, and the tests. Each scenario and the test that
  checks it use the same invented ID.
- **Private item IDs and titles** of the product (named in the handover) used as example titles in the main spec and
  in tests are replaced with neutral item names. Invented generic examples that already exist (the sandbox backlog
  items, the pricing-page examples in two tests) stay.
- **Repository-wide sweep** for other private data: owner paths (a drive letter with a user folder, a home folder),
  user names, product names and further real IDs, in README, docs, `openspec/` (including the archive), tests,
  golden files and the sandbox. Whatever is found is fixed in this change.
- **New requirement** "Public repository holds only invented example data", so the rule is part of the spec and is
  checked by a repeatable grep before a release.
- No dispatcher behavior changes; no code outside tests and docs changes, except example strings if a module
  docstring or help text carries one.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `harness-dispatcher`: adds the requirement "Public repository holds only invented example data". The example IDs
  and titles inside existing scenarios are replaced in place (example data only; the requirement texts and the
  behavior they describe do not change, see design.md).

## Impact

- Docs: `radark/README.md`, `docs/research/workflow-today.md`.
- Specs: `openspec/specs/harness-dispatcher/spec.md`; archived change specs under
  `openspec/changes/archive/2026-11-13-check-long-waits/`, `2026-11-14-wrap-up-at-time-limit/`,
  `2026-11-14-fewer-owner-waits/` (example data only).
- Tests: `test_unconfigured.py`, `test_console.py`, `test_forecast.py`, `test_select.py`, `test_waiting.py`,
  `test_prompts.py`, `test_dispatcher.py`, `test_escalation.py`, `test_hub.py`, and any golden file whose content
  follows from a changed ID.
- Git history keeps the old texts; rewriting history is out of scope (the product check excludes `.git`).
- No push, tag, release or reinstall from a session.
