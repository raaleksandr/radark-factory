## ADDED Requirements

### Requirement: Configuration file name
Without `--config` the dispatcher SHALL read `radark.toml` in the current directory if it exists, else the legacy `harness.toml` there if it exists. If both exist it MUST stop before any hub command and any session with exit code 2 and a message naming both files. An explicit `--config <path>` SHALL be used as given, whatever its name. Configuration keys are unchanged.

#### Scenario: New names only
- **WHEN** the dispatcher is started without `--config` in a directory with `radark.toml` that does not set `run_dir`
- **THEN** it reads `radark.toml`, keeps its run files in `.radark/` next to it and prints no legacy line

#### Scenario: Both configuration files present
- **WHEN** the dispatcher is started without `--config` in a directory with both `radark.toml` and `harness.toml`
- **THEN** it exits with code 2 and a message naming both files, and runs no hub command and starts no session

#### Scenario: Explicit old configuration file
- **WHEN** the dispatcher is started with `--config harness.toml`
- **THEN** it reads that file and prints no legacy line for the configuration file

#### Scenario: No configuration file
- **WHEN** the dispatcher is started without `--config` in a directory with neither file
- **THEN** it exits with code 2 and a message naming `radark.toml`

### Requirement: Run directory name
An explicit `run_dir` in the configuration SHALL always be used as given. Without `run_dir` the run directory SHALL be `.radark/` next to the configuration file, or the legacy `.harness/` there if `.radark/` does not exist and `.harness/` does. If both exist the dispatcher MUST stop with exit code 2 and a message naming both directories.

#### Scenario: Both run directories present
- **WHEN** the configuration does not set `run_dir` and both `.radark/` and `.harness/` exist next to it
- **THEN** the dispatcher exits with code 2 and a message naming both directories, and starts no session

#### Scenario: Explicit old run directory
- **WHEN** the configuration sets `run_dir = ".harness"`
- **THEN** the run directory is `.harness/` next to the configuration file, there is no legacy line for it, and the session prompts are the same as before this change

### Requirement: Legacy names are reported, never migrated
When a fallback picks a legacy name, the start lines of `run` and `once` and the output of `dry-run` and `plan` SHALL contain one line saying so and naming the new name; there SHALL be no such line when the legacy name is set explicitly. The dispatcher MUST NOT move, rename or delete a configuration file or run directory of either name.

#### Scenario: Old names only
- **WHEN** the dispatcher is started without `--config` in a directory with only `harness.toml`, which does not set `run_dir`, and only `.harness/` exists there
- **THEN** it reads `harness.toml`, keeps its run files in `.harness/`, and its start lines contain one legacy line for the file and one for the run directory, each naming the new name

#### Scenario: Nothing is migrated
- **WHEN** the dispatcher runs with the legacy names picked by the fallback
- **THEN** `harness.toml` and `.harness/` are still in place under the same names after it exits

## REMOVED Requirements

### Requirement: Configuration and run file names unchanged by the rename
**Reason**: The configuration file and run directory now default to `radark.toml` / `.radark/`; the old names stay as a fallback.
**Migration**: Nothing is required: pipelines with `harness.toml` / `.harness/` keep working (see "Configuration file name", "Run directory name" and "Legacy names are reported, never migrated"). To adopt the new names, stop the pipeline, rename `harness.toml` to `radark.toml`, and rename `.harness/` to `.radark/` or set `run_dir = ".harness"`.
