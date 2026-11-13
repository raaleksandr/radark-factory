"""PreToolUse guard for routine denials (fewer-owner-waits D1-D5), on Bash, PowerShell, Write and Edit.

It recognises three kinds of routine commands and either allows a narrow, safe form or denies with a reason that
names the allowed way:

- discarding working-tree edits: `git restore` / `git checkout --` of named files inside the team repository is
  allowed; a broad form (`.`, a directory, a wildcard, pathspec magic, a path outside the repository, `--source`) is
  denied;
- stopping processes: by ID, when every ID descends from the session's own Claude Code process, is allowed; by name
  or image, or a process outside that tree, is denied;
- temporary files: a write to the system temporary directory is denied; the session temp directory is the place.

Anything else prints nothing, so the permission mode decides exactly as before. An allow is given only for a single
simple command (no `;`, `&&`, `||`, `|`, `&`, newline, backtick, `$(`, redirection), so it covers exactly the
narrow form; a compound command can only be denied."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import hookcommon as hc

DISCARD_REASON = (
    "Discarding edits is allowed only for named files of this repository: run `git restore -- <file> [<file>…]` "
    "(one command, nothing else on the line), or re-write each file with the edit tool. Whole-tree or "
    "out-of-repository discards stay denied."
)
STOP_REASON = (
    "Stop only processes this session started, by their ID: `Stop-Process -Id <pid>` (or `taskkill /PID <pid> /T /F`) "
    "is allowed for processes started in this session. Better: start servers as background tasks and stop them with "
    "the task tool. Processes by name or not started by this session stay denied."
)


def temp_reason(temp_dir: str) -> str:
    return (f"Temporary files go to `{temp_dir}` (it is also `$TEMP`/`$TMP` in this session); write them there.")


SHELLS = ("Bash", "PowerShell")
NOT_SIMPLE = re.compile(r";|&|\||\n|\r|`|\$\(|>|<")
SEGMENT_SPLIT = re.compile(r";|&&|\|\||\||&|\n|\r")
PROCESS_TABLE_TIMEOUT = 15
PS_KEYS = ("-id", "-name", "-processname", "-inputobject")


# ---- paths

def _norm(path: str) -> str:
    """Comparable form of a path: forward slashes, no trailing slash, case-folded on Windows."""
    text = str(path).replace("\\", "/").rstrip("/")
    return text.lower() if os.name == "nt" else text


def _msys(path: str) -> str | None:
    """`C:\\Temp` as Git Bash writes it: `/c/Temp`."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else None


def _inside(path: str, root: str) -> bool:
    p, r = _norm(path), _norm(root)
    return bool(r) and (p == r or p.startswith(r + "/"))


