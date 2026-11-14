"""Workflow profiles (workflow-profiles): the setting, the built-in `openspec` and `plain` profiles, prompt overrides,
user-defined profiles and their checks. Fake `ho` / `claude` only."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from radark import config as config_mod
from radark import forecast, prompts, workflow
from radark import select as sel
from radark.__main__ import Dispatcher, main
from radark.select import Candidate
from radark.tests.conftest import START, item, show

A = "HO-20261114-ab12"
LATER = "2099-01-01T00:00:00.000Z"
README = Path(__file__).resolve().parents[1] / "README.md"  # radark/README.md
FORBIDDEN = ("opsx", "OpenSpec", "tasks.md", "CHANGE:")


def cand(phase, team="backend", **kw):
    base = dict(kind="work", team=team, handover=A, title="Export", phase=phase, recency="", team_index=0)
    base.update(kw)
    return Candidate(**base)


def set_profile(env, team="backend", profile="plain", workflow_section=""):
    """Give `team` a `profile` in its [[teams]] entry, and add a [workflow] section."""
    text = env.config_path.read_text(encoding="utf-8")
    if profile:
        text = text.replace(f'id = "{team}"\n', f'id = "{team}"\nprofile = "{profile}"\n')
    env.config_path.write_text(text + ("\n[workflow]\n" + workflow_section + "\n" if workflow_section else ""),
                               encoding="utf-8")


def disp(env, out=None):
    return Dispatcher(env.cfg(), out=out or (lambda *a: None))


def log_events(env, kind=None):
    events = [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    return [e for e in events if kind is None or e["event"] == kind]


def git_init(repo):
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                ["commit", "-q", "--allow-empty", "-m", "start"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)


def committed(*writes, msg="work"):
    return [{"write": [path, text]} for path, text in writes] + [
        {"cmd": ["git", "add", "-A"]}, {"cmd": ["git", "commit", "-q", "-m", msg]}]


# ---- 1.2 profile model and templates

def test_every_builtin_loads_from_the_package():
    for name in workflow.BUILTINS:
        p = workflow.load_profile(name)
        assert set(p.templates) == set(workflow.required_templates(p.phases))
        assert all(src is None for src in p.sources.values())
    assert workflow.builtin("openspec").phases == ("propose", "apply", "archive")
    assert workflow.builtin("plain").phases == ("apply",)


def test_unknown_template_variable_is_refused(tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "apply.md").write_text("Do $handover in $HOME.\n", encoding="utf-8")
    with pytest.raises(workflow.ProfileError) as exc:
        workflow.load_profile("plain", tmp_path)
    assert "apply.md" in str(exc.value) and "$HOME" in str(exc.value)


def test_double_dollar_is_a_literal_dollar(tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "apply.md").write_text("Use $$HO_HUB for $handover.\n", encoding="utf-8")
    p = workflow.load_profile("plain", tmp_path)
    assert "Use $HO_HUB for HO-20261114-ab12." in prompts.phase_prompt(cand("apply"), profile=p)


def test_every_documented_variable_renders(tmp_path):
    (tmp_path / "plain").mkdir()
    text = " ".join(f"[{v}=${{{v}}}]" for v in workflow.VARIABLES)
    (tmp_path / "plain" / "apply.md").write_text(text, encoding="utf-8")
    p = workflow.load_profile("plain", tmp_path)
    out = prompts.phase_prompt(cand("apply", expects="done", change="x"), profile=p)
    assert "[handover=HO-20261114-ab12]" in out and "[team=backend]" in out and "[noun=task]" in out
    assert "$" not in out.split("\n\n")[1]


def test_readme_lists_exactly_the_template_variables():
    text = README.read_text(encoding="utf-8")
    section = text.split("### Template variables", 1)[1].split("\n#", 1)[0]
    names = re.findall(r"^\| `\$(\w+)`", section, re.M)
    assert sorted(names) == sorted(workflow.VARIABLES)


# ---- 3.1 configuration

def test_no_workflow_setting_means_openspec(env):
    cfg = env.cfg()
    assert {t.id: t.profile for t in cfg.teams} == {"product": "openspec", "app": "openspec", "backend": "openspec"}
    assert cfg.team_phases()["app"] == ("propose", "apply", "archive")


def test_pipeline_default_and_team_override(env):
    set_profile(env, team="app", profile="openspec", workflow_section='profile = "plain"')
    cfg = env.cfg()
    assert {t.id: t.profile for t in cfg.teams} == {"product": "plain", "app": "openspec", "backend": "plain"}


def test_unknown_profile_exits_2(env, capsys):
    set_profile(env, team="app", profile="kanban")
    with pytest.raises(config_mod.ConfigError) as exc:
        env.cfg()
    assert "'app'" in str(exc.value) and "kanban" in str(exc.value) and "openspec, plain" in str(exc.value)
    for cmd in ("dry-run", "run"):
        assert main(["--config", str(env.config_path), cmd]) == 2
    assert "kanban" in capsys.readouterr().err
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []


def test_explicit_missing_dir_exits_2(env):
    set_profile(env, profile=None, workflow_section='dir = "no-such-dir"')
    with pytest.raises(config_mod.ConfigError, match="profile directory does not exist"):
        env.cfg()
    assert main(["--config", str(env.config_path), "dry-run"]) == 2


def test_default_dir_may_be_absent(env):
    set_profile(env, profile=None, workflow_section='profile = "openspec"')
    assert env.cfg().workflow_dir is None


def test_unknown_workflow_key_is_refused(env):
    set_profile(env, profile=None, workflow_section='profiel = "plain"')
    with pytest.raises(config_mod.ConfigError, match="profiel"):
        env.cfg()


# ---- 3.2 dry-run shows the profile

def test_dry_run_shows_each_teams_profile(env, capsys):
    set_profile(env)
    env.set_hub({})
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^  app +technical openspec  ", out, re.M)
    assert re.search(r"^  backend +technical plain     ", out, re.M)
    assert "Workflow profiles:" not in out  # no profile directory in use


# ---- 2.2 wording

def test_plain_wording_names_no_openspec_change():
    body = prompts.escalation_body(team="backend", handover=A, reason="stalled", phase="apply", change="x",
                                   question=None, result_tail="", session=None, repo="r",
                                   label=workflow.builtin("plain").label)
    assert "OpenSpec" not in body and "phase apply" in body and A in body
    consult = prompts.consult_prompt({"q": 1}, "backend", A, "x", label=workflow.builtin("plain").label)
    assert "OpenSpec" not in consult


def test_goal_check_names_the_finished_work_of_the_profiles_in_use():
    plain, spec = workflow.builtin("plain"), workflow.builtin("openspec")
    assert workflow.finished_words([spec]) == "closed handovers, archived OpenSpec changes"
    assert workflow.finished_words([plain]) == "closed handovers"
    assert workflow.finished_words([plain, spec]) == "closed handovers, archived OpenSpec changes"
    text = prompts.goal_check_prompt("Goal.", finished=workflow.finished_words([plain]))
    assert "(closed handovers)." in text and "OpenSpec" not in text


# ---- 5.1 plain prompts

def test_plain_prompts_do_not_name_openspec():
    p = workflow.builtin("plain")
    texts = {
        "apply": prompts.phase_prompt(cand("apply"), profile=p),
        "returned": prompts.phase_prompt(cand("apply", return_comment="Add a header."), profile=p),
        "wrap-up": prompts.wrap_up_message(cand("apply"), 180, 1, 15, profile=p),
        "act": prompts.phase_prompt(cand("act", team="product", expects="response"), profile=p),
    }
    for name, text in texts.items():
        assert not [w for w in FORBIDDEN if w in text], name
    assert f"ho ack {A}" in texts["apply"] and "commit locally" in texts["apply"] and f"ho done {A}" in texts["apply"]
    assert "> Add a header." in texts["returned"] and "commit locally" in texts["returned"]
    assert f"ho done {A}" in texts["wrap-up"] and "Left: <what is left>" in texts["wrap-up"]
    assert "record the assumption in your commit message" in texts["apply"]
    assert "(response)" in texts["act"]


# ---- 5.2 phase sequence

def test_select_plain_new_handover_goes_to_apply():
    teams = [("app", "technical"), ("backend", "technical")]
    inboxes = {"app": {"action_required": [item("HO-1")]}, "backend": {"action_required": [item("HO-2")]}}
    phases = {"app": ("propose", "apply", "archive"), "backend": ("apply",)}
    got = {c.handover: c.phase for c in sel.candidates(teams, inboxes, {}, {}, None, phases)}
    assert got == {"HO-1": "propose", "HO-2": "apply"}


def test_select_closed_done_plain_record_is_no_archive_candidate():
    teams = [("app", "technical"), ("backend", "technical")]
    closed = show("HO-3", [("2026-10-16T11:00:00.000Z", "product", "close", "")], status="closed")
    rec = {"team": "backend", "phase": "done", "flags": {}, "sessions": []}
    assert sel.candidates(teams, {}, {"HO-3": closed}, {"HO-3": rec}, None, {"backend": ("apply",)}) == []
    assert [c.phase for c in sel.candidates(teams, {}, {"HO-3": closed}, {"HO-3": dict(rec, team="app")})] == [
        "archive"]


def test_prediction_for_plain_has_no_propose_or_archive():
    teams = [("product", "product"), ("backend", "technical")]
    inboxes = {"backend": {"action_required": [item(A)]}}
    shows = {A: dict(show(A), **{"from": "product", "to": ["backend"]})}
    f = forecast.simulate(teams, inboxes, shows, {}, None, 5, "2026-11-14T10:00:00.000Z",
                          phases={"product": ("apply",), "backend": ("apply",)})
    assert [(s.team, s.phase) for s in f.steps] == [("backend", "apply"), ("product", "review")]


def test_plain_handover_end_to_end(env):
    """New handover -> one apply session -> `ho done` -> the author closes -> finished without a session."""
    set_profile(env)
    env.set_hub({"inbox:backend": {"action_required": [item(A)]},
                 f"show:{A}": show(A, [(LATER, "backend", "ack", ""), (LATER, "backend", "done", "Done.")])})
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    lines = []
    d = disp(env, lines.append)
    d.loop(once=True)
    start = log_events(env, "session_start")[0]
    assert start["phase"] == "apply" and f"ho ack {A}" in start["prompt"]
    assert not [w for w in FORBIDDEN if w in start["prompt"]]
    rec = d.state.get(A)
    assert rec["phase"] == "done" and rec.get("change") is None and rec["no_progress"] == 0
    env.set_hub({f"show:{A}": show(A, [("2026-11-14T10:00:00.000Z", "backend", "done", "Done."),
                                        ("2026-11-14T11:00:00.000Z", "product", "close", "")], status="closed")})
    calls = len(env.claude_calls())
    d.loop(once=True)
    assert len(env.claude_calls()) == calls  # no archive session
    assert d.state.get(A)["phase"] == "archived"
    assert log_events(env, "closed_without_archive")[0]["profile"] == "plain"
    assert any("closed by the author; finished (profile plain has no archive phase)" in str(x) for x in lines)


def test_dry_run_reports_a_plain_item_it_would_finish(env, capsys):
    set_profile(env)
    env.set_hub({f"show:{A}": show(A, [("2026-11-14T11:00:00.000Z", "product", "close", "")], status="closed")})
    d = disp(env)
    d.state.ensure(A, "backend").update(phase="done")
    d.state.save()
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert f"Would finish: backend {A}" in capsys.readouterr().out
    assert disp(env).state.get(A)["phase"] == "done"  # a dry run changes nothing


# ---- 5.3 plain progress and loops

def test_plain_commit_without_ho_done_is_progress(env):
    set_profile(env)
    repo = env.root / "repos" / "backend"
    git_init(repo)
    env.set_hub({"inbox:backend": {"action_required": [item(A, my_state="acknowledged")]}, f"show:{A}": show(A)})
    d = disp(env)
    d.state.ensure(A, "backend").update(phase="apply", no_progress=1)
    d.state.save()
    env.set_claude([{"steps": [START, *committed(("src/a.py", "x = 1\n"))], "result": {"result": "Partly done."}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0
    assert log_events(env, "session_end")[0]["progress_sources"] == ["commits"]


def test_plain_sessions_without_progress_stall(env):
    set_profile(env)
    env.set_hub({"inbox:backend": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 1
    d.loop(once=True)
    assert d.state.get(A)["flags"]["stalled"]
    assert [e["phase"] for e in log_events(env, "session_start")] == ["apply", "apply"]
    body = [c for c in env.ho_calls() if c["args"][0] == "new"]
    assert body and "OpenSpec" not in json.dumps(body)


def test_plain_return_gives_one_apply_session_with_the_comment(env):
    set_profile(env)
    events = [("2026-11-14T10:00:00.000Z", "backend", "done", "Done."),
              ("2026-11-14T11:00:00.000Z", "product", "return", "Add a CSV header.", "backend")]
    env.set_hub({"inbox:backend": {"action_required": [item(A, my_state="returned")]}, f"show:{A}": show(A, events)})
    d = disp(env)
    d.state.ensure(A, "backend").update(phase="apply")
    d.state.save()
    env.set_claude([{"steps": [START], "result": {"result": "Fixed."}}])
    d.loop(once=True)
    start = log_events(env, "session_start")[0]
    assert start["phase"] == "apply" and "> Add a CSV header." in start["prompt"]
    assert not [w for w in FORBIDDEN if w in start["prompt"]]


# ---- 6.1 overrides

def test_override_of_a_single_plain_template(env, capsys):
    root = env.config_path.parent / "workflows" / "plain"
    root.mkdir(parents=True)
    (root / "apply.md").write_text("${hub_sync}Custom apply for $handover. $closing\n", encoding="utf-8")
    set_profile(env)
    cfg = env.cfg()
    p = cfg.profile_of("backend")
    text = prompts.phase_prompt(cand("apply"), profile=p)
    assert f"Custom apply for {A}. When the work is finished" in text
    assert prompts.phase_prompt(cand("review", kind="review"), profile=p) == prompts.phase_prompt(
        cand("review", kind="review"), profile=workflow.builtin("plain"))
    env.set_hub({})
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    assert "overrides: plain/apply.md" in capsys.readouterr().out


def test_profile_toml_in_a_builtin_override_dir_is_refused(env):
    root = env.config_path.parent / "workflows" / "plain"
    root.mkdir(parents=True)
    (root / "profile.toml").write_text('phases = ["apply"]\n', encoding="utf-8")
    set_profile(env)
    with pytest.raises(config_mod.ConfigError, match="profile.toml"):
        env.cfg()


def test_unknown_template_file_is_refused(env):
    root = env.config_path.parent / "workflows" / "plain"
    root.mkdir(parents=True)
    (root / "aply.md").write_text("x\n", encoding="utf-8")
    set_profile(env)
    with pytest.raises(config_mod.ConfigError, match="aply"):
        env.cfg()


# ---- 6.2 user-defined profiles

SPEC_KIT = '''phases = ["propose", "apply", "archive"]
noun = "spec"
finished_words = "archived specs"
based_on = "openspec"
artifact_dir = "specs/{name}"

[closing]
propose = "End your final message with one line `CHANGE: <name>` naming the spec you created."
'''


def spec_kit(env, toml=SPEC_KIT, files=None):
    root = env.config_path.parent / "workflows" / "spec-kit"
    root.mkdir(parents=True)
    (root / "profile.toml").write_text(toml, encoding="utf-8")
    for name, text in (files or {"propose.md": "${hub_sync}Write a spec for $handover in specs/. $closing\n"}).items():
        (root / name).write_text(text, encoding="utf-8")
    set_profile(env, team="app", profile="spec-kit")


def test_user_profile_with_an_artifact_dir(env):
    spec_kit(env)
    repo = env.root / "repos" / "app"
    git_init(repo)
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START, *committed(("specs/add-x/spec.md", f"# Spec\n\nFor {A}.\n"))],
                     "result": {"result": "Specified."}}])
    d = disp(env)
    d.loop(once=True)
    start = log_events(env, "session_start")[0]
    assert start["phase"] == "propose" and f"Write a spec for {A}" in start["prompt"]
    assert d.state.get(A)["change"] == "add-x"  # found by its citation, no CHANGE line
    p = d.profile("app")
    assert p.change_ref("add-x", A) == "the spec `add-x`" and p.label == "spec"
    base = p.checks.snapshot(repo, "add-x")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "noop"], check=True)
    (repo / "specs" / "add-x" / "notes.md").write_text("note\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "notes"], check=True)
    ignored = []
    assert p.checks.progress(repo, base, "apply", ignored) == [] and ignored == ["change_notes"]
    assert not p.checks.archived(repo, "add-x")
    import shutil
    shutil.rmtree(repo / "specs" / "add-x")
    assert p.checks.archived(repo, "add-x")
    assert workflow.finished_words(d.cfg.profiles_in_use()) == (
        "closed handovers, archived OpenSpec changes, archived specs")


def test_user_profile_archive_after_close(env):
    spec_kit(env)
    env.set_hub({f"show:{A}": show(A, [("2026-11-14T10:00:00.000Z", "app", "done", "ok"),
                                        ("2026-11-14T11:00:00.000Z", "product", "close", "")], status="closed")})
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="done")
    d.state.save()
    env.set_claude([{"steps": [START], "result": {"result": "Archived."}}])
    d.loop(once=True)
    start = log_events(env, "session_start")[0]
    assert start["phase"] == "archive" and "the spec `add-x`" in start["prompt"]
    assert d.state.get(A)["phase"] == "archived"


def test_user_profile_without_artifact_dir_behaves_like_plain(env):
    spec_kit(env, toml='phases = ["apply"]\nbased_on = "plain"\n', files={})
    cfg = env.cfg()
    p = cfg.profile_of("app")
    assert p.phases == ("apply",) and p.label == ""
    assert isinstance(p.checks, workflow.PlainChecks) and not isinstance(p.checks, workflow.DirChecks)
    assert f"ho ack {A}" in prompts.phase_prompt(cand("apply", team="app"), profile=p)


def test_user_profile_without_templates_or_base_is_refused(env):
    spec_kit(env, toml='phases = ["apply"]\n', files={})
    with pytest.raises(config_mod.ConfigError, match="missing prompt template"):
        env.cfg()


def test_propose_without_artifact_dir_is_refused(env):
    spec_kit(env, toml='phases = ["propose", "apply"]\nbased_on = "openspec"\n', files={})
    with pytest.raises(config_mod.ConfigError) as exc:
        env.cfg()
    assert "spec-kit" in str(exc.value) and "artifact_dir" in str(exc.value)
    assert main(["--config", str(env.config_path), "run"]) == 2


def test_invalid_profile_toml_names_the_file(env):
    spec_kit(env, toml='phases = ["apply"]\nnown = "task"\n', files={})
    with pytest.raises(config_mod.ConfigError) as exc:
        env.cfg()
    assert "profile.toml" in str(exc.value) and "nown" in str(exc.value)
    assert main(["--config", str(env.config_path), "dry-run"]) == 2


def test_dry_run_lists_a_user_defined_profile(env, capsys):
    spec_kit(env)
    env.set_hub({})
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "user-defined: spec-kit" in out and re.search(r"^  app +technical spec-kit  ", out, re.M)
