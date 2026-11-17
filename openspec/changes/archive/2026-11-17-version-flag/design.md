# Design: `radark --version` (HO-20261117-c3hc)

## Context

`radark` (`radark/__main__.py` `main()`) is an `argparse` parser with required subcommands; every command except
`status`, `cockpit` and `test-slot` reads a configuration first. The `ho` start check is `radark/hub.py`
`check_ho(cmd, hub, ...)`, which runs `ho --version --json` with `HO_HUB` set and returns a `HoVersion` or one
message. The package version lives in `pyproject.toml` (`version = "0.5.0"`) and, once installed, in the
distribution metadata of `radark-factory`. The handover asks for an info flag that prints the engine version and the
`ho` it needs, exit 0, without a configuration and without a session.

## Goals / Non-Goals

**Goals:** a top-level `--version` that answers in about a second in any directory; the same through the
`harness` alias; docs use it to check the install.

**Non-Goals:** `--version --json`; a version per subcommand (`radark run --version`); checking Claude Code or
OpenSpec; changing the start check of `run` / `dry-run` / `plan`; reading the `ho` setting of a configuration.

## Decisions

### D1. Output form

Two lines on standard output, nothing on standard error (the `harness` alias keeps its one deprecation line):

```
radark 0.5.0
ho: needs contract 1; found ho 0.2.0 (contract 1)
```

The second line always starts `ho: needs contract <n>` (`hub.contracts_text()`, e.g. `1` or `1 or 2`), then `; `
and one of:

| `ho` on `PATH` | after `; ` |
|---|---|
| compatible | `found ho 0.2.0 (contract 1)` |
| unsupported contract | `found ho 0.9.0 (contract 2), not supported` |
| not on `PATH` / cannot start | `no ho found on PATH` |
| exits non-zero or no usable answer | `found ho without a usable --version (too old)` |
| no answer within the time limit | `ho did not answer --version within 10 s` |

The product example's `ho >= 0.2.0` is replaced by the contract number: the engine checks the JSON contract, not a
minimum `ho` release, and the start check messages already speak in contracts (assumption, recorded here;
unattended propose).

### D2. Engine version source

`radark/version.py` `engine_version() -> str`:

1. **Source checkout first.** If `pyproject.toml` exists in the parent directory of the imported `radark` package
   and its `[project] name` is `radark-factory` (read with `tomllib`), the version is its `[project] version` plus
   ` (source checkout)`. This covers the working tree on `PYTHONPATH` / as current directory and an editable install,
   where installed metadata could be stale or belong to another install.
2. Else `importlib.metadata.version("radark-factory")` (the installed release, the source a release uses).
3. Else (`PackageNotFoundError`, unreadable `pyproject.toml`) `unknown`.

Line 1 is `radark <version>`, e.g. `radark 0.5.0` or `radark 0.5.0 (source checkout)`. An installed wheel has no
`pyproject.toml` next to the package (site-packages), so step 1 never fires for a release.

### D3. Which `ho`, and how it is probed

The flag reads no configuration (handover), so it probes `ho` as found by `shutil.which("ho")` (the same lookup the
configuration uses for the default `ho = "ho"`); the line says "on PATH" so a pipeline with another `ho` in its
configuration is not misled. Tests replace the command through a module attribute `radark.version.HO_COMMAND`
(default `["ho"]`, resolved with `shutil.which` at call time), since a fake `ho` on `PATH` is not portable on
Windows.

`check_ho` gets `hub: Path | None`: with `None` it leaves `HO_HUB` as the environment has it (still drops
`HO_TEAM`); `ho --version --json` does not need a hub. The flag passes `timeout=10` (an info command should not hang
for the start check's 60 s). The flag does not show `check_ho`'s messages; it needs the outcome kind and, for an
unsupported contract, the found version. So `check_ho` is split into `probe_ho(cmd, hub, timeout, supported) ->
HoProbe` (kind `ok` / `missing` / `timeout` / `old` / `unsupported`, plus version, contract, features, exit code,
error text) and `check_ho`, which formats its existing messages from the probe. One probe per call; the start
check's messages and behaviour stay byte-for-byte the same (`test_ho_check.py` passes unchanged). `version.py`
maps the probe kind to the D1 phrases.

### D4. Wiring in `main()`

A custom `argparse.Action` (`nargs=0`) on the top-level parser: when `--version` is seen it prints
`version.lines()` and calls `parser.exit(0)`. argparse handles it before the required-subcommand check, so
`radark --version`, `radark --config X --version` and `radark --version run` all print and exit 0 without reading
the configuration. It is added after `test-slot` interception, which only triggers on `test-slot`. Help text:
`print the radark version and the ho it needs, then exit`.

The `harness` alias calls the same `main()`, so it behaves the same (stdout identical, exit 0) plus its existing
deprecation line on stderr.

### D5. Docs

- `docs/setup.md` Install check: `radark --version` replaces `pip show radark-factory  # or: uv tool list`; the
  sentence "`radark` has no `--version` flag" becomes one saying `radark --version` prints the engine version and
  the `ho` contract it needs and the `ho` found on `PATH`; the existing `ho --version` lines stay.
- `README.md` Quick start: one line `radark --version   # the installed version and the ho it needs` after the
  install line.
- `radark/README.md` Commands: `python -m radark --version` with a short comment; "Compatibility of `ho`": one
  sentence that `--version` reports the same contract without stopping.

## Risks / Trade-offs

- [The `ho` on `PATH` differs from the pipeline's configured `ho`] → the line says "on PATH"; `dry-run` remains the
  check of the configured one (stated in `docs/setup.md`).
- [Refactoring `check_ho` changes a start-check message] → `check_ho` keeps its signature (plus `hub=None`
  allowed) and its texts; the existing `test_ho_check.py` must pass unchanged.
- [A source checkout run from another directory without `PYTHONPATH` imports the installed release] → expected:
  the flag reports what is imported; that is the version that would run.

## Open Questions

None. Assumptions (unattended propose, 2026-11-17): contract instead of a minimum `ho` release (D1); source
checkout detected by `pyproject.toml` next to the package (D2); `ho` from `PATH` with a 10 s limit (D3).
