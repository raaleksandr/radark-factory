"""Start banner: its form and where it is printed (change start-banner, HO-20261117-u2vc)."""
import shutil

from radark import banner
from radark.__main__ import main
from radark.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
LATER = "2099-01-01T00:00:00.000Z"


def run_main(env, *args):
    return main(["--config", str(env.config_path), *args])


def has_banner(text):
    return banner.lines()[0] in text.splitlines()


# ---- form (task 2.1)

def test_banner_form():
    lines = banner.lines()
    assert 1 <= len(lines) <= 25
    assert "\t" not in banner.BANNER and "\r" not in banner.BANNER and not banner.BANNER.endswith("\n")
    for line in lines:
        assert len(line) <= 80 and line == line.rstrip()
        assert all(0x20 <= ord(c) <= 0x7E for c in line)


def test_banner_lettering_and_factory():
    lines = banner.lines()
    assert "            #####    ####           #####    ####   #####   #   #" in lines  # top of "RA DARK"
    assert "            ######   ####    #####  ######   ####   #####   #    #" in lines  # top of "FACTORY"
    assert any("||" in line for line in lines)  # chimneys
    assert any("(" in line and ")" in line for line in lines) and any("~" in line for line in lines)  # smoke


# ---- where it is printed (tasks 2.2 - 2.4)

def test_dry_run_starts_with_the_banner(env, capsys):
    assert run_main(env, "dry-run") == 0
    out = capsys.readouterr().out
    assert out.startswith(banner.BANNER + "\n") and out.count(banner.BANNER) == 1
    rest = out[len(banner.BANNER) + 1:]
    assert rest.splitlines()[0] == f"Hub: {env.cfg().hub}"  # the summary follows right after
    assert not (env.root / "run" / "console.log").exists()  # dry-run writes no console.log (design D3)


def test_run_dry_run_flag_prints_it_once(env, capsys):
    assert run_main(env, "run", "--dry-run") == 0
    out = capsys.readouterr().out
    assert out.startswith(banner.BANNER + "\n") and out.count(banner.BANNER) == 1


def test_once_banner_in_window_and_console_log(env, capsys):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A, [(LATER, "app", "ack", "")])})
    env.set_claude([{"steps": [START, {"text": "CHANGE: add-export"}], "result": {"result": "CHANGE: add-export"}}])
    assert run_main(env, "once") == 0
    out = capsys.readouterr().out
    assert out.startswith(banner.BANNER + "\n") and out.count(banner.BANNER) == 1
    log = (env.root / "run" / "console.log").read_text(encoding="utf-8").splitlines()
    assert log[0] == "" and log[1].startswith("==== ")  # the header line of this start
    n = len(banner.lines())
    assert log[2:2 + n] == banner.lines()
    assert log[2 + n] == f"Hub: {env.cfg().hub}"


def test_no_banner_for_plan_and_escalations(env, capsys):
    assert run_main(env, "plan") == 0
    assert run_main(env, "escalations") == 0
    captured = capsys.readouterr()
    assert not has_banner(captured.out) and not has_banner(captured.err)


def test_no_banner_on_a_refused_start(env, capsys):
    shutil.rmtree(env.root / "repos" / "app")
    assert run_main(env, "run") == 2
    captured = capsys.readouterr()
    assert "does not exist" in captured.err and not has_banner(captured.out + captured.err)
