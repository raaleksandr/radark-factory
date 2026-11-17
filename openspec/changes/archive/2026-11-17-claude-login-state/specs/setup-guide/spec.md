## MODIFIED Requirements

### Requirement: Configuration and first dry run in the guide
The Configuration section SHALL start from `radark.toml.example`, name the minimum keys to edit and where the run directory goes, and mention `machine.toml` only for several pipelines on one computer. The First dry run section SHALL show a short neutral example of a healthy `radark dry-run` output, whose Claude Code line shows the login state, and the common errors with their fix: hub not found, team path wrong, `ho` incompatible, Claude Code not found or not logged in. The "NOT logged in" line SHALL be listed with its fix (run `claude` and log in) and marked as a warning that does not stop the start. The guide SHALL NOT say that `dry-run` does not check the Claude Code login.

#### Scenario: A common error
- **WHEN** `radark dry-run` stops because a team `repo` path does not exist
- **THEN** the guide shows the start of that message and how to fix it

#### Scenario: Not logged in
- **WHEN** a user's `radark dry-run` summary says `NOT logged in`
- **THEN** the guide's common errors show that line, say it is a warning that does not stop the start, and tell them to run `claude` and log in
