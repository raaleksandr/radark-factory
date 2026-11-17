"""Claude Code login state in the start summary (claude-login-state, tasks 2.2-2.5) with the fake `claude`."""
import json
from pathlib import Path

import pytest

from radark import config as config_mod
from radark.__main__ import main
from radark.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
LATER = "2099-01-01T00:00:00.000Z"
TASK = {"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A, [(LATER, "app", "ack", "")])}
LOGGED_IN = "logged in"
NOT_LOGGED_IN = "NOT logged in - run `claude` and log in (sessions would fail)"
NOT_AVAILABLE = "login state unknown (`claude auth status` not available)"
TIMED_OUT = "login state unknown (`claude auth status` timed out)"
UNREADABLE = "login state unknown (`claude auth status` gave no readable answer)"
EMAIL, ORG = "someone@example.invalid", "Example Org Zebra"  # the fake's made-up account fields


def auth_calls(env) -> list[dict]:
    p = Path(str(env.scenarios) + ".auth")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def sessions(env) -> list[dict]:
    return [c for c in env.claude_calls() if c["argv"] != ["--version"]]


def claude_line(out: str) -> str:
    return next(x for x in out.splitlines() if x.startswith("Claude Code:"))


# ---- probe (task 2.2)

@pytest.mark.parametrize("mode,expected", [("in", LOGGED_IN), ("out", NOT_LOGGED_IN), ("missing", NOT_AVAILABLE),
                                           ("garbage", UNREADABLE)])
def test_probe_states(env, monkeypatch, mode, expected):
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", mode)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-should-never-reach-claude")
    assert config_mod.claude_login(env.cfg()) == expected
    call, = auth_calls(env)
    assert call == {"argv": ["auth", "status", "--json"], "ANTHROPIC_API_KEY": None, "ANTHROPIC_AUTH_TOKEN": None}
    assert env.claude_calls() == []  # no session-like call recorded


def test_probe_timeout(env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", "sleep")
    monkeypatch.setattr(config_mod, "CLAUDE_LOGIN_TIMEOUT", 1)
    assert config_mod.claude_login(env.cfg()) == TIMED_OUT


def test_claude_not_found(env):
    cfg = env.cfg()
    cfg.claude = [str(env.root / "no-such-claude.exe")]
    assert config_mod.claude_login(cfg) == NOT_AVAILABLE


def test_summary_without_login_is_unchanged(env):
    cfg = env.cfg()
    assert "Claude Code: 1.0\n" in config_mod.summary(cfg, "1.0") + "\n"
    assert "Claude Code: 1.0; logged in" in config_mod.summary(cfg, "1.0", login=LOGGED_IN)


# ---- dry-run (task 2.3)

@pytest.mark.parametrize("mode,expected", [("in", LOGGED_IN), ("out", NOT_LOGGED_IN), ("missing", NOT_AVAILABLE),
                                           ("sleep", TIMED_OUT)])
def test_dry_run_line_and_exit_code(env, monkeypatch, capsys, mode, expected):
    env.set_hub(TASK)
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", mode)
    monkeypatch.setattr(config_mod, "CLAUDE_LOGIN_TIMEOUT", 1)
    assert main(["--config", str(env.config_path), "dry-run"]) == 0  # the same code in every login state
    out = capsys.readouterr().out
    assert claude_line(out) == f"Claude Code: 9.9.9 (Fake Claude); {expected}"
    assert "Would start: app" in out
    assert sessions(env) == []
    assert len(auth_calls(env)) == 1


# ---- once goes on (task 2.4) and privacy (task 2.5)

def test_once_not_logged_in_still_runs_the_session(env, monkeypatch, capsys):
    env.set_hub(TASK)
    env.set_claude([{"steps": [START, {"text": "CHANGE: add-export"}], "result": {"result": "CHANGE: add-export"}}])
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", "out")
    assert main(["--config", str(env.config_path), "once"]) == 0
    assert len(sessions(env)) == 1
    assert len(auth_calls(env)) == 1
    log = (env.root / "run" / "console.log").read_text(encoding="utf-8")
    assert f"Claude Code: 9.9.9 (Fake Claude); {NOT_LOGGED_IN}" in log.splitlines()


def test_run_once_probes_once(env, monkeypatch):
    """The probe sits before the loop in `main`, so a start probes once however many sessions follow."""
    env.set_hub(TASK)
    step = {"steps": [START, {"text": "CHANGE: add-export"}], "result": {"result": "CHANGE: add-export"}}
    env.set_claude([step])
    assert main(["--config", str(env.config_path), "run", "--once"]) == 0
    assert len(sessions(env)) == 1
    assert len(auth_calls(env)) == 1


def test_account_details_stay_private(env, capsys):
    env.set_hub(TASK)
    env.set_claude([{"steps": [START, {"text": "CHANGE: add-export"}], "result": {"result": "CHANGE: add-export"}}])
    assert main(["--config", str(env.config_path), "once"]) == 0
    out, err = capsys.readouterr()
    assert claude_line(out).endswith("; logged in")
    texts = [out, err] + [p.read_text(encoding="utf-8", errors="replace")
                          for p in (env.root / "run").rglob("*") if p.is_file()]
    for text in texts:
        assert EMAIL not in text and ORG not in text
