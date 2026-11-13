"""Load and validate harness.toml (spec: Configuration)."""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .awake import DEFAULT as KEEP_AWAKE_DEFAULT, KeepAwake, parse_keep_awake

DEFAULT_ANSWER = (
    "No user is available. Choose the best variant yourself, record the assumption "
    "in the change's design/tasks notes, and continue."
)
DEFAULT_KEYWORDS = ["push", "deploy", "payment", "delete", "secret", "production",
                    # agents often ask in Russian; word stems, matched at a word start (design E9)
                    "пуш", "запуш", "депло", "задепло", "выкат", "развертыв", "развернуть", "оплат", "платеж",
                    "заплат", "удал", "секрет", "парол", "продакш", "боев"]
KINDS = ("technical", "product")


class ConfigError(Exception):
    pass


@dataclass
class Team:
    id: str
    repo: Path
    kind: str


@dataclass
class Triage:
    team: str
    teams: list[str]
    max_per_handover: int = 3


@dataclass
class Config:
    path: Path
    hub: Path
    teams: list[Team]
    run_dir: Path
    ho: list[str]
    claude: list[str]
    permission_mode: str = "auto"
    extra_args: list[str] = field(default_factory=list)
    default_answer: str = DEFAULT_ANSWER
    escalation_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    triage: Triage | None = None
    poll_seconds: int = 120
    session_idle_minutes: float = 20  # no stream event for this long ends the session (design T1)
    session_max_minutes: float = 180  # cap even for an active session; a checkpoint for a work session (T2, D8)
    limit_check_minutes: float = 60  # extension when the limit check finds the session progressing (D7)
    limit_checks: int = 3  # limit checks per session; 0 turns them off (D7)
    wrap_up_minutes: float = 15  # grace for a wrap-up at the last time limit; 0 turns it off (wrap-up W7)
    wake_grace_minutes: float = 3  # after a wake, a silent session is ended as interrupted (sleep-aware D3)
    no_progress_limit: int = 2
    usage_backoff_minutes: int = 30
    usage_backoff_max_minutes: int = 300
    usage_pause_percent: int = 90  # no new step while a window is used at or above this share (usage-limit-guard)
    idle_ask: bool = False
    keep_awake: KeepAwake = KEEP_AWAKE_DEFAULT  # default of `--keep-awake`: off, on or a daily range (keep-awake D2);
    # without `[loop] keep_awake` the whole run (keep-awake-by-default D1)
    owner_team: str = "owner"
    goal_max_sessions: int = 40  # safety limits of a goal run (goal-run design G1)
    goal_max_hours: float = 12

    def team(self, team_id: str) -> Team:
        for t in self.teams:
            if t.id == team_id:
                return t
        raise KeyError(team_id)

    def team_ids(self) -> list[str]:
        return [t.id for t in self.teams]


def _missing_hint(name: str) -> str:
    """For a missing `ho`: the contract this engine needs and what to do (ho-contract-check D3)."""
    if name != "ho":
        return ""
    from .hub import contracts_text
    needed = contracts_text()
    return (f". This radark-factory needs an ho with JSON contract {needed}: install radark-handover with that "
            "contract, or fix 'ho' in harness.toml")


def _command(value, name: str) -> list[str]:
    """A command is a string (looked up on PATH) or a list (used as given)."""
    if isinstance(value, str):
        found = shutil.which(value)
        if not found:
            raise ConfigError(f"'{value}' ({name}) was not found on PATH{_missing_hint(name)}")
        return [found]
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        if not (shutil.which(value[0]) or Path(value[0]).is_file()):
            raise ConfigError(f"'{value[0]}' ({name}) was not found{_missing_hint(name)}")
        return list(value)
    raise ConfigError(f"'{name}' must be a command name or a non-empty list of strings")


def _req(data: dict, key: str, where: str = ""):
    if key not in data or data[key] in ("", None):
        raise ConfigError(f"missing required value '{where}{key}'")
    return data[key]


def _keep_awake(value) -> KeepAwake:
    """`[loop] keep_awake`: a moment applies to one run only, so only `off`, `on` and a range (design D2)."""
    setting = parse_keep_awake(value, dt.datetime.now()) if isinstance(value, str) else None
    if setting is None or setting.mode == "until":
        raise ConfigError(f"loop.keep_awake must be off, on or HH:MM-HH:MM (local time), not {value!r}")
    return setting


