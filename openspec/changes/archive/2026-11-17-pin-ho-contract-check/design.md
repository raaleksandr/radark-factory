# Design: a release cannot pin an incompatible ho (HO-20261117-c5ns)

## Context

`hub.SUPPORTED_HO_CONTRACTS = (1,)` is what the start check (`hub.check_ho_version`) accepts from
`ho --version --json`. `pyproject.toml` pins `radark-handover @ git+https://...@v0.2.0`. The two are edited by hand
in different files and nothing compares them. The tests must stay offline and use the fake `ho`; the engine is
standard library only (Python 3.11+, so `tomllib` is available).

## Goals / Non-Goals

**Goals:** an incompatible or unknown pin fails the suite; the release step says to bump pin, table and contract
together.

**Non-Goals:** changing the runtime start check or its messages; resolving tags over the network; checking the `ho`
installed on the machine; automating releases (tag, push, release stay the owner's steps).

## Decisions

### D1. A tag-to-contract table in `radark/hub.py`

`HO_RELEASE_CONTRACTS = {"v0.2.0": 1}` (a plain dict of tag -> contract), directly under `SUPPORTED_HO_CONTRACTS`,
with a comment that it lists the radark-handover release tags the engine knows and must be updated together with
the pin in `pyproject.toml`. Chosen over the handover's other option (one "minimum tag" constant) because contracts
are not ordered by tag in general (a later tag may raise the contract beyond what the engine supports), and the
table is explicit about each release the engine was checked against. Kept in `hub.py` so a contract bump edits
both constants in one place. The start check does not read it: at run time it checks the `ho` actually found.

### D2. The pin test parses `pyproject.toml` with `tomllib`

New `radark/tests/test_ho_pin.py`:

- Locate `pyproject.toml` at the repository root (`Path(__file__).resolve().parents[2]`); if it is not there (tests
  run from an installed package without the source tree), `pytest.skip` with a reason - it is a source-tree check.
  In this repository it always exists, so the test runs.
- From `project.dependencies` take the one entry whose name (text before `@`, stripped) is `radark-handover`; the
  tag is the text after the last `@` in the URL. Small pure helpers `pin_tag(dependencies) -> str | None` and
  `pin_problem(tag, table, supported) -> str | None` do the work, so the wrong-pin cases are unit-tested on
  in-memory data without editing the real file.
- Assertions: the real pin has a tag, the tag is in `HO_RELEASE_CONTRACTS`, and its contract is in
  `SUPPORTED_HO_CONTRACTS`. Messages name the pin, the tag, the found contract (or "not in HO_RELEASE_CONTRACTS")
  and the supported contracts, and say to update pin, table and `SUPPORTED_HO_CONTRACTS` together.
- Extra cases on in-memory data: tag mapped to contract 2 with supported `(1,)` fails; unknown tag fails;
  dependency without `@` or missing fails; a table entry whose contract is supported passes.

The helpers live in the test module (they are test logic, not runtime code).

### D3. No test against an installed `ho`

The handover offers an optional test that runs a real installed `ho --version --json` when present. Not done
(assumption of the unattended propose): the repository rule is that tests use the fake `ho` only, and such a test
would pass or fail depending on what is installed on the machine (a pipeline runs an installed release, a developer
may have another one) - the environment dependency the suite avoids. The runtime start check already reports an
incompatible installed `ho` with a clear message.

### D4. Release steps in the README

`README.md` "Development" gets a short "Releasing (owner's steps)" list: run the full suite; when the required `ho`
contract changes, bump the `radark-handover` pin in `pyproject.toml`, add the new tag to `HO_RELEASE_CONTRACTS`
with the contract that tag's `ho --version --json` reports, update `SUPPORTED_HO_CONTRACTS`, and the suite (with
`test_ho_pin.py`) must pass; then tag and release. When only the pin changes (a new radark-handover release with
the same contract), the tag is added to the table too. `radark/README.md` "Compatibility of `ho`" gets one sentence
pointing to the table and the pin test.

## Risks / Trade-offs

- The table is maintained by hand: a wrong entry (claiming a tag has contract 1 when it does not) is not caught
  offline. Mitigation: the release step says to take the contract from that tag's `ho --version --json`; the
  runtime check still catches it on the user's machine.
- A pin by commit hash or branch instead of a tag is reported as "not in the table" - intended: a release pins a
  tag.
