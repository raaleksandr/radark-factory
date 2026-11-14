## ADDED Requirements

### Requirement: Public repository holds only invented example data
The repository's tracked files SHALL use only invented example data (neutral team names, invented handover IDs,
neutral item IDs and titles) and MUST NOT contain IDs or titles from a private product hub, owner paths, user names,
or product or company names. Radark-hub IDs cited as a change's provenance MAY stay.

#### Scenario: Change that removes private data does not quote it
- **WHEN** a change removes private data from the repository
- **THEN** its proposal, design, specs, tasks and commit messages describe that data without quoting it

#### Scenario: Grep for known private data finds nothing
- **WHEN** the repository's tracked files are searched (outside `.git`) for the real IDs, item IDs and titles from
  a private hub that a handover names, and for owner paths
- **THEN** the search has no hits

#### Scenario: README examples are invented
- **WHEN** a reader looks at the `dry-run` / goal-plan example and the console example in `radark/README.md`
- **THEN** every handover ID in them is invented and every item text is a neutral task (for example "Add a health
  check endpoint"), not an item of a real product

#### Scenario: Spec scenario and its test agree
- **WHEN** an example ID or title in a spec scenario is replaced with an invented one
- **THEN** the test that checks that scenario uses the same invented ID or title, and the full test suite passes

#### Scenario: Provenance IDs stay
- **WHEN** an archived change of this repository names the radark hub handover it was made for
- **THEN** that ID stays unchanged