def load(path: str | Path) -> Config:
    path = Path(path).resolve()
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    base = path.parent

    hub = Path(_req(data, "hub"))
    if not (hub / "hub.json").is_file():
        raise ConfigError(f"hub path has no hub.json: {hub}")

    raw_teams = _req(data, "teams")
    if not isinstance(raw_teams, list):
        raise ConfigError("'teams' must be a list of [[teams]] tables")
    teams = []
    for i, t in enumerate(raw_teams):
        tid = _req(t, "id", f"teams[{i}].")
        repo = Path(_req(t, "repo", f"teams[{i}]."))
        kind = _req(t, "kind", f"teams[{i}].")
        if kind not in KINDS:
            raise ConfigError(f"team '{tid}': kind must be one of {', '.join(KINDS)}, not '{kind}'")
        if not repo.is_dir():
            raise ConfigError(f"team '{tid}': repository path does not exist: {repo}")
        if any(x.id == tid for x in teams):
            raise ConfigError(f"team '{tid}' is listed twice")
        teams.append(Team(tid, repo, kind))

    launch = data.get("launch", {})
    answers = data.get("answers", {})
    loop = data.get("loop", {})
    goal = data.get("goal", {})
    cfg = Config(
        path=path,
        hub=hub,
        teams=teams,
        run_dir=(base / data.get("run_dir", ".harness")).resolve(),
        ho=_command(data.get("ho", "ho"), "ho"),
        claude=_command(data.get("claude", "claude"), "claude"),
        permission_mode=launch.get("permission_mode", "auto"),
        extra_args=list(launch.get("extra_args", [])),
        default_answer=answers.get("default", DEFAULT_ANSWER),
        escalation_keywords=[k.lower() for k in answers.get("escalation_keywords", DEFAULT_KEYWORDS)],
        poll_seconds=int(loop.get("poll_seconds", 120)),
        session_idle_minutes=float(loop.get("session_idle_minutes", 20)),
        # the former single `session_timeout_minutes` is accepted as the maximum (design T2)
        session_max_minutes=float(loop.get("session_max_minutes", loop.get("session_timeout_minutes", 180))),
        limit_check_minutes=float(loop.get("limit_check_minutes", 60)),
        limit_checks=loop.get("limit_checks", 3),
        wrap_up_minutes=float(loop.get("wrap_up_minutes", 15)),
        wake_grace_minutes=float(loop.get("wake_grace_minutes", 3)),
        no_progress_limit=int(loop.get("no_progress_limit", 2)),
        usage_backoff_minutes=int(loop.get("usage_backoff_minutes", 30)),
        usage_backoff_max_minutes=int(loop.get("usage_backoff_max_minutes", 300)),
        usage_pause_percent=loop.get("usage_pause_percent", 90),
        idle_ask=bool(loop.get("idle_ask", False)),
        keep_awake=_keep_awake(loop["keep_awake"]) if "keep_awake" in loop else KEEP_AWAKE_DEFAULT,
        owner_team=str(data.get("owner_team", "owner")),
        goal_max_sessions=int(goal.get("max_sessions", 40)),
        goal_max_hours=float(goal.get("max_hours", 12)),
    )
    if cfg.owner_team in cfg.team_ids():
        raise ConfigError(f"owner_team '{cfg.owner_team}' is the human owner and must not be listed in [[teams]]")
    if cfg.session_idle_minutes <= 0 or cfg.session_max_minutes <= 0:
        raise ConfigError("loop.session_idle_minutes and loop.session_max_minutes must be positive")
    if cfg.limit_check_minutes <= 0:
        raise ConfigError("loop.limit_check_minutes must be positive")
    n = cfg.limit_checks
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ConfigError(f"loop.limit_checks must be an integer of 0 or more, not {n!r}")
    if cfg.wrap_up_minutes < 0:
        raise ConfigError("loop.wrap_up_minutes must be 0 or more (0 turns the wrap-up off)")
    if cfg.wake_grace_minutes <= 0:
        raise ConfigError("loop.wake_grace_minutes must be positive")
    if cfg.goal_max_sessions <= 0 or cfg.goal_max_hours <= 0:
        raise ConfigError("goal.max_sessions and goal.max_hours must be positive")
    pct = cfg.usage_pause_percent
    if isinstance(pct, bool) or not isinstance(pct, int) or not 1 <= pct <= 100:
        raise ConfigError(f"loop.usage_pause_percent must be an integer from 1 to 100, not {pct!r}")
    if cfg.permission_mode == "bypassPermissions":
        raise ConfigError("launch.permission_mode 'bypassPermissions' is not allowed")
    if "--bare" in cfg.extra_args:
        raise ConfigError("launch.extra_args must not contain --bare (it skips the repository settings and login)")

    tri = data.get("triage")
    if tri:
        triage = Triage(
            team=_req(tri, "team", "triage."),
            teams=list(tri.get("teams", cfg.team_ids())),  # default: every team, the product team included
            max_per_handover=int(tri.get("max_per_handover", 3)),
        )
        for tid in [triage.team, *triage.teams]:
            if tid not in cfg.team_ids():
                raise ConfigError(f"triage: team '{tid}' is not configured in [[teams]]")
        if cfg.team(triage.team).kind != "product":
            raise ConfigError(f"triage: team '{triage.team}' must be a product team")
        cfg.triage = triage
    return cfg


def check_owner(cfg: Config, hub_teams: list[str]) -> None:
    """The owner must be a hub team (added to hub.json by hand), or escalation handovers cannot be sent."""
    if cfg.owner_team not in hub_teams:
        raise ConfigError(f"owner_team '{cfg.owner_team}' is not a team of the hub {cfg.hub} (`ho teams`); "
                          "add it to hub.json, run `ho validate` and `ho sync`")


def claude_version(cfg: Config) -> str:
    try:
        out = subprocess.run(cfg.claude + ["--version"], capture_output=True, text=True, timeout=60)
        return (out.stdout or out.stderr).strip() or f"unknown (exit {out.returncode})"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unknown ({exc})"


def summary(cfg: Config, version: str, ho: str | None = None) -> str:
    """`ho`: the `ho` version line text, e.g. `0.2.0 (contract 1)` (ho-contract-check D4)."""
    lines = [f"Hub: {cfg.hub}", "Teams (in priority order):"]
    for t in cfg.teams:
        lines.append(f"  {t.id:<22} {t.kind:<9} {t.repo}")
    if cfg.triage:
        lines.append(f"Triage: questions of {', '.join(cfg.triage.teams)} -> {cfg.triage.team}")
    lines.append(f"Owner (escalations): {cfg.owner_team}")
    lines.append(f"Claude Code: {version}")
    if ho:
        lines.append(f"ho: {ho}")
    lines.append(f"Run directory: {cfg.run_dir}")
    return "\n".join(lines)
