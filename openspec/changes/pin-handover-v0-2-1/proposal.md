# Proposal

Handover: **HO-20261121-gcrx** (backlog item RB-034, from `radark-product`). Part 1 of its work split is asked from
the `radark-handover` team as **HO-20261121-g3zr**.

## Why

On Windows, in a console whose output encoding is cp1252 (no `PYTHONIOENCODING`), the installed `ho` 0.2.0 crashes
with `UnicodeEncodeError` when a handover title has characters outside cp1252 (Cyrillic, `→`): its stream setup runs
only under `if __name__ == "__main__":`, which the installed console script `ho = "ho:main"` never reaches. Agents
and the owner cannot read their inbox without an encoding workaround. radark-handover fixes it in **v0.2.1**; the
pipelines get the fixed `ho` only through the radark-factory release that pins it.

## What Changes

- `pyproject.toml` pins `radark-handover @ git+...@v0.2.1` instead of `@v0.2.0`.
- `HO_RELEASE_CONTRACTS` in `radark/hub.py` gets `"v0.2.1"` mapped to the contract that tag's `ho --version --json`
  reports (expected `1`, the same as `v0.2.0`); `v0.2.0` stays in the table.
- Tests and docs that name the current pin are updated (`radark/tests/test_ho_pin.py`, README examples where they
  describe the pinned release).
- radark-factory version bump `0.7.0` → `0.8.0` (a new release that installs the fixed `ho`).
- No change to the dispatcher's behaviour: `SUPPORTED_HO_CONTRACTS` stays `(1,)` unless radark-handover reports a
  different contract for v0.2.1 (then design D3 applies).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: requirement "Pinned ho matches the supported contract" — the current-pin scenario names
  `v0.2.1`, and the table keeps earlier known tags so an older pin is still recognised.

## Impact

- Files: `pyproject.toml`, `radark/hub.py`, `radark/tests/test_ho_pin.py`, possibly `README.md` /
  `radark/README.md` examples.
- Dependency: radark-handover v0.2.1 (from HO-20261121-g3zr). The tag itself is created by the owner; the pin test
  is offline and does not need the tag to exist.
- Installing the new radark-factory pulls the fixed `ho`; install, tag and release are the owner's steps.