def _resolve(path: str, cwd: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    try:
        return str(p.resolve())
    except OSError:
        return os.path.abspath(str(p))


def system_temps(env: dict) -> list[str]:
    """The original temp directories, `/tmp`, and their Git Bash forms, except one inside the session temp dir or the
    repository. The callers exempt the session temp dir and the repository themselves (they may lie under one)."""
    found = [t for t in (env.get("HARNESS_SYSTEM_TEMP") or "").split(os.pathsep) if t.strip()]
    keep = []
    for t in found:
        if any(x and _inside(t, x) for x in (env.get("HARNESS_TEMP"), env.get("HARNESS_REPO"))):
            continue
        keep.append(t)
    keep += [m for m in (_msys(t) for t in keep) if m]
    return list(dict.fromkeys(keep + ["/tmp"]))


# ---- rules

def temp_rule(tool: str, tool_input: dict, cwd: str, env: dict) -> tuple[str, str] | None:
    session_temp = env.get("HARNESS_TEMP")
    if not session_temp:
        return None
    temps = system_temps(env)
    if tool in ("Write", "Edit"):
        path = tool_input.get("file_path")
        if not isinstance(path, str) or not path.strip():
            return None
        forms = {_resolve(path, cwd), os.path.abspath(os.path.join(cwd, path)), path}

        def under(root: str | None) -> bool:  # raw and resolved forms (symlinks, Windows short names)
            return bool(root) and any(_inside(f, r) for f in forms for r in {root, _resolve(root, cwd)})

        if under(session_temp) or under(env.get("HARNESS_REPO")):
            return None
        if any(under(t) for t in temps):
            return "deny", temp_reason(session_temp)
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    text = _norm(command)
    repo = env.get("HARNESS_REPO") or ""
    owned = sorted({x for x in (session_temp, _msys(session_temp), repo, _msys(repo)) if x}, key=len, reverse=True)
    for own in owned:  # the session temp dir and the repository may lie under the system temp dir
        text = text.replace(_norm(own), " ")
    for t in temps:
        if re.search(r"(?:^|[\s'\"=(,])" + re.escape(_norm(t)) + r"(?=$|[/\s'\"),;|&>])", text):
            return "deny", temp_reason(session_temp)
    return None


def simple(command: str) -> bool:
    return not NOT_SIMPLE.search(command.strip())


def tokens(segment: str) -> list[str] | None:
    try:
        parts = shlex.split(segment, posix=False)
    except ValueError:
        return None
    return [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "'\"" else p for p in parts]


def discard_rule(argv: list[str], cwd: str, env: dict) -> str | None:
    """'allow', 'deny' or None for one tokenized command."""
    if len(argv) < 2 or argv[0].lower() not in ("git", "git.exe"):
        return None
    sub, rest = argv[1], argv[2:]
    paths: list[str] = []
    if sub == "restore":
        dashdash = False
        for a in rest:
            if dashdash or not a.startswith("-"):
                paths.append(a)
            elif a == "--":
                dashdash = True
            elif a in ("--worktree", "-W", "--staged", "-S"):
                continue
            elif a in ("-s", "--source") or a.startswith("--source=") or (a.startswith("-s") and len(a) > 2):
                return "deny"
            else:
                return None  # another option (`-p`, `--ours`, ...): left to the permission mode
    elif sub == "checkout":
        if rest == ["."]:
            return "deny"
        if not rest or rest[0] != "--":
            return None
        paths = rest[1:]
    else:
        return None
    if not paths:
        return None
    repo = env.get("HARNESS_REPO")
    unknown = False
    for p in paths:
        if any(c in p for c in "*?[") or p.startswith(":") or p.strip() in (".", "./", ".\\", ""):
            return "deny"
        if not repo:
            unknown = True
            continue
        full = _resolve(p, cwd)
        if not _inside(full, repo) or _norm(full) == _norm(repo):
            return "deny"
        if os.path.isdir(full):
            return "deny"
        if not os.path.isfile(full):
            unknown = True  # e.g. a deleted file: not allowed by the hook, left to the permission mode
    return None if unknown else "allow"


def stop_targets(argv: list[str]) -> tuple[list[str], bool] | None:
    """(IDs, by name or unverifiable) of a recognised stop command, or None."""
    name = argv[0].lower() if argv else ""
    args = argv[1:]
    ids: list[str] = []
    other = False
    if name == "kill" and any(a.lower().partition(":")[0] in PS_KEYS for a in args):
        name = "stop-process"  # PowerShell's `kill` alias with named parameters
    if name in ("stop-process", "spps"):
        def collect(value: str) -> None:
            ids.extend(x for x in value.split(",") if x)

        i = 0
        while i < len(args):
            a = args[i]
            key, _, inline = a.lower().partition(":") if a.startswith("-") else ("", "", "")
            if key == "-id":
                value = a.split(":", 1)[1] if inline else (args[i + 1] if i + 1 < len(args) else "")
                i += 0 if inline else 1
                collect(value)
                while value.endswith(",") and i + 1 < len(args):  # `-Id 1, 2`
                    i += 1
                    value = args[i]
                    collect(value)
            elif key in ("-name", "-processname", "-inputobject"):
                other = True
                i += 0 if inline else 1
            elif not key:
                collect(a)
            # other switches: -Force, -PassThru, -Confirm:$false, -WhatIf
            i += 1
        if not ids:
            other = True  # piped input or nothing named: not verifiable
    elif name in ("taskkill", "taskkill.exe"):
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("/pid", "-pid") and i + 1 < len(args):
                ids.append(args[i + 1])
                i += 1
            elif low in ("/im", "-im", "/fi", "-fi"):
                other = True
                i += 1
            i += 1
        if not ids:
            other = True
    elif name == "kill":
        signal, rest_ids, i = False, False, 0
        while i < len(args):
            a = args[i]
            if a in ("-l", "-L") or a.startswith("%"):
                return None  # listing signals, or a job of the shell itself
            if not rest_ids and a in ("-s", "-n"):
                signal, i = True, i + 2
                continue
            if not rest_ids and a == "--":
                rest_ids = True
            elif a.startswith("-") and not rest_ids and not signal and not ids:
                signal = True  # `-9`, `-TERM`
            elif a.startswith("-"):
                other = True  # a negative ID: a process group
            else:
                ids.append(a)
            i += 1
        if not ids and not other:
            return None
    elif name in ("pkill", "killall"):
        other = True
    else:
        return None
    return ids, other


def stop_rule(argv: list[str], table_fn=None, root: int | None = None) -> str | None:
    found = stop_targets(argv)
    if found is None:
        return None
    ids, other = found
    if other or not ids or not all(x.isdigit() for x in ids):
        return "deny"
    try:
        table = (table_fn or process_table)()
    except Exception:
        table = None
    if not table:
        return "deny"
    own = session_tree(table, root)
    return "allow" if all(int(x) in own for x in ids) else "deny"


# ---- the process tree (fewer-owner-waits D4)

def process_table() -> dict[int, dict]:
    """{pid: {"ppid", "name", "created"}} of every process; one PowerShell call on Windows, `ps` elsewhere."""
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,"
                  "@{n='Created';e={if ($_.CreationDate) { $_.CreationDate.ToFileTimeUtc() } else { 0 }}} | "
                  "ConvertTo-Json -Compress")
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, timeout=PROCESS_TABLE_TIMEOUT)
        rows = json.loads(p.stdout.decode("utf-8", errors="replace") or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return {int(r["ProcessId"]): {"ppid": int(r.get("ParentProcessId") or 0), "name": str(r.get("Name") or ""),
                                      "created": int(r.get("Created") or 0)} for r in rows}
    p = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, timeout=PROCESS_TABLE_TIMEOUT)
    table = {}
    for line in p.stdout.decode("utf-8", errors="replace").splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = {"ppid": int(parts[1]), "name": parts[2] if len(parts) > 2 else "", "created": 0}
    return table


