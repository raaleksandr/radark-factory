# Design: `radark.toml` / `.radark/` with a fallback to `harness.toml` / `.harness/`

Handover HO-20261114-upfg (RB-013). The product decisions in the handover are taken as they are; the points below
only fill in what the handover leaves open.

## Context

Today `--config` defaults to `harness.toml` (`radark/__main__.py`), `config.load()` sets
`run_dir = base / data.get("run_dir", ".harness")`, and the names appear in messages (`config.py`, `hub.py`), CLI
help, docstrings, the sandbox, the example file, `.gitignore`, both READMEs, `CLAUDE.md` and the spec requirement
"Configuration and run file names unchanged by the rename". Prompts do not hard-code the run directory: the parts
that name it (`<run_dir>/tmp/<team>/`, the test-slot wrapper) already use the resolved `cfg.run_dir`. The test
fixtures write `harness.toml` with an explicit `run_dir = "run"`.

## Goals / Non-Goals

Goals: new names by default; old names keep working with no edits; never guess when both exist; a one-line note when
a fallback picked an old name; every place that names the file or directory updated.

Non-goals: automatic migration; renaming configuration keys; renaming environment variables given to sessions and
hooks (`HARNESS_RUN_DIR`, `HARNESS_PARALLEL_SESSIONS`, `HARNESS_TEST_SLOT`, `HARNESS_TEST_SLOT_HELD`, ...): they are
an interface between the dispatcher and its own hooks and sessions, not file or directory names, and the handover
limits the scope to file and directory names. Any change to `radark-handover` or the hub format.

## Decisions

### D1. Configuration file resolution lives in `config.py`

`config.resolve_path(arg: str | None, cwd: Path) -> tuple[Path, str | None]` returns the file to read and an optional
legacy note:

| `--config` | `radark.toml` in cwd | `harness.toml` in cwd | result |
|---|---|---|---|
| given | - | - | the given path as is (relative to cwd), no note, whatever its name |
| not given | yes | no | `radark.toml`, no note |
| not given | no | yes | `harness.toml`, legacy note |
| not given | yes | yes | `ConfigError` naming both files -> exit 2 |
| not given | no | no | `ConfigError`: "configuration file not found: <cwd>/radark.toml (no legacy harness.toml either)" -> exit 2 |

`argparse` gets `default=None` for `--config`; its help reads "configuration file (default: radark.toml, or the
legacy harness.toml, in the current directory)". "Exists" means `is_file()`. Resolution happens first, so the
ambiguity stops `run`, `once`, `dry-run`, `plan`, `escalations`, `clear`, `keep` and `note` with exit 2 before the
`ho` check, before any hub command and before any session.

`status` (read-only, works without a valid configuration) uses the same resolution; a resolution error goes to its
existing "Configuration ... not read (...); repository conflicts are not checked." path and its exit code is
unchanged. Assumption (no owner available to ask): `status` is a view and starts nothing, so it keeps working
instead of exiting 2.

### D2. Run directory resolution in `config.load()`

If the configuration has `run_dir` it is used as today (`base / run_dir`), with no note, whatever its value,
including `".harness"`. Otherwise, with `base` the configuration file's directory:

- `.radark` exists -> `.radark`, no note;
- `.radark` does not exist and `.harness` exists -> `.harness`, legacy note;
- both exist -> `ConfigError` naming both directories and the ways out (remove or rename one, or set `run_dir`) ->
  exit 2;
- neither exists -> `.radark` (created later, as today).

"Exists" means `exists()`: a stray file of that name also counts, so the dispatcher never silently picks the other.

### D3. Legacy notes travel on `Config`

`Config` gets `notes: tuple[str, ...]` (default empty), filled by `load()` with the run-directory note and, through a
`legacy_note` argument passed from the CLI after D1, the configuration-file note. Texts (one line each):

- `Legacy name: harness.toml was used because there is no radark.toml; rename it to radark.toml (nothing else changes).`
- `Legacy name: run directory .harness/ was used because run_dir is not set and there is no .radark/; rename it to .radark/ or set run_dir = ".harness".`

They are printed once with the start lines of `run` / `once` (where the hub and teams are printed) and at the top of
`dry-run` and `plan` output. Nothing else in the output changes.

### D4. Messages name the file actually read

`config.py`'s `ho` contract message ("... or fix 'ho' in harness.toml") and `hub.py`'s ("... fix 'ho' in
harness.toml.") name the configuration file actually read (its file name, e.g. `radark.toml`); where `hub.py` does
not know the path it says "in the configuration file". `test_ho_check.py` is updated accordingly.

### D5. Machine-wide layer needs no format change

Machine records store the resolved absolute configuration path and run directory; repository conflicts compare the
normalised configuration path. Cases:

- Two instances started in the same directory resolve the same file (or both stop on ambiguity) -> same pipeline.
- An instance of an older installed release (always `harness.toml`) and a new one on the same directory with only
  `harness.toml` -> same path -> same pipeline, as today.
- The owner migrates (`harness.toml` -> `radark.toml`) while an old instance still runs -> different paths -> the new
  one sees a *different* pipeline holding the repositories and waits or refuses as for any other pipeline. This is
  the safe outcome; the README migration section says to stop the pipeline before renaming.

A test covers a record with an old-name configuration path seen by an instance with a new-name path as another
pipeline, and the same-path case as the same pipeline.

### D6. Example file, sandbox, `.gitignore`, docs

- `harness.toml.example` is renamed to `radark.toml.example` (`git mv`); its `run_dir` line becomes a comment showing
  the default (`# run_dir = ".radark"   # default; relative to this file`).
- `make_sandbox.py` writes `<dir>/radark.toml` without `run_dir`, so the sandbox exercises the new default; its
  printed command and docstring follow.
- `.gitignore` lists `radark.toml` and `.radark/` and keeps `harness.toml` and `.harness/` (legacy pipelines in a
  checkout).
- README, `radark/README.md` and `CLAUDE.md` use the new names; `radark/README.md` gets a section "Migrating from
  harness.toml / .harness/": nothing is required, old names keep working; to adopt the new names stop the pipeline,
  rename `harness.toml` -> `radark.toml`, then rename `.harness/` -> `.radark/` or keep it by setting
  `run_dir = ".harness"`.
- Test fixtures (`conftest.py`) write `radark.toml`; old-name cases are explicit tests.
- Module docstrings and CLI help that name the file follow.

### D7. One change, no split

The resolution, the notes and the renames in docs and sandbox are small and touch the same few files, so the
handover's optional split is not used.

## Risks / Trade-offs

- A pipeline started from a directory that has *both* `harness.toml` and a newly copied `radark.toml` stops with
  exit 2. Intended (never guess); the message says how to resolve it.
- A pipeline with `harness.toml`, no `run_dir` and an existing `.harness/` keeps using `.harness/` with a note; if
  the owner then creates `.radark/` by hand while keeping `.harness/`, it stops with exit 2 instead of silently
  switching state.
- Golden prompts: fixtures set `run_dir` explicitly, so they do not change; any change seen in apply is listed in the
  result.
