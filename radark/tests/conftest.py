import json
import sys
from pathlib import Path

import pytest

from radark import config as config_mod

FAKES = Path(__file__).resolve().parent / "fakes"
TEAMS = [("product", "product"), ("app", "technical"), ("backend", "technical")]


def toml_path(p) -> str:
    return "'" + str(p) + "'"


def write_config(root: Path, extra: str = "", triage: bool = True, teams=TEAMS) -> Path:
    hub = root / "hub"
    hub.mkdir(exist_ok=True)
    (hub / "hub.json").write_text(json.dumps({"schema_version": 1, "teams": [{"id": t, "name": t} for t, _ in teams]
                                                   + [{"id": "owner", "name": "Owner (human)"}]}))
    lines = [
        f"hub = {toml_path(hub)}",
        'run_dir = "run"',
        f"ho = [{toml_path(sys.executable)}, {toml_path(FAKES / 'fake_ho.py')}]",
        f"claude = [{toml_path(sys.executable)}, {toml_path(FAKES / 'fake_claude.py')}]",
    ]
    for tid, kind in teams:
        repo = root / "repos" / tid
        (repo / "openspec" / "changes").mkdir(parents=True, exist_ok=True)
        lines += ["[[teams]]", f'id = "{tid}"', f"repo = {toml_path(repo)}", f'kind = "{kind}"']
    if triage:
        lines += ["[triage]", 'team = "product"', 'teams = ["app", "backend"]', "max_per_handover = 3"]
    lines += ["[loop]", "poll_seconds = 0", "no_progress_limit = 2"]
    path = root / "harness.toml"
    path.write_text("\n".join(lines) + "\n" + extra, encoding="utf-8")
    return path


class Env:
    def __init__(self, root: Path, monkeypatch):
        self.root = root
        self.ho_data = root / "ho.json"
        self.scenarios = root / "claude.json"
        self.ho_data.write_text("{}")
        self.scenarios.write_text("[]")
        monkeypatch.setenv("FAKE_HO_DATA", str(self.ho_data))
        monkeypatch.setenv("FAKE_CLAUDE_SCENARIOS", str(self.scenarios))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-reach-claude")
        monkeypatch.setattr(sys, "stdout", sys.stdout)  # `run` tees the console to console.log; undo it after the test
        monkeypatch.setattr(sys, "stderr", sys.stderr)
        self.config_path = write_config(root)

    def cfg(self):
        return config_mod.load(self.config_path)

    def set_hub(self, data: dict):
        self.ho_data.write_text(json.dumps(data))

    def set_claude(self, scenarios: list):
        self.scenarios.write_text(json.dumps(scenarios))
        Path(str(self.scenarios) + ".n").unlink(missing_ok=True)

    def claude_calls(self) -> list[dict]:
        p = Path(str(self.scenarios) + ".calls")
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def ho_calls(self) -> list[dict]:
        p = Path(str(self.ho_data) + ".calls")
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def item(hid, title="Task", sender="product", my_state="pending", expects="done", last="2026-10-16T10:00:00.000Z"):
    return {"id": hid, "title": title, "from": sender, "expects": expects, "my_state": my_state,
            "priority": "normal", "due": None, "last_activity": last, "created": last}


def show(hid, events=(), status="open", created="2026-10-16T09:00:00.000Z", title="Task"):
    """events: (at, team, action, body[, target]) tuples."""
    out = []
    for e in events:
        at, team, action, body, target = (tuple(e) + (None,))[:5]
        out.append({"at": at, "team": team, "action": action, "body": body, **({"target": target} if target else {})})
    return {"id": hid, "title": title, "status": status, "created": created, "body": "Do the thing.", "events": out}


START = {"hook": "SessionStart", "input": {"source": "startup"}}
QUESTION = [{"question": "Use a Map or a plain object for the cache?", "header": "Cache",
             "options": [{"label": "Map"}, {"label": "Object"}]}]
ASK_STEP = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion", "tool_input": {"questions": QUESTION}}}


def stop_step(message, active=False):
    return {"hook": "Stop", "input": {"stop_hook_active": active, "last_assistant_message": message}}


def usage_step(status="allowed", **windows):
    """A `rate_limit_event` in a fake session: usage_step(five_hour=(0.57, resets_at), seven_day=(0.34, ...))."""
    return {"usage": {w: list(v) for w, v in windows.items()}, "status": status}


def goal_verdict(status, reason="r", done=(), left=()):
    """A goal-check session result with a structured verdict (goal-run)."""
    return {"structured_output": {"status": status, "reason": reason, "done": list(done), "left": list(left)}}


def hand_over(to="app", title="Next goal item"):
    """A fake session step: the product team hands over one item (`ho new`)."""
    return {"ho": ["new", "--to", to, "--title", title, "--expects", "done", "-m", "Do it."]}
