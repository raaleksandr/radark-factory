# Proposal: a release cannot pin an incompatible ho

Handover: **HO-20261117-c5ns** (RB-018, "a release cannot pin an incompatible ho (pin test + release step)"), from
`radark-product`.

## Why

`pyproject.toml` declares `radark-handover @ git+...@<tag>` as the engine's only runtime dependency, and the engine
refuses at start any `ho` whose JSON contract is not in `hub.SUPPORTED_HO_CONTRACTS`. Nothing ties the two: a past
release pinned a radark-handover tag whose `ho` did not provide the needed contract, so a user who installed that
release got an `ho` the engine refused. Neither the tests nor the release steps catch such a mismatch today.

## What Changes

- One table in `radark/hub.py`, next to `SUPPORTED_HO_CONTRACTS`, maps the radark-handover release tags the engine
  knows to their JSON contract (`"v0.2.0": 1`).
- A new offline test reads the `radark-handover` pin from `pyproject.toml` (standard-library `tomllib`), takes its
  tag, and fails when the tag is not in the table or its contract is not in `SUPPORTED_HO_CONTRACTS`. The failure
  message names the pin, the tag, the found contract and the supported ones, and says what to update.
- The release steps are written down (README "Development" section, with a pointer from "Compatibility of `ho`" in
  `radark/README.md`): when the required `ho` contract changes, bump the `radark-handover` pin in `pyproject.toml`,
  add the tag to the table, update `SUPPORTED_HO_CONTRACTS`, and the full suite (including the pin test) must pass
  before a release.
- No change to the runtime start check, its messages, or any command output.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirement *Pinned ho matches the supported contract* - the declared radark-handover
  pin is checked by the test suite against the supported contract(s), and the release step says to bump them
  together.

## Impact

- `radark/hub.py`: one new constant (data only; not read by the start check).
- New test file `radark/tests/test_ho_pin.py`.
- `README.md` (release steps) and `radark/README.md` (pointer in "Compatibility of `ho`").
- No change to `pyproject.toml` content (the current pin `v0.2.0` already has contract 1), the run log, the state,
  the hub, the cockpit or the `ho` contract.
