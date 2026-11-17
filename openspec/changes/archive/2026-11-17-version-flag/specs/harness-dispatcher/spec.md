## ADDED Requirements

### Requirement: Version flag
`radark --version` and `python -m radark --version` SHALL print two lines on standard output, `radark <version>` and `ho: needs contract <n>; <found>`, and exit with code 0. The flag needs no subcommand and MUST NOT read a configuration file, take a lock, run a hub command other than the `ho` version probe, or start a session. `python -m harness --version` SHALL print the same standard output with the same exit code.

#### Scenario: Installed release with a compatible ho
- **WHEN** the owner runs `radark --version` with radark-factory 0.6.0 installed and an `ho` on `PATH` that reports version `0.2.0` and contract `1`
- **THEN** the output is `radark 0.6.0` and `ho: needs contract 1; found ho 0.2.0 (contract 1)`, and the exit code is 0

#### Scenario: No configuration in the current directory
- **WHEN** the owner runs `python -m radark --version` in an empty directory
- **THEN** it prints the two lines and exits with code 0, with no configuration error

#### Scenario: Deprecated alias
- **WHEN** the owner runs `python -m harness --version`
- **THEN** standard output is the same as for `python -m radark --version`, the exit code is 0, and standard error has the one deprecation line

### Requirement: Engine version source
The version on the first line of `--version` SHALL come from the `pyproject.toml` next to the imported package when that file belongs to radark-factory, marked `(source checkout)`; otherwise from the installed `radark-factory` package metadata; otherwise it SHALL be `unknown`.

#### Scenario: Installed release
- **WHEN** no radark-factory `pyproject.toml` is next to the package and the installed metadata says `0.6.0`
- **THEN** the first line is `radark 0.6.0`

#### Scenario: Source checkout
- **WHEN** the imported `radark` package sits in a radark-factory source checkout whose `pyproject.toml` has version `0.6.0`
- **THEN** the first line is `radark 0.6.0 (source checkout)`

### Requirement: The ho line of the version flag
The second line of `--version` SHALL name the supported `ho` JSON contract versions and describe the `ho` on `PATH`, probed once with `--version --json` under a short time limit. A missing, too old, silent or incompatible `ho` SHALL be described on that line and MUST NOT change the exit code 0.

#### Scenario: ho missing
- **WHEN** no `ho` can be found on `PATH`
- **THEN** the second line is `ho: needs contract 1; no ho found on PATH` and the exit code is 0

#### Scenario: Incompatible ho
- **WHEN** the `ho` on `PATH` reports version `0.9.0` and contract `2`, and the engine supports only contract `1`
- **THEN** the second line is `ho: needs contract 1; found ho 0.9.0 (contract 2), not supported` and the exit code is 0
