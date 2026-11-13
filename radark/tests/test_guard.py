"""The guard hook for routine denials (change fewer-owner-waits, task 3.3): narrow forms are allowed, broad forms are
denied with a reason naming the allowed way, everything else is left to the permission mode."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))
import guard  # noqa: E402  (a plain script module, imported like the hooks import hookcommon)


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repos" / "app"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "cache.py").write_text("x = 1\n")
    (repo / "README.md").write_text("hi\n")
    temp = tmp_path / "run" / "tmp" / "app"
    temp.mkdir(parents=True)
    system = tmp_path / "systemp"
    system.mkdir()
    env = {"HARNESS_REPO": str(repo), "HARNESS_TEMP": str(temp), "HARNESS_SYSTEM_TEMP": str(system),
           "HARNESS_RUN_DIR": str(tmp_path / "run"), "HARNESS_RUN_ID": "run-1", "HARNESS_SESSION": "sess-1",
           "HARNESS_TEAM": "app", "HARNESS_HANDOVER": "HO-20261016-ab12", "HARNESS_PHASE": "apply"}
    return {"repo": repo, "temp": temp, "system": system, "env": env, "run": tmp_path / "run"}


def shell(command, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command}}


def decide(s, data, table=None, root=None):
    data = {"cwd": str(s["repo"]), **data}
    return guard.decide(data, s["env"], table_fn=table, root=root)


def tree(*pairs):
    """A fake process table: (pid, ppid) pairs."""
    return lambda: {pid: {"ppid": ppid, "name": "x", "created": 0} for pid, ppid in pairs}


TABLE = tree((100, 1), (200, 100), (300, 200), (400, 1), (os.getpid(), 100))


# ---- discarding working-tree edits

@pytest.mark.parametrize("command", [
    "git restore -- src/cache.py",
    "git restore src/cache.py",
    "git restore --staged --worktree -- src/cache.py README.md",
    'git restore -- "src/cache.py"',
    "git checkout -- src/cache.py",
])
def test_named_file_discard_is_allowed(setup, command):
    decision, reason, rule = decide(setup, shell(command))
    assert (decision, rule) == ("allow", "discard")


@pytest.mark.parametrize("command", [
    "git checkout -- .",
    "git checkout .",
    "git restore .",
    "git restore -- src",
    "git restore ../x",
    "git restore '*.py'",
    "git restore -- :/src/cache.py",
    "git restore --source HEAD~1 src/cache.py",
    "git restore -s HEAD src/cache.py",
])
def test_broad_discard_is_denied_with_the_allowed_way(setup, command):
    decision, reason, rule = decide(setup, shell(command))
    assert (decision, rule) == ("deny", "discard")
    assert "git restore -- <file>" in reason and "re-write each file" in reason


def test_discard_outside_the_repository_by_absolute_path(setup):
    other = setup["repo"].parent / "backend"
    other.mkdir()
    (other / "api.py").write_text("")
    assert decide(setup, shell(f"git restore {other / 'api.py'}"))[0] == "deny"


@pytest.mark.parametrize("command", [
    "git push origin main",
    "git status",
    "git restore -- src/cache.py; git push",
    "git restore -- src/cache.py && git push",
    "git restore -p src/cache.py",
    "git restore -- src/missing.py",
    "git checkout main",
    "git reset --hard",
    "ls -la",
])
def test_other_commands_are_left_to_the_permission_mode(setup, command):
    assert decide(setup, shell(command)) is None


def test_broad_discard_inside_a_compound_command_is_denied(setup):
    assert decide(setup, shell("git status; git checkout -- ."))[:2] == ("deny", guard.DISCARD_REASON)


# ---- stopping processes

def test_own_process_by_id_is_allowed(setup):
    for command, tool in (("Stop-Process -Id 300", "PowerShell"), ("Stop-Process -Id 200,300 -Force", "PowerShell"),
                          ("taskkill /PID 300 /T /F", "Bash"), ("kill -9 300", "Bash"), ("kill 200 300", "Bash")):
        assert decide(setup, shell(command, tool), TABLE, root=100)[:1] == ("allow",), command


@pytest.mark.parametrize("command", [
    "Stop-Process -Name node",
    "taskkill /IM node.exe /F",
    "taskkill /PID 400 /F",
    "Stop-Process -Id 400",
    "Stop-Process -Id 100",
    f"Stop-Process -Id {os.getpid()}",
    "kill 999999",
    "pkill node",
    "killall node",
    "Stop-Process -Id $serverPid",
    "Get-Process node | Stop-Process -Force",
])
def test_foreign_or_named_process_is_denied_with_the_allowed_way(setup, command):
    decision, reason, rule = decide(setup, shell(command, "PowerShell"), TABLE, root=100)
    assert (decision, rule) == ("deny", "stop")
    assert "Stop-Process -Id <pid>" in reason and "task tool" in reason


def test_stop_without_a_process_table_is_denied(setup):
    def broken():
        raise OSError("no table")
    assert decide(setup, shell("Stop-Process -Id 300", "PowerShell"), broken, root=100)[0] == "deny"


def test_compound_stop_is_never_allowed(setup):
    assert decide(setup, shell("Stop-Process -Id 300; git push", "PowerShell"), TABLE, root=100) is None


def test_reused_parent_id_is_not_a_descendant():
    table = {100: {"ppid": 1, "name": "claude", "created": 50},
             200: {"ppid": 100, "name": "x", "created": 10}}  # created before its "parent": a reused ID
    assert guard.session_tree(table, root=100) == set()


def test_python_launcher_is_skipped_to_find_the_session_root():
    table = {10: {"ppid": 1, "name": "claude.exe", "created": 0},
             11: {"ppid": 10, "name": "python.exe", "created": 0},
             12: {"ppid": 11, "name": "python.exe", "created": 0}}
    assert guard.session_root(table, 11) == 10


def test_real_child_of_the_hooks_parent_is_allowed(setup):
    """The real hook script and the real process table: a process started by the hook's parent (this test) may be
    stopped by ID; the test process itself (the hook's parent) may not."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        out = run_hook(setup, shell(f"Stop-Process -Id {child.pid}", "PowerShell"))
        assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
        out = run_hook(setup, shell(f"Stop-Process -Id {os.getpid()}", "PowerShell"))
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        child.kill()
        child.wait()


# ---- temporary files

def test_write_to_system_temp_is_denied_with_the_session_temp_dir(setup):
    decision, reason, rule = decide(setup, {"tool_name": "Write",
                                            "tool_input": {"file_path": str(setup["system"] / "check.ps1")}})
    assert (decision, rule) == ("deny", "temp") and str(setup["temp"]) in reason


def test_powershell_writing_to_system_temp_is_denied(setup):
    command = f'Set-Content -Path "{setup["system"]}\\check.ps1" -Value "x"'
    decision, reason, rule = decide(setup, shell(command, "PowerShell"))
    assert (decision, rule) == ("deny", "temp") and str(setup["temp"]) in reason


def test_bash_writing_to_slash_tmp_is_denied(setup):
    assert decide(setup, shell("echo x > /tmp/check.sh"))[2] == "temp"


@pytest.mark.parametrize("target", ["temp", "repo"])
def test_writes_to_session_temp_or_repository_are_not_decided(setup, target):
    path = setup[target] / "check.ps1"
    assert decide(setup, {"tool_name": "Write", "tool_input": {"file_path": str(path)}}) is None
    assert decide(setup, {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}) is None
    assert decide(setup, shell(f'Set-Content -Path "{path}" -Value x', "PowerShell")) is None


def test_session_temp_under_the_system_temp_is_not_decided(setup):
    nested = setup["system"] / "run" / "tmp" / "app"
    nested.mkdir(parents=True)
    setup["env"]["HARNESS_TEMP"] = str(nested)
    assert decide(setup, {"tool_name": "Write", "tool_input": {"file_path": str(nested / "a.txt")}}) is None
    assert decide(setup, shell(f"cat {nested / 'a.txt'}")) is None
    assert decide(setup, {"tool_name": "Write",
                          "tool_input": {"file_path": str(setup["system"] / "b.txt")}})[2] == "temp"


def test_other_tools_are_not_decided(setup):
    assert decide(setup, {"tool_name": "Read", "tool_input": {"file_path": str(setup["system"] / "x")}}) is None


# ---- the script

def run_hook(s, payload):
    env = {**{k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "PATH", "WINDIR", "COMSPEC")},
           **s["env"]}
    p = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=json.dumps({"cwd": str(s["repo"]),
                                                                                    **payload}).encode(),
                       capture_output=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr.decode()
    text = p.stdout.decode().strip()
    return json.loads(text) if text else None


def test_script_denies_with_reason_and_writes_a_marker(setup):
    out = run_hook(setup, shell("git checkout -- ."))
    assert out == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": guard.DISCARD_REASON}}
    marker = json.loads((setup["run"] / "markers" / "run-1.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert (marker["event"], marker["decision"], marker["rule"]) == ("guard", "deny", "discard")


def test_script_prints_nothing_when_nothing_matches(setup):
    assert run_hook(setup, shell("git push origin main")) is None
    assert run_hook(setup, {"tool_name": "AskUserQuestion", "tool_input": {"questions": []}}) is None
    assert not (setup["run"] / "markers").exists()


def test_script_survives_unparsable_input(setup):
    p = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=b"not json", capture_output=True,
                       env={**os.environ, **setup["env"]}, timeout=60)
    assert p.returncode == 0 and p.stdout == b""
