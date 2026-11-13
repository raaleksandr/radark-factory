import json
import shutil

import pytest

from radark import config as config_mod
from radark.tests.conftest import write_config


def test_valid_config(env):
    cfg = env.cfg()
    assert [t.id for t in cfg.teams] == ["product", "app", "backend"]
    assert cfg.team("app").kind == "technical"
    assert cfg.triage.team == "product" and cfg.triage.teams == ["app", "backend"]
    assert cfg.run_dir == (env.root / "run").resolve()
    assert cfg.permission_mode == "auto"
    text = config_mod.summary(cfg, config_mod.claude_version(cfg))
    assert "9.9.9 (Fake Claude)" in text and str(cfg.hub) in text and "app" in text


def test_triage_defaults_to_every_team(tmp_path):
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace('teams = ["app", "backend"]\n', ""))
    assert config_mod.load(p).triage.teams == ["product", "app", "backend"]


def test_missing_repo_names_team_and_path(env):
    shutil.rmtree(env.root / "repos" / "backend")
    with pytest.raises(config_mod.ConfigError, match=r"team 'backend'.*does not exist"):
        env.cfg()


def test_missing_required_value(tmp_path):
    p = tmp_path / "h.toml"
    p.write_text('run_dir = "x"\n')
    with pytest.raises(config_mod.ConfigError, match="missing required value 'hub'"):
        config_mod.load(p)


def test_missing_file(tmp_path):
    with pytest.raises(config_mod.ConfigError, match="not found"):
        config_mod.load(tmp_path / "nope.toml")


def test_command_not_on_path(tmp_path):
    p = write_config(tmp_path)
    text = p.read_text().splitlines()
    text = [ln if not ln.startswith("claude =") else 'claude = "definitely-not-claude-xyz"' for ln in text]
    p.write_text("\n".join(text))
    with pytest.raises(config_mod.ConfigError, match="definitely-not-claude-xyz"):
        config_mod.load(p)


def test_bad_kind_and_bypass_refused(tmp_path):
    p = write_config(tmp_path, extra='[launch]\npermission_mode = "bypassPermissions"\n')
    with pytest.raises(config_mod.ConfigError, match="bypassPermissions"):
        config_mod.load(p)
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace('kind = "product"', 'kind = "manager"'))
    with pytest.raises(config_mod.ConfigError, match="kind must be"):
        config_mod.load(p)


def test_triage_team_must_be_configured(tmp_path):
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace('teams = ["app", "backend"]', 'teams = ["app", "games"]'))
    with pytest.raises(config_mod.ConfigError, match="'games' is not configured"):
        config_mod.load(p)


def test_cli_exits_nonzero_on_broken_config(env, capsys):
    from radark.__main__ import main
    shutil.rmtree(env.root / "repos" / "app")
    assert main(["--config", str(env.config_path), "dry-run"]) == 2
    err = capsys.readouterr().err
    assert "app" in err and "does not exist" in err
    assert env.claude_calls() == []


def test_owner_team_default_and_check(env):
    cfg = env.cfg()
    assert cfg.owner_team == "owner"
    config_mod.check_owner(cfg, ["app", "owner"])
    with pytest.raises(config_mod.ConfigError, match="'owner' is not a team of the hub"):
        config_mod.check_owner(cfg, ["app"])


def test_owner_team_must_not_be_a_dispatcher_team(tmp_path):
    p = write_config(tmp_path, extra="")
    p.write_text('owner_team = "backend"\n' + p.read_text())
    with pytest.raises(config_mod.ConfigError, match="must not be listed"):
        config_mod.load(p)


def test_cli_refuses_to_start_without_owner_team(env, capsys):
    from radark.__main__ import main
    hub_json = env.cfg().hub / "hub.json"
    data = json.loads(hub_json.read_text())
    data["teams"] = [t for t in data["teams"] if t["id"] != "owner"]
    hub_json.write_text(json.dumps(data))
    assert main(["--config", str(env.config_path), "dry-run"]) == 2
    assert "owner" in capsys.readouterr().err
    assert main(["--config", str(env.config_path), "escalations"]) == 0  # the manual path still works