def _is_python(name: str) -> bool:
    low = os.path.basename(name or "").lower()
    return low.startswith("python") or low in ("py", "py.exe")


def session_root(table: dict[int, dict], start: int) -> int:
    """The session's Claude Code process: the hook's parent, above a Python launcher (a virtual environment's
    `python.exe` on Windows starts the real interpreter as its child)."""
    pid, seen = start, set()
    while pid in table and _is_python(table[pid]["name"]) and pid not in seen:
        seen.add(pid)
        parent = table[pid]["ppid"]
        if parent not in table:
            break
        pid = parent
    return pid


def session_tree(table: dict[int, dict], root: int | None = None) -> set[int]:
    """IDs of the processes descended from the session root, without the root and the hook's own chain upward.
    A child created before its parent is a reused parent ID, not a descendant."""
    root = session_root(table, os.getppid()) if root is None else root
    children: dict[int, list[int]] = {}
    for pid, info in table.items():
        if pid != info["ppid"]:
            children.setdefault(info["ppid"], []).append(pid)
    tree, todo = set(), [root]
    while todo:
        parent = todo.pop()
        for child in children.get(parent, []):
            created, parent_created = table[child].get("created") or 0, (table.get(parent) or {}).get("created") or 0
            if child in tree or child == root or (created and parent_created and created < parent_created):
                continue
            tree.add(child)
            todo.append(child)
    chain, pid = set(), os.getpid()
    while pid and pid not in chain:  # the hook itself and everything above it
        chain.add(pid)
        pid = (table.get(pid) or {}).get("ppid") or 0
    return tree - chain - {root}


# ---- the decision

def shell_rule(command: str, cwd: str, env: dict, table_fn=None, root: int | None = None) -> tuple[str, str] | None:
    if simple(command):
        argv = tokens(command.strip())
        if not argv:
            return None
        for rule, reason in ((lambda a: discard_rule(a, cwd, env), DISCARD_REASON),
                             (lambda a: stop_rule(a, table_fn, root), STOP_REASON)):
            verdict = rule(argv)
            if verdict:
                return verdict, reason
        return None
    for segment in SEGMENT_SPLIT.split(command):  # a compound command: deny rules only, never an allow
        argv = tokens(segment.strip())
        if not argv:
            continue
        if discard_rule(argv, cwd, env) == "deny":
            return "deny", DISCARD_REASON
        found = stop_targets(argv)
        if found is not None:
            ids, other = found
            if other or not ids or not all(x.isdigit() for x in ids):
                return "deny", STOP_REASON
    return None


def decide(data: dict, env: dict, table_fn=None, root: int | None = None) -> tuple[str, str, str] | None:
    """(decision, reason, rule) or None when the permission mode should decide as before."""
    tool = data.get("tool_name")
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    cwd = data.get("cwd") or os.getcwd()
    if tool not in SHELLS + ("Write", "Edit"):
        return None
    found = temp_rule(tool, tool_input, cwd, env)
    if found:
        return found[0], found[1], "temp"
    if tool in SHELLS and isinstance(tool_input.get("command"), str):
        found = shell_rule(tool_input["command"], cwd, env, table_fn, root)
        if found:
            return found[0], found[1], "discard" if found[1] == DISCARD_REASON else "stop"
    return None


def main() -> None:
    data = hc.read_input()
    e = hc.env()
    try:
        found = decide(data, dict(os.environ))
    except Exception as exc:  # a guard failure must never block a tool call: the permission mode decides
        sys.stderr.write(f"guard: {exc}\n")
        return
    if not found:
        return
    decision, reason, rule = found
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    hc.write_marker(e, "guard", decision=decision, rule=rule, tool=data.get("tool_name"),
                    input=str(tool_input.get("command") or tool_input.get("file_path") or "")[:200])
    hc.emit(hc.pre_tool_decision(decision, reason))


if __name__ == "__main__":
    main()
