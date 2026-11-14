# Design: neutral examples

## Context

See proposal.md for the why. The private data to remove is named in the body of handover HO-20261114-flmx
(`ho show HO-20261114-flmx --json`): 15 real handover IDs from the owner's private product hub, private item IDs and
two product item titles. The apply session reads that list from the hub; this change deliberately does not repeat it,
because the change text itself is published.

At proposal time (2026-11-14) a grep found the real IDs in 16 tracked files: `radark/README.md` (14 hits),
`openspec/specs/harness-dispatcher/spec.md` (35 hits over 15 requirements), three archived change specs (2 each),
`docs/research/workflow-today.md`, `radark/sandbox/make_sandbox.py` (an invented `BL-003`, which stays) and the tests
`test_console.py`, `test_dispatcher.py`, `test_escalation.py`, `test_forecast.py`, `test_hub.py`, `test_prompts.py`,
`test_select.py`, `test_unconfigured.py`, `test_waiting.py`. A grep for owner paths and user names found only the
GitHub URL of the `radark-handover` dependency (README, `pyproject.toml`).

## Goals / Non-Goals

**Goals:**
- No hit outside `.git` for the handover's grep (the 15 IDs, the private item IDs, the two product titles, owner
  paths).
- README examples read as a coherent invented story.
- Specs and tests stay consistent; the full suite passes.

**Non-Goals:**
- Rewriting git history (the check excludes `.git`; history rewriting would be a push-level owner step anyway).
- Any behavior change of the dispatcher.
- A test that greps for the private IDs: it would have to contain them and so publish them again.

## Decisions

1. **Invented ID scheme.** Replacement IDs keep the real shape (`HO-YYYYMMDD-xxxx`, so parsing, sorting and
   shortening tests keep their meaning) and keep each original date part when a test depends on ordering or age;
   only the 4-character suffix becomes an obviously invented one built from a letter/digit pattern (`ab12`, `cd34`,
   `ef56`, …), in the style of the already-invented `HO-20261016-ab12` and `HO-20261024-k2m9`. One fixed mapping
   (old → new) is used across all files so that a scenario and its test stay paired. Each new ID is checked to be
   absent from the radark hub (`ho show <ID>` → not found) and from the handover's list. The mapping is kept only in
   the apply session's scratch space, never committed (it would pair the private IDs with their replacements).
   - Alternative: random fresh IDs per file — rejected, breaks scenario/test pairing and makes the diff harder to
     review.
2. **Spec scenarios are edited in place, not through MODIFIED deltas.** Replacing example IDs and titles in 15
   requirements of `harness-dispatcher` changes example data, not requirement behavior. Copying 15 full requirement
   blocks into MODIFIED deltas would be large and error-prone and would gain nothing on archive. So the apply phase
   edits the example data in `openspec/specs/harness-dispatcher/spec.md` directly, and the delta spec only ADDS the
   new requirement. Archived change specs are edited in place the same way (they are history, but a public one).
   - Alternative: MODIFIED deltas for every touched requirement — rejected as above.
3. **Neutral titles.** Private item titles become neutral software tasks with the same shape (length, punctuation,
   quotes) where a test checks truncation or formatting, e.g. "Add a health check endpoint", "Show the retry button
   on a failed upload". Private item IDs become neutral ones (`BL-101`, `ST-7`, …) that do not collide with the
   invented examples that stay (sandbox `BL-001..003`, the pricing-page examples in `test_escalation.py` and
   `test_goal_ends_with_run.py`).
4. **Golden files.** If a golden file (e.g. `radark/tests/golden/openspec_prompts.json`) contains a replaced ID, it is
   regenerated from the tests' own generator if one exists, else edited with the same mapping; the golden test must
   pass unchanged otherwise.
5. **Dependency URL stays (assumption).** The GitHub URL of `radark-handover` in `README.md` and `pyproject.toml`
   contains the owner's public GitHub account name. It is the published install source of the only runtime
   dependency, not private run data; it stays. Recorded as an assumption because no user was available to confirm.
6. **Sweep beyond the list.** The apply session greps all tracked files for: `HO-` IDs that are neither invented
   (after the replacement) nor radark-hub provenance; drive-letter or home-directory paths with a user folder; user
   names; capitalized product-like names in examples; and item IDs (`ST-`, `BL-`, other prefixes) in titles that read
   like real product work. Radark-hub IDs are told apart by `ho show <ID>` against the radark hub.

## Risks / Trade-offs

- [A test asserts on ordering, age or shortened suffixes of an ID] → keep the date part, pick suffixes that keep
  the same uniqueness for 4+-character shortening, run the affected test file after each file's edit.
- [A replaced ID accidentally exists in some real hub] → cannot be proved for a hub we cannot see; the obviously
  invented suffix pattern makes a collision unlikely and recognisable as an example.
- [The change text leaks what it removes] → proposal, design, tasks and commit messages describe the data only as
  "real IDs from a private hub"; the apply session checks its own commit messages and the `ho done` summary too.
- [Old texts remain in git history] → accepted; out of scope (see Non-Goals).

## Migration Plan

None: docs, specs and tests only. Rollback is reverting the commits.