def test_session_limits_default_and_old_timeout_key(tmp_path):
    cfg = config_mod.load(write_config(tmp_path))
    assert (cfg.session_idle_minutes, cfg.session_max_minutes) == (20, 180)
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nsession_max_minutes = 360"))
    assert config_mod.load(p).session_max_minutes == 360
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nsession_timeout_minutes = 240"))
    cfg = config_mod.load(p)
    assert (cfg.session_idle_minutes, cfg.session_max_minutes) == (20, 240)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nsession_max_minutes = 300\nsession_idle_minutes = 5"))
    cfg = config_mod.load(p)  # the new key wins over the alias
    assert (cfg.session_idle_minutes, cfg.session_max_minutes) == (5, 300)


def test_usage_pause_percent(tmp_path, env, capsys):
    root = tmp_path / "other"
    root.mkdir()
    assert config_mod.load(write_config(root)).usage_pause_percent == 90
    p = write_config(root)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nusage_pause_percent = 80"))
    assert config_mod.load(p).usage_pause_percent == 80
    for bad in ("0", "101", "90.5", '"90"'):
        p = write_config(root)
        p.write_text(p.read_text().replace("[loop]", f"[loop]\nusage_pause_percent = {bad}"))
        with pytest.raises(config_mod.ConfigError, match="usage_pause_percent"):
            config_mod.load(p)
    from radark.__main__ import main
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\nusage_pause_percent = 0"))
    assert main(["--config", str(env.config_path), "dry-run"]) == 2
    assert "usage_pause_percent" in capsys.readouterr().err


def test_goal_limits_default_and_override(tmp_path):
    cfg = config_mod.load(write_config(tmp_path))
    assert (cfg.goal_max_sessions, cfg.goal_max_hours) == (40, 12)
    p = write_config(tmp_path, extra="[goal]\nmax_sessions = 5\nmax_hours = 1.5\n")
    cfg = config_mod.load(p)
    assert (cfg.goal_max_sessions, cfg.goal_max_hours) == (5, 1.5)
    p = write_config(tmp_path, extra="[goal]\nmax_sessions = 0\n")
    with pytest.raises(config_mod.ConfigError, match="goal.max_sessions"):
        config_mod.load(p)


def test_wake_grace_default_and_zero_refused(tmp_path):
    assert config_mod.load(write_config(tmp_path)).wake_grace_minutes == 3
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nwake_grace_minutes = 0.5"))
    assert config_mod.load(p).wake_grace_minutes == 0.5
    p.write_text(p.read_text().replace("wake_grace_minutes = 0.5", "wake_grace_minutes = 0"))
    with pytest.raises(config_mod.ConfigError, match="wake_grace_minutes"):
        config_mod.load(p)


def test_limit_check_defaults_and_values(tmp_path):
    cfg = config_mod.load(write_config(tmp_path))
    assert (cfg.limit_check_minutes, cfg.limit_checks) == (60, 3)
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nlimit_check_minutes = 30\nlimit_checks = 0"))
    cfg = config_mod.load(p)
    assert (cfg.limit_check_minutes, cfg.limit_checks) == (30, 0)


def test_wrap_up_minutes_default_value_and_zero(tmp_path):
    assert config_mod.load(write_config(tmp_path)).wrap_up_minutes == 15
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[loop]", "[loop]\nwrap_up_minutes = 7.5"))
    assert config_mod.load(p).wrap_up_minutes == 7.5
    p.write_text(p.read_text().replace("wrap_up_minutes = 7.5", "wrap_up_minutes = 0"))
    assert config_mod.load(p).wrap_up_minutes == 0


@pytest.mark.parametrize("line,key", [("limit_check_minutes = 0", "limit_check_minutes"),
                                      ("limit_check_minutes = -5", "limit_check_minutes"),
                                      ("limit_checks = -1", "limit_checks"), ("limit_checks = 1.5", "limit_checks"),
                                      ("limit_checks = true", "limit_checks"),
                                      ("wrap_up_minutes = -1", "loop.wrap_up_minutes")])
def test_invalid_limit_check_settings_refused(env, capsys, line, key):
    from radark.__main__ import main
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", f"[loop]\n{line}"))
    with pytest.raises(config_mod.ConfigError, match=key):
        config_mod.load(env.config_path)
    assert main(["--config", str(env.config_path), "dry-run"]) == 2
    assert key in capsys.readouterr().err
