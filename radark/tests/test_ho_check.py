"""Start check of `ho --version --json` (ho-contract-check, tasks 1.1 and 2.1) with the fake `ho`."""
import json
import os
import sys

import pytest

from radark.__main__ import main
from radark.hub import HoVersion, check_ho, contracts_text
from radark.tests.conftest import item, show

A = "HO-20261016-aaaa"
TASK = {"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)}
OLD = {"exit": 1}
WRONG = {"schema_version": 2, "version": "0.9.0", "contract": 2}


def with_version(env, answer):
    env.set_hub({**TASK, "_version": answer})


def missing_ho(env):
    text = env.config_path.read_text(encoding="utf-8").splitlines()
    text = [f"ho = ['{env.root / 'no-such-ho.exe'}']" if line.startswith("ho = ") else line for line in text]
    env.config_path.write_text("\n".join(text) + "\n", encoding="utf-8")


# ---- probe (task 1.1)

def test_compatible_ho(env, monkeypatch):
    cfg = env.cfg()
    monkeypatch.setenv("HO_TEAM", "app")
    assert check_ho(cfg.ho, cfg.hub) == HoVersion("0.2.0", 1, ("hub-lock",))
    call, = env.ho_calls()
    assert call == {"args": ["--version"], "team": None, "hub": str(cfg.hub)}


def test_missing_ho(env):
    cfg = env.cfg()
    cmd = [str(env.root / "no-such-ho.exe")]
    message = check_ho(cmd, cfg.hub)
    assert isinstance(message, str) and message.startswith("ho not found: cannot start")
    assert cmd[0] in message and "JSON contract 1" in message and "harness.toml" in message


@pytest.mark.parametrize("answer,how", [({"exit": 2}, "exit 2"), ("ho 0.1.0", "no version in its answer"),
                                        ({"schema_version": 1}, "no version in its answer")])
def test_too_old_ho(env, answer, how):
    cfg = env.cfg()
    env.set_hub({"_version": answer})
    message = check_ho(cfg.ho, cfg.hub)
    assert isinstance(message, str) and f"has no --version ({how})" in message
    assert "Found: no version; needed: JSON contract 1" in message and "radark-handover" in message
    assert " ".join(cfg.ho) in message


def test_unsupported_contract(env):
    cfg = env.cfg()
    env.set_hub({"_version": WRONG})
    message = check_ho(cfg.ho, cfg.hub)
    assert isinstance(message, str)
    assert "is version 0.9.0 with JSON contract 2" in message and "needs contract 1" in message
    assert "radark-factory release that supports contract 2" in message


def test_schema_version_stands_in_for_a_missing_contract(env):
    cfg = env.cfg()
    env.set_hub({"_version": {"schema_version": 1, "version": "0.3.0"}})
    assert check_ho(cfg.ho, cfg.hub) == HoVersion("0.3.0", 1)


def test_several_supported_contracts(env):
    cfg = env.cfg()
    env.set_hub({"_version": WRONG})
    assert contracts_text((1, 2)) == "1 or 2"
    assert check_ho(cfg.ho, cfg.hub, supported=(1, 2)) == HoVersion("0.9.0", 2)  # no `features`: no hub lock
    env.set_hub({"_version": {"version": "1.0.0", "contract": 3}})
    assert "needs contract 1 or 2" in check_ho(cfg.ho, cfg.hub, supported=(1, 2))


def test_no_answer_in_time(env):
    cfg = env.cfg()
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    message = check_ho(slow, cfg.hub, timeout=1)
    assert isinstance(message, str) and "did not answer '--version --json' within 1 s" in message


# ---- start path (task 2.1)

def test_dry_run_prints_the_ho_line(env, capsys):
    env.set_hub(TASK)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert "ho: 0.2.0 (contract 1)" in lines
    assert lines.index("ho: 0.2.0 (contract 1)") == next(i for i, x in enumerate(lines) if x.startswith("Claude Code:")) + 1
    assert "Would start: app" in out
    assert env.ho_calls()[0]["args"] == ["--version"]


def stopped(env, capsys, argv, prefix="ho incompatible: "):
    capsys.readouterr()
    assert main(["--config", str(env.config_path)] + argv) == 2
    out, err = capsys.readouterr()
    assert err.startswith(prefix) and len(err.strip().splitlines()) == 1
    assert "Hub:" not in out  # no summary
    assert env.claude_calls() == []
    assert [c["args"] for c in env.ho_calls()] in ([], [["--version"]])
    run = env.root / "run"
    assert not (run / "lock").exists()
    log = run / "runs.jsonl"
    assert not log.exists() or "dispatcher_start" not in log.read_text(encoding="utf-8")
    return err


@pytest.mark.parametrize("argv", [["dry-run"], ["run", "--once"], ["once"], ["run"]])
@pytest.mark.parametrize("case", ["missing", "old", "wrong"])
def test_incompatible_ho_stops_before_anything(env, capsys, argv, case):
    if case == "missing":
        env.set_hub(TASK)
        missing_ho(env)
    else:
        with_version(env, OLD if case == "old" else WRONG)
    # a command that does not exist is already found by the configuration check, with the same hint
    err = stopped(env, capsys, argv, "Configuration error: " if case == "missing" else "ho incompatible: ")
    expected = {"missing": "no-such-ho.exe' (ho) was not found. This radark-factory needs an ho with JSON contract 1", "old": "has no --version (exit 1)",
                "wrong": "is version 0.9.0 with JSON contract 2"}[case]
    assert expected in err and "contract 1" in err


def test_plan_checks_too(env, capsys):
    with_version(env, WRONG)
    err = stopped(env, capsys, ["plan"])
    assert "is version 0.9.0 with JSON contract 2" in err


def test_plan_with_compatible_ho(env, capsys):
    env.set_hub(TASK)
    assert main(["--config", str(env.config_path), "plan"]) == 0
    assert "ho: " not in capsys.readouterr().out  # plan prints no summary (design D4)


@pytest.mark.parametrize("argv", [["escalations"], ["clear", A], ["keep", A, "--team", "app"]])
def test_local_commands_skip_the_check(env, capsys, argv):
    with_version(env, WRONG)
    assert main(["--config", str(env.config_path)] + argv) in (0, 1)
    assert env.ho_calls() == []


# ---- hub lock for parallel sessions (parallel-sessions task 4.1)

NO_LOCK = {"schema_version": 1, "version": "0.2.0", "contract": 1}
LOCK = {**NO_LOCK, "features": ["hub-lock"]}


def sessions(env, n):
    env.config_path.write_text(env.config_path.read_text() + f"parallel_sessions = {n}\n")


def test_hub_lock_signal(env):
    cfg = env.cfg()
    env.set_hub({"_version": LOCK})
    assert check_ho(cfg.ho, cfg.hub).hub_lock
    env.set_hub({"_version": NO_LOCK})
    assert not check_ho(cfg.ho, cfg.hub).hub_lock
    env.set_hub({"_version": {**NO_LOCK, "features": "hub-lock"}})  # not a list: ignored
    assert not check_ho(cfg.ho, cfg.hub).hub_lock


@pytest.mark.parametrize("argv", [["dry-run"], ["once"], ["run"]])
def test_two_sessions_without_the_hub_lock_stop(env, capsys, argv):
    sessions(env, 2)
    with_version(env, NO_LOCK)
    err = stopped(env, capsys, argv)
    assert "ho 0.2.0 (contract 1) does not report the hub lock" in err
    assert "parallel_sessions = 2" in err and "radark-handover" in err and "parallel_sessions = 1" in err


def test_two_sessions_with_the_hub_lock_start(env, capsys):
    sessions(env, 2)
    with_version(env, LOCK)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert "Would start: app" in capsys.readouterr().out


def test_one_session_needs_no_lock(env, capsys):
    with_version(env, NO_LOCK)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert "Would start: app" in capsys.readouterr().out


def test_plan_needs_no_lock(env, capsys):
    sessions(env, 2)
    with_version(env, NO_LOCK)
    assert main(["--config", str(env.config_path), "plan"]) == 0
    assert "Plan (if every step succeeds):" in capsys.readouterr().out
