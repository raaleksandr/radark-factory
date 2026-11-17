# setup-guide Specification

## Purpose

A "Setup from zero" guide in the repository that takes a new user from nothing to a first `radark dry-run` and a first real run without reading the engine source.

## Requirements
### Requirement: Setup-from-zero guide
The repository SHALL have a guide `docs/setup.md` titled "Setup from zero" that takes a new user from nothing to a first `radark dry-run` and a first real run without reading the engine source. `README.md` SHALL link to it near its top and from its "Quick start" section.

#### Scenario: Reaching the guide
- **WHEN** a new user opens `README.md`
- **THEN** a link to `docs/setup.md` appears before the "Status" section, and the "Quick start" section also links to it

### Requirement: Sections of the guide
The guide SHALL have these sections in this order: Prerequisites, Install, Hub, Team repositories, Configuration, First dry run, The sandbox, First real run. Every step SHALL use only what an earlier step set up.

#### Scenario: Following the guide in order
- **WHEN** a new user with none of the prerequisites reads the guide from top to bottom
- **THEN** the sections appear in this order, and the First dry run section comes after Hub, Team repositories and Configuration

### Requirement: Prerequisites and install in the guide
The Prerequisites section SHALL name the Python version, Claude Code with its tested version and a login, Git, Node and the OpenSpec CLI (only for the `openspec` profile), and the Windows vs POSIX differences that matter. The Install section SHALL install radark-factory (which brings `ho`), show how to check both, including the `ho` JSON contract number, and say what the start check prints when `ho` is incompatible. The installed radark-factory SHALL be checked with `radark --version`, not with `pip show` or `uv tool list`.

#### Scenario: Checking the install
- **WHEN** a user follows the Install section
- **THEN** they can see the installed radark-factory, the `ho` version with its contract number, and the Claude Code version

#### Scenario: Engine version by its own flag
- **WHEN** a user reads the Install section's check commands
- **THEN** the engine version is checked with `radark --version`, and neither `pip show radark-factory` nor `uv tool list` is given as the way to check it

### Requirement: Hub and team repositories in the guide
The Hub section SHALL link to the radark-handover README for a hub shared through git and give the minimal commands for a local hub (a plain folder or a local git repository without a remote) and the meaning of `HO_HUB` / `HO_TEAM`. The Team repositories section SHALL give a copy-paste `CLAUDE.md` template, a `.claude/settings.json` example with `HO_HUB` / `HO_TEAM` in `env`, `openspec init` for the `openspec` profile, and what the product team that sends tasks needs.

#### Scenario: CLAUDE.md template is copy-paste ready
- **WHEN** a user copies the `CLAUDE.md` template into a new team repository and fills its placeholders
- **THEN** it states the team's role, hub and team, `ho sync` first and last, the owner-only actions and the decisions the team takes, and the workflow profile

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

### Requirement: Sandbox and first real run in the guide
The sandbox section SHALL show how to try the whole loop on a throw-away hub and throw-away repositories first, using what the engine has today without a new command. The First real run section SHALL cover `radark run` and `--until`, where to watch (the console, `console.log`, the cockpit), how to answer an escalation, and what the engine never does on its own (push, publish, pay).

#### Scenario: Trying the loop safely
- **WHEN** a user follows the sandbox section
- **THEN** they get a scratch setup on which `radark dry-run` succeeds without touching their real hub or repositories

### Requirement: The guide links instead of repeating
The guide SHALL link to the sections of `README.md`, `radark/README.md` and the radark-handover README that hold the reference details (configuration keys, `ho` compatibility messages, workflow profiles, several pipelines on one computer, owner workflow, console, cockpit, hub setup through git) instead of copying their tables. It SHALL NOT document a command, flag or key that the current code does not have.

#### Scenario: Reference details
- **WHEN** a user needs the full list of `[loop]` keys or every `ho` incompatibility message
- **THEN** the guide links to the `radark/README.md` section that lists them rather than repeating the list

#### Scenario: Only existing commands
- **WHEN** every command and flag in the guide is run against the current release
- **THEN** each exists and behaves as the guide says

### Requirement: Guide examples are neutral
Every example in the guide SHALL use neutral team names (`product`, `app`, `backend`, `strategy`), made-up handover IDs and neutral paths such as `D:\work\my-factory` or `~/work/my-factory`; it SHALL contain no owner path, no product, pipeline or company name and no excerpt of a real hub or run.

#### Scenario: Healthy dry-run example
- **WHEN** a reader looks at the example of a healthy `dry-run` output in the guide
- **THEN** it shows only neutral names, paths and IDs
