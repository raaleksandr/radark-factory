# Design

## Context

HO-20261121-gcrx (RB-034) splits the fix in two. radark-handover makes `ho` never raise `UnicodeEncodeError` on
stdout/stderr and releases it as v0.2.1 (asked as HO-20261121-g3zr). radark-factory pins that release so installing
radark-factory installs the fixed `ho`. The cause was verified in the radark-handover working copy: `ho.py`
reconfigures the streams only under `if __name__ == "__main__":`, while `pyproject.toml` declares the console script
`ho = "ho:main"`.

The pin machinery exists already (pin-ho-contract-check): `HO_RELEASE_CONTRACTS` in `radark/hub.py`,
`SUPPORTED_HO_CONTRACTS`, and the offline test `radark/tests/test_ho_pin.py`.

## Goals / Non-Goals

**Goals:** pin `radark-handover` v0.2.1; keep the pin test green; bump radark-factory's version for a release.

**Non-Goals:** no encoding workaround in the dispatcher (it reads `ho ... --json` through pipes it controls; the
fix belongs to `ho`); no change to the start check, `SUPPORTED_HO_CONTRACTS` or any output; no tag, push, install
or release.

## Decisions

- **D1 — Wait for radark-handover's `ho done`.** Apply starts the code edits only after HO-20261121-g3zr is done and
  the radark-handover working copy reports `ho --version --json` → version `0.2.1`. The contract it reports is the
  value written into the table. If HO-20261121-g3zr is not done yet when apply runs, apply stops at that task and
  reports it as waiting (it does not pin a tag whose content is unknown).
- **D2 — Keep `v0.2.0` in the table.** The table records every known tag; removing the old one gains nothing and
  would make a checkout of an older pin fail the test needlessly. The test fixtures that use `v0.2.0` as a made-up
  example stay as they are (they test the logic, not the real pin); only places that describe *the current pin*
  move to `v0.2.1`.
- **D3 — Contract other than 1.** If radark-handover reports a contract other than `1` for v0.2.1, the engine does
  not support it: apply does not pin it, comments on HO-20261121-gcrx (`ho comment`) and stops, since supporting a
  new contract is a separate change.
- **D4 — Version 0.8.0.** A new pinned dependency is a minor release in this repository's usual steps (0.6.0 →
  0.7.0 were minor). The bump is a separate commit `Release 0.8.0` like earlier releases; tagging is the owner's.
- **D5 — Doc examples.** README examples that show `ho 0.2.0` as sample output of `ho --version` stay unless they
  claim to be the pinned release; text that names the pinned tag is updated. Spec scenarios that use `0.2.0` as a
  sample version (Compatibility of ho, Reporting the ho version, Version flag) are examples, not the pin, and are
  not changed.

## Risks / Trade-offs

- The pin names a tag the owner has not created yet; `pip install` of the new radark-factory fails until the owner
  tags radark-handover v0.2.1. Mitigation: the result of `ho done` says the order (tag radark-handover v0.2.1 first,
  then release radark-factory 0.8.0).
- The fix itself is verified by radark-handover's tests, not here; radark-factory tests use the fake `ho`.

## Assumptions (unattended session)

- radark-factory sends the request to radark-handover (the handover says "ask them by a handover"); it was sent in
  the propose session as HO-20261121-g3zr so the work can run in parallel.
- Version number 0.8.0 (D4) chosen without asking.
