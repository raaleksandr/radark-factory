## MODIFIED Requirements

### Requirement: Pinned ho matches the supported contract
The engine SHALL keep one table, next to the supported contract constant, mapping each radark-handover release tag it knows to its `ho` JSON contract. A new pin SHALL add its tag to the table; earlier known tags SHALL stay in it. An offline test SHALL read the `radark-handover` pin in `pyproject.toml` and fail when the pin or its tag is missing, the tag is not in the table, or the tag's contract is not supported; the message SHALL name the pin, the tag, the found contract and the supported contracts.

#### Scenario: Current pin is compatible
- **WHEN** `pyproject.toml` pins `radark-handover @ git+...@v0.2.1`, the table maps `v0.2.1` to contract `1`, and the engine supports contract `1`
- **THEN** the pin test passes

#### Scenario: Earlier tag stays known
- **WHEN** the pin moves from `v0.2.0` to `v0.2.1`
- **THEN** the table still maps `v0.2.0` to contract `1`, and a pin naming `v0.2.0` would also pass the test

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
