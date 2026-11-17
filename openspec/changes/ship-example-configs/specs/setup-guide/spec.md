## MODIFIED Requirements

### Requirement: Configuration and first dry run in the guide
The Configuration section SHALL start from `radark.toml.example`, obtained with `radark example-config` from the installed package (the guide SHALL NOT say it is not installed with the package or require the repository for it), name the minimum keys to edit and where the run directory goes, and mention `machine.toml` (obtained with `radark example-config --machine`) only for several pipelines on one computer. The First dry run section SHALL show a short neutral example of a healthy `radark dry-run` output, whose Claude Code line shows the login state, and the common errors with their fix: hub not found, team path wrong, `ho` incompatible, Claude Code not found or not logged in. The "NOT logged in" line SHALL be listed with its fix (run `claude` and log in) and marked as a warning that does not stop the start. The guide SHALL NOT say that `dry-run` does not check the Claude Code login.

#### Scenario: A common error
- **WHEN** `radark dry-run` stops because a team `repo` path does not exist
- **THEN** the guide shows the start of that message and how to fix it

#### Scenario: Not logged in
- **WHEN** a user's `radark dry-run` summary says `NOT logged in`
- **THEN** the guide's common errors show that line, say it is a warning that does not stop the start, and tell them to run `claude` and log in

#### Scenario: Example configuration after install
- **WHEN** a user who installed radark-factory without cloning the repository follows the Configuration section
- **THEN** the guide tells them to run `radark example-config -o radark.toml` in the pipeline folder, and says that it does not overwrite an existing file
