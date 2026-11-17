"""`radark --version`: the engine version and the `ho` it needs (version-flag D1-D3).

Reads no configuration, takes no lock, starts no session; the only process it runs is `ho --version --json`."""
from __future__ import annotations

import importlib.metadata
import shutil
import tomllib
from pathlib import Path

from . import hub as hub_mod

DIST = "radark-factory"
HO_COMMAND = ["ho"]  # the `ho` probed: found on PATH at call time (tests replace it; version-flag D3)
PROBE_TIMEOUT_S = 10  # an info command should not hang for the start check's 60 s


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def engine_version(package_dir: Path | None = None) -> str:
    """The source checkout's pyproject.toml next to the package first, then the installed metadata, else
    `unknown` (version-flag D2)."""
    pyproject = (package_dir or _package_dir()).parent / "pyproject.toml"
    if pyproject.is_file():
        try:
            project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        except (OSError, ValueError, UnicodeDecodeError):
            project = {}
        if not isinstance(project, dict):
            project = {}
        version = project.get("version")
        if project.get("name") == DIST and isinstance(version, str) and version:
            return f"{version} (source checkout)"
    try:
        return importlib.metadata.version(DIST)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def ho_line(timeout: float | None = None, supported=hub_mod.SUPPORTED_HO_CONTRACTS) -> str:
    timeout = PROBE_TIMEOUT_S if timeout is None else timeout
    head = f"ho: needs contract {hub_mod.contracts_text(supported)}; "
    cmd = list(HO_COMMAND)
    found = shutil.which(cmd[0]) if cmd else None
    if not found:
        return head + "no ho found on PATH"
    probe = hub_mod.probe_ho([found] + cmd[1:], None, timeout, supported)
    if probe.kind == "ok":
        return head + f"found ho {probe.version} (contract {probe.contract})"
    if probe.kind == "unsupported":
        return head + f"found ho {probe.version} (contract {probe.contract}), not supported"
    if probe.kind == "missing":
        return head + "no ho found on PATH"
    if probe.kind == "timeout":
        return head + f"ho did not answer --version within {timeout:g} s"
    return head + "found ho without a usable --version (too old)"


def lines() -> list[str]:
    return [f"radark {engine_version()}", ho_line()]
