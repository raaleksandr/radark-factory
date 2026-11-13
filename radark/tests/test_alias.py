"""Package name `radark` and the deprecated alias `harness` (change rename-harness-module-to-radark)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import radark
from radark import runner as runner_mod
from radark.tests.conftest import write_config

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(radark.__file__).resolve().parent
NOTE = "note: `python -m harness` is deprecated, use `python -m radark` (kept for at least one release)"


def run_module(name: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ if env is None else env)
    full_env["PYTHONPATH"] = str(ROOT) + os.pathsep + full_env.get("PYTHONPATH", "")
    full_env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m", name, *args], capture_output=True, text=True, encoding="utf-8",
                          env=full_env, cwd=ROOT, timeout=120)


def both(*args: str, env: dict | None = None):
    new, old = run_module("radark", *args, env=env), run_module("harness", *args, env=env)
    assert old.stdout == new.stdout
    assert old.returncode == new.returncode
    assert old.stderr.splitlines()[0] == NOTE
    assert old.stderr.splitlines()[1:] == new.stderr.splitlines()
    assert NOTE not in new.stderr
    return new, old


def test_help_same_via_both_names():
    new, _ = both("--help")
    assert new.returncode == 0
    assert new.stdout.startswith("usage: python -m radark")


def test_unknown_command_same_exit_code():
    new, _ = both("no-such-command")
    assert new.returncode != 0


def test_dry_run_same_via_both_names(tmp_path):
    config_path = write_config(tmp_path)
    ho_data, scenarios = tmp_path / "ho.json", tmp_path / "claude.json"
    ho_data.write_text("{}")
    scenarios.write_text("[]")
    env = dict(os.environ, FAKE_HO_DATA=str(ho_data), FAKE_CLAUDE_SCENARIOS=str(scenarios))
    new, _ = both("--config", str(config_path), "dry-run", env=env)
    assert new.returncode == 0
    assert new.stdout.strip()


def test_old_imports_give_radark_modules():
    import harness
    import harness.state
    import radark.state
    from harness.state import GoalRun
    assert harness.state is radark.state
    assert GoalRun is radark.state.GoalRun
    assert harness.__doc__ == radark.__doc__


def test_importing_alias_main_starts_nothing():
    # in a fresh interpreter: the import must neither print nor run the dispatcher
    code = ("import harness.__main__ as a, radark.__main__ as r; from harness.__main__ import main, Dispatcher; "
            "assert a is r and main is r.main and Dispatcher is r.Dispatcher; print('ok')")
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "ok\n" and done.stderr == ""


def test_hooks_and_sandbox_resolve_inside_radark_package(env):
    hooks = PACKAGE / "hooks"
    assert runner_mod.HOOKS_DIR == hooks
    settings = json.loads(runner_mod.write_session_settings(env.cfg()).read_text())
    scripts = [Path(h["args"][0]) for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    assert scripts and all(s.parent == hooks and s.is_file() for s in scripts)
    assert (PACKAGE / "sandbox" / "make_sandbox.py").is_file()
    assert PACKAGE.name == "radark"

