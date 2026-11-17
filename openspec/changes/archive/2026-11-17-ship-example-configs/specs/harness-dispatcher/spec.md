## ADDED Requirements

### Requirement: Example configurations are package data
The example configuration files `radark.toml.example` and `machine.toml.example` SHALL be installed with the `radark` package and read from the installed package, never from a repository path. The repository SHALL keep exactly one copy of each, the packaged one.

#### Scenario: Installed without the repository
- **WHEN** the `radark` package is run from a directory that holds only the package (no repository) and the owner asks for an example file
- **THEN** its content comes from the package's own copy

#### Scenario: One copy in the repository
- **WHEN** a reader follows a documentation link to an example file
- **THEN** the link points to the packaged copy, and no other copy of that file exists in the repository

### Requirement: Example configuration command
`radark example-config` SHALL print the example `radark.toml` unchanged on standard output and exit with code 0; with `--machine` it SHALL print the example `machine.toml` instead; with `--path` it SHALL print the path of the installed example file instead of its content. The command MUST NOT read a configuration file, take a lock, run a hub command or start a session. `python -m harness example-config` SHALL give the same standard output and exit code.

#### Scenario: Printing the example
- **WHEN** the owner runs `radark example-config` in an empty directory
- **THEN** standard output is the content of the packaged `radark.toml.example`, the exit code is 0, and no file is created

#### Scenario: Machine example
- **WHEN** the owner runs `radark example-config --machine`
- **THEN** standard output is the content of the packaged `machine.toml.example`

#### Scenario: Installed path
- **WHEN** the owner runs `radark example-config --machine --path`
- **THEN** standard output is the path of `machine.toml.example` inside the installed `radark` package

### Requirement: Writing an example file
`radark example-config -o FILE` SHALL write the example to `FILE`. When `FILE` already exists it MUST NOT change it and SHALL exit with code 2 and a message naming the file and `--force`, unless `--force` is given, which replaces the file.

#### Scenario: Writing a new file
- **WHEN** the owner runs `radark example-config -o radark.toml` and `radark.toml` does not exist
- **THEN** `radark.toml` is created with the content of the example, and the exit code is 0

#### Scenario: Existing file is not overwritten
- **WHEN** the owner runs `radark example-config -o radark.toml` and `radark.toml` exists
- **THEN** the file is unchanged, the exit code is 2, and the message names `radark.toml` and `--force`

#### Scenario: Replacing on request
- **WHEN** the owner runs `radark example-config -o radark.toml --force` and `radark.toml` exists
- **THEN** the file is replaced by the example, and the exit code is 0
