## ADDED Requirements

### Requirement: Machine-wide pipeline registry
The dispatcher SHALL keep a registry of known pipelines in the machine directory (`pipelines.json`, changed under an OS file lock and written atomically). `run`, `once` and `dry-run` SHALL record, before any session, the resolved configuration path, the pipeline name and the last-seen time, updating an existing entry with the same resolved path (case-insensitive on Windows). The registry SHALL hold configuration paths only, no hub path. `plan`, `status` and the other commands SHALL NOT record.

#### Scenario: Recorded by dry-run
- **WHEN** the owner runs `dry-run` with a configuration that has `name = "alpha"`
- **THEN** the registry has one entry with that configuration's resolved path, name `alpha` and the current time

#### Scenario: Plan does not record
- **WHEN** the owner runs `plan` with a configuration that is not registered
- **THEN** the registry is unchanged

### Requirement: Registered pipeline name and registry errors
The recorded pipeline name SHALL be the configuration's optional top-level `name` key when set, otherwise the name of the run directory's parent folder. A registry that cannot be read or written SHALL be reported with one line and MUST NOT stop the run.

#### Scenario: Name from the folder
- **WHEN** a configuration has no `name` and its run directory is `<dir>/beta/.harness`
- **THEN** the recorded name is `beta`

#### Scenario: Corrupt registry
- **WHEN** `pipelines.json` is not valid JSON and the owner runs `once`
- **THEN** one line reports the registry problem, the session still runs, and the registry is rewritten with this pipeline

### Requirement: Pipeline name setting
The configuration file SHALL accept an optional top-level `name`, a non-empty string naming the pipeline in the registry and in the cockpit. Another value MUST be refused as a configuration error (exit 2) naming the key.

#### Scenario: Empty name
- **WHEN** `radark.toml` sets `name = ""`
- **THEN** `dry-run` exits with code 2 naming `name`

### Requirement: Cockpit port in machine configuration
`machine.toml` SHALL accept an optional `[cockpit] port`, an integer from 1 to 65535, used by the `cockpit` command when no `--port` is given. The key SHALL NOT affect `run`, `once`, `dry-run` or `status`, and an invalid value SHALL be refused only by `cockpit`.

#### Scenario: Invalid cockpit port does not stop a run
- **WHEN** `machine.toml` sets `[cockpit] port = 0` and the owner runs `dry-run`
- **THEN** `dry-run` runs as usual, while `cockpit` exits with code 2 naming `cockpit.port`
