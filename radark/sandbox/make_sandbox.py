"""Create a throw-away sandbox for end-to-end checks (task 5.1, design D9).

    python radark/sandbox/make_sandbox.py <empty-or-new-dir> [--force]

Creates <dir>/hub (a hub made with `ho init`, same team ids as the real hub), two git repositories
<dir>/repos/app (technical) and <dir>/repos/product (product, with a tiny backlog),
each with a minimal CLAUDE.md, OpenSpec (`openspec init --tools claude`) and .claude/settings.json pointing
at the sandbox hub, and <dir>/harness.toml for the dispatcher. Never touches the real hub or teams."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

TEAMS = {
    "strategy": "Strategy (sandbox)",
    "app": "the product technical (sandbox)",
    "product": "the product product (sandbox)",
    "backend": "Backend (sandbox)",
    "games": "Games (sandbox)",
    "owner": "Owner - human (sandbox)",
}

TECH_CLAUDE = """# CLAUDE.md — app (SANDBOX)

This is a throw-away sandbox copy of a technical team, used to test the dispatcher. The code is a tiny
Python module, `greet.py`, with tests in `test_greet.py` (`python -m pytest -q`).

## Team workflow
- You are the technical team `app`. Other teams reach you only through the handover hub, with the
  `ho` CLI (`HO_HUB` and `HO_TEAM` are set in `.claude/settings.json`). Read the hub guide (`AGENTS.md`
  in the hub directory) before acting on a handover.
- Every task gets an OpenSpec change (`/opsx:propose`, then `/opsx:apply`, `/opsx:archive`), citing the
  handover ID in its proposal.
- Never push to a remote; this repository has none.
"""

PRODUCT_CLAUDE = """# CLAUDE.md — product (SANDBOX)

This is a throw-away sandbox copy of the product team, used to test the dispatcher. No product code here.

## Team workflow
- You are the product manager team `product`. You keep `backlog/BACKLOG.md` and hand tasks to
  the technical team `app` through the handover hub with the `ho` CLI (`HO_HUB` and `HO_TEAM` are
  set in `.claude/settings.json`; the hub guide is `AGENTS.md` in the hub directory).
- Routine work (reviewing results, closing or returning handovers) needs no OpenSpec change.
- Product goal: more weekly active users; the greeting is the first thing a new user sees.
"""

BACKLOG = """# Backlog

- BL-001 (next) — `greet(name)` should greet in a friendly way and handle an empty name. Small, no human needed.
- BL-002 — Show an onboarding tour on first install (needs design work).
- BL-003 — Pricing page (needs the owner).
"""

GREET = '''def greet(name):
    return "Hello " + name
'''

TEST_GREET = '''from greet import greet


def test_greet():
    assert greet("Ann").startswith("Hello")
'''


def run(cmd, cwd=None, check=True):
    exe = shutil.which(cmd[0]) or cmd[0]
    p = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise SystemExit(f"{' '.join(cmd)} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
    return p


def git_repo(path: Path) -> None:
    run(["git", "init", "-q", "-b", "main"], cwd=path)
    run(["git", "config", "user.email", "sandbox@example.invalid"], cwd=path)
    run(["git", "config", "user.name", "Sandbox"], cwd=path)
    run(["git", "add", "-A"], cwd=path)
    run(["git", "commit", "-q", "-m", "Sandbox initial state"], cwd=path)


def team_repo(root: Path, hub: Path, team: str, claude_md: str, files: dict[str, str]) -> Path:
    repo = root / "repos" / team
    repo.mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    run(["openspec", "init", "--tools", "claude", "--no-animation"], cwd=repo)
    settings = {
        "env": {"HO_HUB": str(hub), "HO_TEAM": team},
        "permissions": {"allow": ["Bash(ho:*)", "Bash(openspec:*)", "Bash(python -m pytest:*)", "Bash(git status:*)",
                                  "Bash(git diff:*)", "Bash(git log:*)"]},
    }
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    git_repo(repo)
    return repo


def toml_str(p: Path) -> str:
    return "'" + str(p) + "'"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--force", action="store_true", help="delete the directory first if it exists")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if root.exists() and any(root.iterdir()):
        if not args.force:
            raise SystemExit(f"{root} is not empty; pass --force to recreate it")
        if not (root / "SANDBOX").is_file():
            raise SystemExit(f"{root} was not made by this script (no SANDBOX marker); refusing to delete it")
        shutil.rmtree(root, onexc=lambda fn, path, exc: (os.chmod(path, stat.S_IWRITE), fn(path)))  # git objects are read-only
    root.mkdir(parents=True, exist_ok=True)
    (root / "SANDBOX").write_text("Throw-away dispatcher sandbox; safe to delete.\n")

    hub = root / "hub"
    run(["ho", "init", str(hub), "--teams", ",".join(f"{k}={v}" for k, v in TEAMS.items())])
    git_repo(hub)
    tech = team_repo(root, hub, "app", TECH_CLAUDE, {"greet.py": GREET, "test_greet.py": TEST_GREET})
    prod = team_repo(root, hub, "product", PRODUCT_CLAUDE, {"backlog/BACKLOG.md": BACKLOG})

    package_dir = Path(__file__).resolve().parents[1]
    config = f"""# Sandbox configuration written by {Path(__file__).name}
hub = {toml_str(hub)}
run_dir = "run"
ho = "ho"
claude = "claude"

[[teams]]
id = "product"
repo = {toml_str(prod)}
kind = "product"

[[teams]]
id = "app"
repo = {toml_str(tech)}
kind = "technical"

[triage]
team = "product"
max_per_handover = 3

[loop]
poll_seconds = 30
session_idle_minutes = 20
session_max_minutes = 30
"""
    (root / "harness.toml").write_text(config, encoding="utf-8")
    machine = root / "machine"  # a sandbox-local machine directory: never the real one (machine-wide-instances D1)
    machine.mkdir(exist_ok=True)
    (root / "machine-env.ps1").write_text(f"$env:RADARK_MACHINE_DIR = '{machine}'\n", encoding="utf-8")
    (root / "machine-env.sh").write_text(f"export RADARK_MACHINE_DIR='{machine}'\n", encoding="utf-8")
    print(f"Sandbox ready in {root}\n  hub: {hub}\n  repos: {tech}, {prod}\n"
          f"  machine directory: {machine}\n"
          f"    set it first: . {root / 'machine-env.ps1'}  (PowerShell)  or  . {root / 'machine-env.sh'}  (sh)\n"
          f"  run: python -m radark --config {root / 'harness.toml'} dry-run   (from {package_dir.parent})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
