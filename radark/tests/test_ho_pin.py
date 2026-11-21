"""The radark-handover pin in pyproject.toml matches a supported ho contract (pin-ho-contract-check D2).

Offline: reads only pyproject.toml and the constants in radark/hub.py; never runs an `ho`.
"""

from pathlib import Path

import pytest
import tomllib

from radark.hub import HO_RELEASE_CONTRACTS, SUPPORTED_HO_CONTRACTS

PACKAGE = "radark-handover"
PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
WHAT_TO_UPDATE = ("update the radark-handover pin in pyproject.toml, HO_RELEASE_CONTRACTS and "
                  "SUPPORTED_HO_CONTRACTS in radark/hub.py together")


def pin_entry(dependencies) -> str | None:
    """The `radark-handover` entry of `project.dependencies`, or None."""
    for dep in dependencies or ():
        name = dep.split("@", 1)[0].split(";", 1)[0].strip()
        if name == PACKAGE:
            return dep
    return None


def pin_tag(dependencies) -> str | None:
    """The tag after the last `@` of the radark-handover URL pin, or None if missing or not a URL pin."""
    dep = pin_entry(dependencies)
    if dep is None or "@" not in dep:
        return None
    url = dep.split("@", 1)[1].split(";", 1)[0].strip()
    if "@" not in url:
        return None
    tag = url.rsplit("@", 1)[1].strip()
    return tag or None


def pin_problem(dependencies, table, supported) -> str | None:
    """None if the pin's tag is in `table` with a contract in `supported`; otherwise the failure message."""
    supported_text = ", ".join(str(c) for c in supported)
    dep = pin_entry(dependencies)
    tag = pin_tag(dependencies)
    if tag is None:
        return (f"pin {dep!r}: a release must pin a radark-handover tag "
                f"(`{PACKAGE} @ git+...@<tag>`); {WHAT_TO_UPDATE}")
    if tag not in table:
        return (f"pin {dep!r}: tag {tag} is not in HO_RELEASE_CONTRACTS (supported contracts: {supported_text}); "
                f"{WHAT_TO_UPDATE}")
    contract = table[tag]
    if contract not in supported:
        return (f"pin {dep!r}: tag {tag} has ho contract {contract}, the engine supports contract(s) "
                f"{supported_text}; {WHAT_TO_UPDATE}")
    return None


def test_real_pin_is_compatible():
    if not PYPROJECT.is_file():
        pytest.skip("pyproject.toml not found: the pin check runs only in the source tree")
    with PYPROJECT.open("rb") as f:
        dependencies = tomllib.load(f).get("project", {}).get("dependencies", [])
    problem = pin_problem(dependencies, HO_RELEASE_CONTRACTS, SUPPORTED_HO_CONTRACTS)
    assert problem is None, problem


GOOD = [f"{PACKAGE} @ git+https://example.invalid/radark-handover.git@v0.2.0"]


def test_supported_entry_passes():
    assert pin_tag(GOOD) == "v0.2.0"
    assert pin_problem(GOOD, {"v0.2.0": 1}, (1,)) is None


def test_unsupported_contract_fails():
    problem = pin_problem(GOOD, {"v0.2.0": 2}, (1,))
    assert problem is not None
    assert "v0.2.0" in problem and "contract 2" in problem and "contract(s) 1" in problem
    assert "pyproject.toml" in problem and "SUPPORTED_HO_CONTRACTS" in problem


def test_unknown_tag_fails():
    problem = pin_problem(GOOD, {"v0.1.0": 1}, (1,))
    assert problem is not None
    assert "v0.2.0" in problem and "not in HO_RELEASE_CONTRACTS" in problem


@pytest.mark.parametrize("dependencies", [
    [],
    ["other-package @ git+https://example.invalid/other.git@v1.0.0"],
    [PACKAGE],
    [f"{PACKAGE}>=0.2"],
    [f"{PACKAGE} @ git+https://example.invalid/radark-handover.git"],
])
def test_missing_pin_or_tag_fails(dependencies):
    assert pin_tag(dependencies) is None
    problem = pin_problem(dependencies, {"v0.2.0": 1}, (1,))
    assert problem is not None and "must pin a radark-handover tag" in problem


def test_two_contracts_during_migration():
    assert pin_problem(GOOD, {"v0.2.0": 2}, (1, 2)) is None


def test_earlier_tag_stays_known():
    # pin-handover-v0-2-1 D2: moving the pin keeps earlier known tags in the table.
    assert HO_RELEASE_CONTRACTS.get("v0.2.0") == 1
    assert HO_RELEASE_CONTRACTS.get("v0.2.1") == 1
