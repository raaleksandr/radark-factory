## MODIFIED Requirements

### Requirement: Prerequisites and install in the guide
The Prerequisites section SHALL name the Python version, Claude Code with its tested version and a login, Git, Node and the OpenSpec CLI (only for the `openspec` profile), and the Windows vs POSIX differences that matter. The Install section SHALL install radark-factory (which brings `ho`), show how to check both, including the `ho` JSON contract number, and say what the start check prints when `ho` is incompatible. The installed radark-factory SHALL be checked with `radark --version`, not with `pip show` or `uv tool list`.

#### Scenario: Checking the install
- **WHEN** a user follows the Install section
- **THEN** they can see the installed radark-factory, the `ho` version with its contract number, and the Claude Code version

#### Scenario: Engine version by its own flag
- **WHEN** a user reads the Install section's check commands
- **THEN** the engine version is checked with `radark --version`, and neither `pip show radark-factory` nor `uv tool list` is given as the way to check it
