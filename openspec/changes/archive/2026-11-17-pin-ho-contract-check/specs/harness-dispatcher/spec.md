## ADDED Requirements

### Requirement: Pinned ho matches the supported contract
The engine SHALL keep one table, next to the supported contract constant, mapping each radark-handover release tag it knows to its `ho` JSON contract. An offline test SHALL read the `radark-handover` pin in `pyproject.toml` and fail when the pin or its tag is missing, the tag is not in the table, or the tag's contract is not supported; the message SHALL name the pin, the tag, the found contract and the supported contracts.

#### Scenario: Current pin is compatible
- **WHEN** `pyproject.toml` pins `radark-handover @ git+...@v0.2.0`, the table maps `v0.2.0` to contract `1`, and the engine supports contract `1`
- **THEN** the pin test passes

#### Scenario: Pin to a tag with an unsupported contract
- **WHEN** the pin names a tag the table maps to contract `2` and the engine supports only contract `1`
- **THEN** the pin test fails with a message naming the tag, contract `2` found and contract `1` supported

#### Scenario: Pin to an unknown tag
- **WHEN** the pin names a tag that is not in the table
- **THEN** the pin test fails with a message naming the tag and saying it is not in the table, so the table must be updated together with the pin

#### Scenario: Pin without a tag
- **WHEN** the `radark-handover` dependency has no `@<tag>` or is missing from `pyproject.toml`
- **THEN** the pin test fails with a message saying the release must pin a radark-handover tag

#### Scenario: Offline
- **WHEN** the pin test runs on a machine without network and without an installed `ho`
- **THEN** it gives the same result

### Requirement: Release step for the ho pin
The release steps in the README SHALL say that when the required `ho` contract changes, the `radark-handover` pin in `pyproject.toml`, the tag table and the supported contracts are updated together, and that the full test suite must pass before a release.

#### Scenario: Release step documented
- **WHEN** the owner reads the release steps in the README
- **THEN** they say to bump the `radark-handover` pin, the tag table and the supported contracts together when the required contract changes, and to run the full test suite before a release
