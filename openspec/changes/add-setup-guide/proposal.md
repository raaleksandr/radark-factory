# Proposal: "Setup from zero" guide for a new user

Handover: **HO-20261117-d7uw** (RB-009, "Setup-from-zero guide for a new user"), from `radark-product`.

## Why

A new user (the owner's colleagues, later the community) cannot get from nothing to a first `radark dry-run` and a
first real run without reading the engine source or asking the owner. The README "Quick start" is five lines and
assumes a hub, team repositories with `CLAUDE.md`, OpenSpec and a Claude Code login already exist; the needed facts
are spread over `README.md`, `radark/README.md`, `radark.toml.example`, the sandbox script and the radark-handover
README.

## What Changes

- New file `docs/setup.md`, **"Setup from zero"**: one page, in order: 1. Prerequisites, 2. Install, 3. Hub,
  4. Team repositories (with a copy-paste `CLAUDE.md` template and a `.claude/settings.json` example),
  5. Configuration, 6. First dry run (healthy output, common errors and fixes), 7. The sandbox, 8. First real run.
- A guide, not a second reference: it links to `radark/README.md` sections (configuration keys, `ho` compatibility,
  workflow profiles, owner workflow, console, pause / stop, several pipelines) and to the radark-handover README
  ("Set up a hub shared through git") instead of repeating them.
- `README.md`: a link to the guide at the top and in "Quick start".
- Every command and flag in the guide is checked against the current code; the guide is followed literally on a
  scratch directory up to a green `radark dry-run`, and the result reports which steps were run.
- Neutral examples only (`product`, `app`, `backend`, made-up `HO-…` IDs, `D:\work\my-factory`, `~/work/my-factory`).
- No code change: no new command or flag (in particular no `radark --version` and no sandbox command; the guide
  describes what exists today).

## Capabilities

### New Capabilities

- `setup-guide`: the "Setup from zero" guide — where it lives, how it is reached from the README, the sections it
  covers and in which order, what it links instead of repeating, and that its commands are verified and its
  examples neutral.

### Modified Capabilities

(none)

## Impact

- New `docs/setup.md`; small edit of `README.md` (link at the top and in "Quick start"); possibly a one-line
  cross-link from `radark/README.md` "Setup" to the guide.
- No change to the code, the tests, the run log, the state, the hub, the cockpit or the `ho` contract; no handover
  to `radark-handover` expected (product's decision 2026-11-17: the ho README already covers hub setup).
- The full test suite must still pass (it covers no documentation, but the handover asks for it).
