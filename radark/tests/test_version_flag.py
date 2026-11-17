"""`radark --version` (version-flag, tasks 2.1-2.5) with the fake `ho`."""
import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

import pytest

from radark import version
from radark.__main__ import main
from radark.tests.conftest import FAKES

ROOT = Path(__file__).resolve().parents[2]
WRONG = {"schema_version": 2, "version": "0.9.0", "contract": 2}


@pytest.fixture
def fake_ho(env, monkeypatch):
    monkeypatch.setattr(version, "HO_COMMAND", [sys.executable, str(FAKES / "fake_ho.py")])
    return env


def run_flag(capsys, argv=("--version",)):
    capsys.readouterr()
    with pytest.raises(SystemExit) as exit_:
        main(list(argv))
    out, err = capsys.readouterr()
    return exit_.value.code, out, err


# ---- output (task 2.1)

def test_compatible_ho_prints_both_lines(fake_ho, capsys, monkeypatch):
    monkeypatch.setattr(version, "engine_version", lambda: "0.6.0")
    code, out, err = run_flag(capsys)
    assert code == 0 and err == ""
    assert out.splitlines() == ["radark 0.6.0", "ho: needs contract 1; found ho 0.2.0 (contract 1)"]


def test_the_flag_comes_before_the_subcommand_check(fake_ho, capsys):
    for argv in (["--version", "run"], ["--version", "status"]):
        code, out, _ = run_flag(capsys, argv)
        assert code == 0 and out.startswith("radark ")


# ---- no configuration (task 2.2)

def test_empty_directory(fake_ho, capsys, monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    code, out, err = run_flag(capsys)
    assert code == 0 and "Configuration" not in out + err and len(out.splitlines()) == 2
    assert list(empty.iterdir()) == []


def test_missing_config_file_is_not_read(fake_ho, capsys, tmp_path):
    missing = tmp_path / "no-such.toml"
    code, out, err = run_flag(capsys, ["--config", str(missing), "--version"])
    assert code == 0 and "Configuration" not in out + err
    assert not missing.exists() and not (fake_ho.root / "run").exists()
    hub = os.environ.get("HO_HUB")
    assert fake_ho.ho_calls() == [{"args": ["--version"], "team": None, "hub": hub}]


def test_existing_config_is_not_read(fake_ho, capsys):
    fake_ho.config_path.write_text("this is not toml = = =\n", encoding="utf-8")
    code, out, err = run_flag(capsys, ["--config", str(fake_ho.config_path), "--version"])
    assert code == 0 and err == ""
    assert [c["args"] for c in fake_ho.ho_calls()] == [["--version"]]
    assert not (fake_ho.root / "run").exists()


def test_ho_team_is_dropped(fake_ho, capsys, monkeypatch):
    monkeypatch.setenv("HO_TEAM", "app")
    assert run_flag(capsys)[0] == 0
    assert fake_ho.ho_calls()[0]["team"] is None


# ---- the ho line (task 2.3)

def test_ho_missing(env, capsys, monkeypatch):
    monkeypatch.setattr(version, "HO_COMMAND", [str(env.root / "no-such-ho.exe")])
    code, out, _ = run_flag(capsys)
    assert code == 0 and out.splitlines()[1] == "ho: needs contract 1; no ho found on PATH"


@pytest.mark.parametrize("answer", [{"exit": 1}, "ho 0.1.0", {"schema_version": 1}])
def test_ho_too_old(fake_ho, capsys, answer):
    fake_ho.set_hub({"_version": answer})
    code, out, _ = run_flag(capsys)
    assert code == 0
    assert out.splitlines()[1] == "ho: needs contract 1; found ho without a usable --version (too old)"


def test_ho_unsupported_contract(fake_ho, capsys):
    fake_ho.set_hub({"_version": WRONG})
    code, out, _ = run_flag(capsys)
    assert code == 0 and out.splitlines()[1] == "ho: needs contract 1; found ho 0.9.0 (contract 2), not supported"


def test_ho_does_not_answer(env, capsys, monkeypatch):
    monkeypatch.setattr(version, "HO_COMMAND", [sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setattr(version, "PROBE_TIMEOUT_S", 1)
    code, out, _ = run_flag(capsys)
    assert code == 0 and out.splitlines()[1] == "ho: needs contract 1; ho did not answer --version within 1 s"


def test_several_contracts_are_named(fake_ho):
    assert version.ho_line(supported=(1, 2)).startswith("ho: needs contract 1 or 2; found ho 0.2.0")


# ---- engine version (task 2.4)

def package_in(root: Path, pyproject: str | None) -> Path:
    pkg = root / "radark"
    pkg.mkdir(parents=True)
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return pkg


def installed(monkeypatch, value):
    def fake(name):
        assert name == "radark-factory"
        if value is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return value
    monkeypatch.setattr(importlib.metadata, "version", fake)


def test_installed_release(tmp_path, monkeypatch):
    installed(monkeypatch, "0.6.0")
    assert version.engine_version(package_in(tmp_path, None)) == "0.6.0"


def test_source_checkout(tmp_path, monkeypatch):
    installed(monkeypatch, "0.4.0")
    pkg = package_in(tmp_path, '[project]\nname = "radark-factory"\nversion = "0.6.0"\n')
    assert version.engine_version(pkg) == "0.6.0 (source checkout)"


@pytest.mark.parametrize("text", ['[project]\nname = "other"\nversion = "9.9.9"\n', "not toml = = =\n",
                                  'project = "x"\n', '[project]\nname = "radark-factory"\n'])
def test_other_pyproject_is_ignored(tmp_path, monkeypatch, text):
    installed(monkeypatch, "0.6.0")
    assert version.engine_version(package_in(tmp_path, text)) == "0.6.0"


def test_unknown(tmp_path, monkeypatch):
    installed(monkeypatch, None)
    assert version.engine_version(package_in(tmp_path, None)) == "unknown"


def test_this_checkout():
    assert version.engine_version().endswith(" (source checkout)")


# ---- deprecated alias (task 2.5)

def test_harness_alias(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PATH=str(tmp_path))  # no ho on PATH: no real hub call
    env.pop("HO_HUB", None)

    def run(module):
        return subprocess.run([sys.executable, "-m", module, "--version"], capture_output=True, text=True, env=env,
                              cwd=tmp_path, timeout=60)

    radark, harness = run("radark"), run("harness")
    assert radark.returncode == harness.returncode == 0
    assert harness.stdout == radark.stdout and radark.stdout.splitlines()[1].endswith("no ho found on PATH")
    assert radark.stderr == ""
    assert len(harness.stderr.strip().splitlines()) == 1 and "deprecated" in harness.stderr
