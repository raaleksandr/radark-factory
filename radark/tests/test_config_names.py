"""Configuration file and run directory names: radark.toml / .radark/ with a fallback to the legacy harness.toml /
.harness/ (change radark-config-names, design D1-D5)."""
import json
import os
import re

import pytest

from radark import config as config_mod
from radark.__main__ import main
from radark.machine import Machine
from radark.tests.conftest import START, item, show, write_config

A = "HO-20261114-aaaa"


def legacy_names(root, drop_run_dir=True):
    """Turn the fixture's radark.toml (explicit `run_dir = "run"`) into a harness.toml, by default without `run_dir`."""
    new = root / "radark.toml"
    text = new.read_text(encoding="utf-8")
    if drop_run_dir:
        text = text.replace('run_dir = "run"\n', "")
    old = root / "harness.toml"
    old.write_text(text, encoding="utf-8")
    new.unlink()
    return old


def without_run_dir(path):
    path.write_text(path.read_text(encoding="utf-8").replace('run_dir = "run"\n', ""), encoding="utf-8")
    return path


def with_task(env):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})


# ---- configuration file (D1)

def test_new_names_only(tmp_path):
    without_run_dir(write_config(tmp_path))
    path, note = config_mod.resolve_path(None, tmp_path)
    assert path == tmp_path / "radark.toml" and note is None
    cfg = config_mod.load(path, note)
    assert cfg.run_dir == (tmp_path / ".radark").resolve() and cfg.notes == ()
    assert "Legacy name" not in config_mod.summary(cfg, "x")


def test_old_names_only_fall_back_with_both_notes(tmp_path):
    write_config(tmp_path)
    legacy_names(tmp_path)
    (tmp_path / ".harness").mkdir()
    path, note = config_mod.resolve_path(None, tmp_path)
    assert path == tmp_path / "harness.toml" and note == config_mod.LEGACY_CONFIG_NOTE
    cfg = config_mod.load(path, note)
    assert cfg.run_dir == (tmp_path / ".harness").resolve()
    assert cfg.notes == (config_mod.LEGACY_CONFIG_NOTE, config_mod.LEGACY_RUN_DIR_NOTE)
    assert "rename it to radark.toml" in cfg.notes[0] and "rename it to .radark/" in cfg.notes[1]
    assert config_mod.summary(cfg, "x").splitlines()[:2] == list(cfg.notes)
    assert (tmp_path / "harness.toml").is_file() and (tmp_path / ".harness").is_dir()  # nothing migrated
    assert not (tmp_path / "radark.toml").exists() and not (tmp_path / ".radark").exists()


