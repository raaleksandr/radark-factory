"""`radark example-config` and the packaged example configurations (ship-example-configs, tasks 3.1-3.4)."""
import os
import re
import shutil
import subprocess
import sys
import tomllib
from fnmatch import fnmatch
from pathlib import Path

import pytest

import radark
from radark import examples

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(radark.__file__).resolve().parent
NOTE = "note: `python -m harness` is deprecated, use `python -m radark` (kept for at least one release)"
DOCS = {"docs/setup.md": ROOT / "docs", "README.md": ROOT, "radark/README.md": ROOT / "radark"}


def run(*args: str, cwd: Path, pythonpath: Path = ROOT, module: str = "radark") -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(pythonpath), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", module, *args], capture_output=True, env=env, cwd=cwd, timeout=120)


@pytest.fixture(scope="module")
def package_copy(tmp_path_factory):
    """A copy of the `radark` package (without tests) outside the repository: only it is on PYTHONPATH."""
    root = tmp_path_factory.mktemp("installed")
    shutil.copytree(PACKAGE, root / "radark", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    return root


# ---- the files come from the package (task 3.1)

@pytest.mark.parametrize("flags,name", [((), "radark.toml.example"), (("--machine",), "machine.toml.example")])
def test_prints_the_packaged_file_outside_the_repository(package_copy, tmp_path, flags, name):
    result = run("example-config", *flags, cwd=tmp_path, pythonpath=package_copy)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (package_copy / "radark" / "examples" / name).read_bytes()
    assert list(tmp_path.iterdir()) == []  # nothing written, no run directory


@pytest.mark.parametrize("flags,name", [((), "radark.toml.example"), (("--machine",), "machine.toml.example")])
def test_path_points_inside_the_package(package_copy, tmp_path, flags, name):
    result = run("example-config", *flags, "--path", cwd=tmp_path, pythonpath=package_copy)
    assert result.returncode == 0, result.stderr
    shown = Path(result.stdout.decode("utf-8").strip())
    assert shown.is_absolute()
    assert shown.resolve() == (package_copy / "radark" / "examples" / name).resolve()


# ---- writing (task 3.2)

def test_o_writes_exact_bytes_and_refuses_existing(tmp_path):
    target = tmp_path / "radark.toml"
    result = run("example-config", "-o", str(target), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == examples.read("radark")
    assert b"wrote" in result.stdout and b"radark.toml.example" in result.stdout

    target.write_bytes(b"mine\n")
    result = run("example-config", "-o", str(target), cwd=tmp_path)
    assert result.returncode == 2
    assert target.read_bytes() == b"mine\n"
    err = result.stderr.decode("utf-8")
    assert str(target) in err and "--force" in err

    result = run("example-config", "--machine", "-o", str(target), "--force", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == examples.read("machine")


def test_o_missing_parent_directory(tmp_path):
    target = tmp_path / "no-such-dir" / "radark.toml"
    result = run("example-config", "-o", str(target), cwd=tmp_path)
    assert result.returncode == 2
    assert str(target) in result.stderr.decode("utf-8")
    assert not target.parent.exists()


@pytest.mark.parametrize("args", [("--path", "-o", "x.toml"), ("--force",)])
def test_usage_errors(tmp_path, args):
    result = run("example-config", *args, cwd=tmp_path)
    assert result.returncode == 2
    assert list(tmp_path.iterdir()) == []


def test_reads_no_configuration(tmp_path):
    result = run("--config", str(tmp_path / "missing.toml"), "example-config", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == examples.read("radark")
    assert list(tmp_path.iterdir()) == []  # no .radark / .harness run directory


# ---- the documented copy is the packaged one (task 3.3)

def test_doc_links_point_to_the_packaged_files():
    seen = set()
    for doc, base in DOCS.items():
        text = (ROOT / doc).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#\s]*\.toml\.example)\)", text):
            resolved = (base / target).resolve()
            assert resolved.parent == (PACKAGE / "examples").resolve(), (doc, target)
            kind = "machine" if resolved.name == "machine.toml.example" else "radark"
            assert resolved.read_bytes() == examples.read(kind)
            seen.add(resolved.name)
        assert "radark example-config" in text, doc
    assert seen == set(examples.NAMES.values())


def test_no_root_copies():
    assert list(ROOT.glob("*.toml.example")) == []
    for doc in DOCS:
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "](../radark.toml.example)" not in text and "](radark.toml.example)" not in text
        assert "](../machine.toml.example)" not in text and "](machine.toml.example)" not in text
        assert "not installed with the package" not in text


def test_package_data_matches_both_files():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["radark"]
    for name in examples.NAMES.values():
        assert any(fnmatch(f"examples/{name}", pattern) for pattern in patterns), name


def test_examples_still_parse_as_toml():
    for kind in examples.NAMES:
        tomllib.loads(examples.read(kind).decode("utf-8"))


# ---- deprecated alias (task 3.4)

@pytest.mark.parametrize("flags", [(), ("--machine",), ("--force",)])
def test_harness_alias_same_output(tmp_path, flags):
    new = run("example-config", *flags, cwd=tmp_path)
    old = run("example-config", *flags, cwd=tmp_path, module="harness")
    assert old.stdout == new.stdout
    assert old.returncode == new.returncode
    old_err = old.stderr.decode("utf-8").splitlines()
    assert old_err[0] == NOTE
    assert old_err[1:] == new.stderr.decode("utf-8").splitlines()
