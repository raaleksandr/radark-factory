# Design: ship the example configurations with the package (HO-20261117-nymh)

## Context

The two example files sit in the repository root and are not in `[tool.setuptools.package-data]`, so a wheel has
neither. `radark/__main__.py` `main()` is an `argparse` parser with required subcommands; `status`, `cockpit` and
`test-slot` already run without a configuration, `--version` (change version-flag) too. Package data is already
used for hooks, the sandbox script, workflow profiles and the cockpit page, resolved inside the installed `radark`
package. The handover asks for both examples as package data with one source of truth, a one-step way to get them
after `pip install` that never overwrites a file unasked, and docs that name that way.

## Goals / Non-Goals

**Goals:** both examples in every wheel and install; one copy in the repository; one command that prints or writes
either file; docs use the command.

**Non-Goals:** a generated or interactive configuration (`radark init`); filling in real paths; changing any
configuration key or the examples' settings (only comment lines that tell the reader where to copy the file from
may change); `--json` output.

## Decisions

### D1. One source of truth: move, not copy

The repository copies move (`git mv`) to `radark/examples/radark.toml.example` and
`radark/examples/machine.toml.example`; no root copy stays and no build step copies anything. Alternatives
considered: a setuptools hook copying the root files into the package at build time (custom build code; the
editable install and the working tree would differ from a wheel) and keeping both copies with a test that they are
equal (two hand-kept copies, ruled out by the handover). Moving costs only the root links, which this change
updates. `radark/examples/` has no `__init__.py`; `importlib.resources.files("radark") / "examples" / name` reads it
as package data (a wheel, an editable install, the working tree on `PYTHONPATH`).

`pyproject.toml` `[tool.setuptools.package-data]` `radark` adds `"examples/*.toml.example"`.

### D2. Command form

`radark example-config [--machine] [-o FILE [--force]] [--path]` (assumption, unattended propose: the handover lets
the team pick; a subcommand with options matches the handover's own example and the existing `status` / `cockpit`
style):

| call | result | exit |
|---|---|---|
| `radark example-config` | the content of `radark.toml.example` on standard output, unchanged | 0 |
| `--machine` | the same for `machine.toml.example` | 0 |
| `-o FILE` | writes the content to `FILE`, prints `wrote <FILE> (from radark.toml.example)`; the parent directory must exist | 0 |
| `-o FILE`, `FILE` exists | `<FILE> exists; not overwritten (add --force to replace it)` on standard error, file untouched | 2 |
| `-o FILE --force` | replaces `FILE` | 0 |
| `-o FILE`, parent missing / not writable | one line naming the file and the OS error on standard error | 2 |
| `--path` | the absolute path of the installed file on standard output | 0 |
| `--path` with `-o`, or `--force` without `-o` | usage error | 2 |

Redirecting standard output (`radark example-config > radark.toml`) overwrites by the shell's rules; that is an
explicit request of the user, so "never overwrite unasked" is met by `-o` refusing and by standard output never
touching a file itself. The docs show `-o`: it refuses to overwrite and avoids the Windows PowerShell 5.1 `>`
encoding (UTF-16) trap.

Writing: the bytes are written as stored (no newline translation), with exclusive create (`open(FILE, "xb")`)
unless `--force`, so a file created between a check and the write is still not overwritten. Printing writes the
bytes to `sys.stdout.buffer` (no console code-page translation of the UTF-8 text when redirected).

### D3. Wiring

`example-config` is a normal subparser; `main()` dispatches it right after parsing, before any configuration is
read, before the run lock and before any `ho` call (like `status` and `cockpit`). `--config` is accepted and
ignored. The `harness` alias behaves the same (same standard output and exit code, plus its one deprecation line on
standard error). Help: `print the example radark.toml (--machine: machine.toml); -o FILE writes it`.

Helper `radark/examples.py`: `NAMES = {"radark": "radark.toml.example", "machine": "machine.toml.example"}`,
`read(kind) -> bytes`, `path(kind) -> Path` (the file in the package directory; a zipped install is not a supported
layout, as for the hooks).

### D4. Docs

- `docs/setup.md` section 5: "Start from radark.toml.example (in the repository; it is not installed with the
  package)" becomes: write the example into the pipeline folder with `radark example-config -o radark.toml` (it
  refuses to overwrite an existing file; `--force` replaces it; without `-o` it prints the example), with a link to
  `radark/examples/radark.toml.example` for readers of the repository. The `machine.toml` sentence names
  `radark example-config --machine -o <machine directory>/machine.toml` and `radark status` for the directory.
- `README.md` Quick start: `copy radark.toml.example D:\work\my-factory\radark.toml` becomes
  `radark example-config -o D:\work\my-factory\radark.toml`; the `machine.toml.example` link goes to
  `radark/examples/machine.toml.example`.
- `radark/README.md` Setup step 2 and "Machine limits": the command instead of `copy`; Commands lists
  `python -m radark example-config [--machine] [-o FILE [--force]] [--path]`.
- Comment lines inside the example files that say how to get / copy them name the command.

### D5. Checks

- Tests (`radark/tests/test_example_config.py`):
  - a copy of the `radark` package (without `tests`) in a temporary directory, run as
    `python -m radark example-config` (and `--machine`, `--path`) in a subprocess with only that copy on
    `PYTHONPATH` and an empty working directory: the output equals the packaged file and `--path` points inside the
    copy — the files come from the package, not from the repository path;
  - `-o` writes the exact bytes, refuses an existing file (exit 2, content unchanged), `--force` replaces; a missing
    parent directory gives exit 2; no configuration is read (`--config <missing file>` still works) and no run
    directory is created;
  - the documented copy is the packaged one: the links to the examples in `docs/setup.md`, `README.md` and
    `radark/README.md` resolve to `radark/examples/<name>`, which is byte-equal to what `examples.read()` returns,
    and no root `*.toml.example` exists or is linked;
  - `pyproject.toml` package data has a pattern matching both files;
  - `python -m harness example-config`: same standard output and exit code.
- Wheel: built once by hand (`python -m pip wheel . --no-deps -w <temp dir>`) and listed with `zipfile` for
  `radark/examples/radark.toml.example` and `radark/examples/machine.toml.example`; the command and result are
  recorded in the tasks notes and in `ho done`. Not an automated test: a wheel build needs the build backend (and
  possibly the network) and is slow; the package-data test guards the pattern.

## Risks / Trade-offs

- [Old links or habits use the root files] → every repository link is updated; a test checks that no doc names a
  root `*.toml.example` path.
- [`>` in Windows PowerShell 5.1 writes UTF-16] → the docs use `-o`.
- [The wheel build cannot run in the session (no build backend offline)] → try `--no-build-isolation` with the
  installed setuptools; if that fails too, record the error and report it in `ho done` instead of claiming the
  check.

## Open Questions

None. Assumptions (unattended propose, 2026-11-17): move instead of a build-time copy (D1); the form
`example-config` with `--machine`, `-o`, `--force`, `--path` (D2); the wheel check is manual, not a test (D5).