def test_both_configuration_files_are_an_error(tmp_path):
    write_config(tmp_path)
    (tmp_path / "harness.toml").write_text((tmp_path / "radark.toml").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(config_mod.ConfigError) as exc:
        config_mod.resolve_path(None, tmp_path)
    assert str(tmp_path / "radark.toml") in str(exc.value) and str(tmp_path / "harness.toml") in str(exc.value)


def test_explicit_old_configuration_file_has_no_note(tmp_path):
    write_config(tmp_path)
    old = legacy_names(tmp_path, drop_run_dir=False)
    path, note = config_mod.resolve_path("harness.toml", tmp_path)
    assert path == old and note is None
    assert config_mod.load(path, note).notes == ()


def test_explicit_path_is_used_whatever_its_name(tmp_path):
    other = tmp_path / "pipeline.toml"
    write_config(tmp_path).rename(other)
    (tmp_path / "harness.toml").write_text("not read", encoding="utf-8")
    assert config_mod.resolve_path(str(other), tmp_path) == (other, None)


def test_no_configuration_file(tmp_path):
    with pytest.raises(config_mod.ConfigError, match=r"radark\.toml \(no legacy harness\.toml either\)") as exc:
        config_mod.resolve_path(None, tmp_path)
    assert str(tmp_path / "radark.toml") in str(exc.value)


# ---- run directory (D2)

def test_both_run_directories_are_an_error(tmp_path):
    path = without_run_dir(write_config(tmp_path))
    (tmp_path / ".radark").mkdir()
    (tmp_path / ".harness").mkdir()
    with pytest.raises(config_mod.ConfigError) as exc:
        config_mod.load(path)
    assert str(tmp_path / ".radark") in str(exc.value) and str(tmp_path / ".harness") in str(exc.value)


def test_stray_file_counts_as_existing(tmp_path):
    path = without_run_dir(write_config(tmp_path))
    (tmp_path / ".radark").write_text("", encoding="utf-8")
    (tmp_path / ".harness").mkdir()
    with pytest.raises(config_mod.ConfigError, match="both"):
        config_mod.load(path)


def test_explicit_old_run_directory_has_no_note(tmp_path):
    path = write_config(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('run_dir = "run"', 'run_dir = ".harness"'),
                    encoding="utf-8")
    (tmp_path / ".radark").mkdir()  # an explicit run_dir wins even when both exist
    (tmp_path / ".harness").mkdir()
    cfg = config_mod.load(path)
    assert cfg.run_dir == (tmp_path / ".harness").resolve() and cfg.notes == ()


def test_new_run_directory_wins_when_only_it_exists(tmp_path):
    path = without_run_dir(write_config(tmp_path))
    (tmp_path / ".radark").mkdir()
    cfg = config_mod.load(path)
    assert cfg.run_dir == (tmp_path / ".radark").resolve() and cfg.notes == ()


def test_ho_message_names_the_file_read(tmp_path):
    path = write_config(tmp_path)
    path.write_text(re.sub(r"(?m)^ho = .*$", 'ho = "no-such-ho-command-xyz"', path.read_text(encoding="utf-8")),
                    encoding="utf-8")
    old = legacy_names(tmp_path, drop_run_dir=False)
    with pytest.raises(config_mod.ConfigError, match=r"fix 'ho' in harness\.toml"):
        config_mod.load(old)


# ---- CLI (D1, D3)

def test_both_files_stop_the_cli_before_ho_and_any_session(env, capsys, monkeypatch):
    with_task(env)
    (env.root / "harness.toml").write_text(env.config_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(env.root)
    for argv in (["once"], ["run"], ["dry-run"], ["plan"], ["escalations"]):
        assert main(argv) == 2
        err = capsys.readouterr().err
        assert err.startswith("Configuration error: both") and "radark.toml" in err and "harness.toml" in err
    assert env.ho_calls() == [] and env.claude_calls() == []
    assert not (env.root / "run").exists()


def test_both_run_directories_stop_the_cli(env, capsys, monkeypatch):
    with_task(env)
    without_run_dir(env.config_path)
    (env.root / ".radark").mkdir()
    (env.root / ".harness").mkdir()
    monkeypatch.chdir(env.root)
    assert main(["once"]) == 2
    assert "Configuration error: run_dir is not set and both" in capsys.readouterr().err
    assert env.ho_calls() == [] and env.claude_calls() == []


def test_old_names_only_dry_run_and_plan_show_the_legacy_lines(env, capsys, monkeypatch):
    with_task(env)
    legacy_names(env.root)
    (env.root / ".harness").mkdir()
    monkeypatch.chdir(env.root)
    for argv in (["dry-run"], ["plan"]):
        assert main(argv) == 0
        out = capsys.readouterr().out
        assert out.count(config_mod.LEGACY_CONFIG_NOTE) == 1 and out.count(config_mod.LEGACY_RUN_DIR_NOTE) == 1
    assert env.claude_calls() == []
    assert (env.root / "harness.toml").is_file() and not (env.root / "radark.toml").exists()
    assert not (env.root / ".radark").exists()


def test_once_with_old_names_keeps_them(env, capsys, monkeypatch):
    with_task(env)
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    legacy_names(env.root)
    (env.root / ".harness").mkdir()
    monkeypatch.chdir(env.root)
    assert main(["once"]) == 0
    out = capsys.readouterr().out
    assert config_mod.LEGACY_CONFIG_NOTE in out and config_mod.LEGACY_RUN_DIR_NOTE in out
    assert (env.root / ".harness" / "runs.jsonl").is_file() and not (env.root / ".radark").exists()
    assert (env.root / "harness.toml").is_file() and not (env.root / "radark.toml").exists()


def test_default_run_directory_reaches_the_session(env, monkeypatch):
    """Prompts and the session temp directory use the resolved run directory (`.radark` by default)."""
    with_task(env)
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    without_run_dir(env.config_path)
    monkeypatch.chdir(env.root)
    assert main(["once"]) == 0
    call, = env.claude_calls()
    argv = call["argv"]
    temp = str((env.root / ".radark" / "tmp" / "app").resolve())
    system = argv[argv.index("--append-system-prompt") + 1]
    assert f"temporary files go to `{temp}`" in system
    assert ".harness" not in json.dumps(argv)


def test_status_reports_ambiguity_without_failing(env, capsys, monkeypatch):
    (env.root / "harness.toml").write_text(env.config_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(env.root)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "not read (both" in out and "repository conflicts are not checked" in out


# ---- machine-wide layer (D5): no record format change

def test_old_name_record_is_another_pipeline(machine_home, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    old = Machine(machine_home, tmp_path / "harness.toml")
    old.enter()
    assert old.claim_repos([repo]) is None
    new = Machine(machine_home, tmp_path / "radark.toml")
    conflict, = new.repo_conflicts([repo])
    assert conflict[1]["config"] == os.fspath(tmp_path / "harness.toml")
    same = Machine(machine_home, tmp_path / "harness.toml")
    assert same.repo_conflicts([repo]) == []  # the same resolved path: the same pipeline
    old.close()
