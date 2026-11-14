## ADDED Requirements

### Requirement: Public repository holds only invented example data
The repository's tracked files (README and docs, `openspec/` including archived changes, tests and their golden
files, the sandbox and code) SHALL use only invented example data: neutral team names (`product`, `app`, `backend`,
`strategy`), invented handover IDs that do not exist in any real hub, and neutral item IDs and titles. They MUST NOT
contain handover IDs, item IDs or item titles from a private product hub, owner paths (a drive letter or home
directory with a user folder), user names, or product or company names. IDs of radark's own hub cited as provenance
of a change ("Handover: HO-…") are radark's traceability and MAY stay. A change that removes private data MUST
describe it without quoting it.

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
