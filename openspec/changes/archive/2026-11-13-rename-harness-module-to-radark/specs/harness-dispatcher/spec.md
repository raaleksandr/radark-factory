## ADDED Requirements

### Requirement: Package and command name
The dispatcher SHALL be installed as the Python package `radark` and started with `python -m radark <command>` or the `radark` console script. Its hook scripts and the sandbox script SHALL be resolved inside the installed `radark` package. Texts the dispatcher writes that name a command (help, escalation hints, error hints, sandbox hints) SHALL name `python -m radark`.

#### Scenario: Starting by the new name
- **WHEN** the owner runs `python -m radark --help` or `radark --help` after installing the release
- **THEN** the dispatcher's help is printed, naming `python -m radark` as the program, and the exit code is 0

#### Scenario: Hooks come from the installed package
- **WHEN** the dispatcher starts a Claude Code session
- **THEN** every hook command it passes to the session points to a script inside the `radark` package's `hooks` directory

#### Scenario: Escalation hint names the new command
- **WHEN** the dispatcher writes an escalation that tells the owner how to clear the item `HO-1`
- **THEN** the hint names `python -m radark clear HO-1`

### Requirement: Deprecated alias harness
For at least one release after the rename, `python -m harness <arguments>` SHALL run the same dispatcher as `python -m radark <arguments>`, with the same standard output and the same exit code; it MAY add one deprecation line to standard error naming `python -m radark`. Importing `harness` or `harness.<module>` SHALL give the same module objects as `radark` and `radark.<module>`.

#### Scenario: Old command, same result
- **WHEN** the owner runs `python -m harness dry-run` and `python -m radark dry-run` with the same configuration
- **THEN** both print the same standard output and end with the same exit code, and the first also prints one deprecation line to standard error

#### Scenario: Old command with a bad argument
- **WHEN** the owner runs `python -m harness` with an unknown command
- **THEN** the exit code is the same as for `python -m radark` with that command

#### Scenario: Old import
- **WHEN** existing code runs `from harness.state import GoalRun`
- **THEN** the import succeeds and `GoalRun` is the same object as `radark.state.GoalRun`

### Requirement: Configuration and run file names unchanged by the rename
The package rename SHALL NOT change the default configuration file name `harness.toml`, the example file `harness.toml.example`, the default run directory `.harness/` or any configuration key.

#### Scenario: Run files keep their names
- **WHEN** the dispatcher is started as `python -m radark` in a directory with `harness.toml`
- **THEN** it reads `harness.toml` by default and keeps its run files in `.harness/` as before
