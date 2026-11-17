"""Strict end time for `--until` with fake `ho` and `claude` (strict-end-time, tasks 5.1-5.6).

The end time is set a few seconds ahead on the real clock and the wrap-up grace period is a few seconds, so a fake
session is "running at the end time" without long waits; fake sessions stay active far longer than the test."""
import datetime as dt
import time

import pytest

import radark.__main__ as hm
from radark import prompts
from radark.__main__ import Dispatcher, main, sym
from radark.runner import WRAP_UP, SessionResult
from radark.tests.conftest import START, item, show
from radark.tests.test_limit_check import FINISHES, verdict
from radark.tests.test_limit_check import limits as check_limits
from radark.tests.test_parallel import f, parallel, two_teams
from radark.tests.test_progress import A, apply_item, limits, log_events

GRACE = 0.05  # 3 s wrap-up grace period
AHEAD = 2.0  # seconds from now to the end time: the fake session has started by then
ACTIVE = {"steps": [START, {"active": 30, "every": 0.2}], "result": {}}
WRAPS_UP = {"steps": [START, {"text": "Committed; reporting."}], "result": {"result": "Wrapped up."}}
NOW = dt.datetime(2026, 11, 17, 10, 2)


def strict_item(env, lines, wrap=GRACE, strict=True, ahead=AHEAD):
    limits(env, wrap=wrap)
    d = apply_item(env)
    d._print = lines.append
    d.until, d.until_strict = time.time() + ahead, strict
    return d


def run_item(d):
    (cand,) = d.plan()
    return d.run_candidate(cand)


def prompt_of(call):
    return call["argv"][call["argv"].index("-p") + 1]


def run(env, *args):
    return main(["--config", str(env.config_path), *args])


def loop_config(env, text):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\n" + text))


# ---- stopping a work session at the end time (tasks 5.1, 5.2)

def test_work_session_is_stopped_and_wraps_up_at_the_end_time(env):
    lines = []
    d = strict_item(env, lines)
    env.set_claude([ACTIVE, ACTIVE])  # the wrap-up keeps running too: it is stopped at the end time + grace
    t0 = time.time()
    r = run_item(d)
    took = time.time() - t0
    assert r.outcome == "interrupted" and r.interrupt_cause == "end_time" and took < 20
    work, wrap = env.claude_calls()
    assert wrap["argv"][wrap["argv"].index("--resume") + 1] == r.session_id
    text = prompt_of(wrap)
    assert text.startswith("The run's end time ")
    assert f"in the apply phase of handover {A}. You now have {GRACE:g} min to wrap up" in text
    assert "`git status`" in text and "Start no new work. Commit what works." in text
    assert "`Left for a later run` note" in text and "`tasks.md`" in text
    assert f"Do not report handover {A} as done unless the phase is complete" in text
    assert not log_events(env, "limit_check_start") and not log_events(env, "wrap_up_start")
    (stop,) = log_events(env, "end_time_stop")
    assert (stop["team"], stop["handover"], stop["phase"], stop["grace_min"]) == ("app", A, "apply", GRACE)
    (event,) = log_events(env, "end_time_wrap_up")
    assert (event["outcome"], event["interrupt_cause"], event["wrap_up_session"]) == (
        "interrupted", "end_time", r.session_id)
    assert [e["interrupt_cause"] for e in log_events(env, "session_end")] == ["end_time", "end_time"]
    rec = d.state.get(A)
    assert rec["resume_after_timeout"]["reason"] == "end_time" and rec.get("no_progress", 0) == 0
    assert [s["outcome"] for s in rec["sessions"]] == ["interrupted", "interrupted"]
    assert "time_limits" not in rec  # an end time says nothing about the task's size
    out = "\n".join(lines)
    assert f"! app {A}: end time " in out and f"reached; asking the session to wrap up within {GRACE:g} min" in out
    assert f"app {sym('·')} apply {sym('·')} end-time wrap-up {sym('·')} {A}" in out
    assert f"{sym('→')} interrupted, end time (" in out
    assert "session ended with an error" not in out and "Note: the end time" not in out
    # no new session after the end time; the run ends with exit 0
    assert d.loop() == 0 and len(env.claude_calls()) == 2
    assert len(log_events(env, "run_until_reached")) == 1


def test_next_run_resumes_the_session_stopped_at_the_end_time(env):
    d = strict_item(env, [], wrap=0)
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "interrupted" and r.interrupt_cause == "end_time"
    nxt = Dispatcher(env.cfg(), out=lambda *a: None)
    again = run_item(nxt)
    call = env.claude_calls()[1]
    assert call["argv"][call["argv"].index("--resume") + 1] == r.session_id
    assert prompt_of(call).startswith(prompts.INTERRUPT_LABELS["end_time"] + ", in the apply phase of handover ")
    assert again.outcome == "finished"
    assert log_events(env, "resume_after_timeout")[0]["reason"] == "end_time"


def test_wrap_up_that_completes_its_phase_keeps_finished(env, monkeypatch):
    d = strict_item(env, [])
    monkeypatch.setattr(d, "phase_complete", lambda *a: True)
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "finished" and r.interrupt_cause is None
    assert log_events(env, "end_time_wrap_up")[0]["outcome"] == "finished"
    assert "resume_after_timeout" not in d.state.get(A)


def test_wrap_up_that_ends_without_completing_the_phase_is_interrupted(env):
    d = strict_item(env, [])
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "interrupted" and r.interrupt_cause == "end_time"
    assert d.state.get(A)["resume_after_timeout"]["reason"] == "end_time"


def test_grace_period_off_stops_at_the_end_time_without_a_wrap_up(env):
    lines = []
    d = strict_item(env, lines, wrap=0)
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "interrupted" and r.interrupt_cause == "end_time" and r.duration_s < 15
    assert len(env.claude_calls()) == 1 and not log_events(env, "end_time_wrap_up")
    assert log_events(env, "end_time_stop")[0]["grace_min"] == 0
    assert any(x.endswith("reached; the session is stopped") for x in lines)
    assert d.state.get(A)["resume_after_timeout"]["reason"] == "end_time"


@pytest.mark.parametrize("phase,handover", [("consult", A), ("goal", None), ("idle", None)])
def test_non_work_session_is_stopped_at_the_end_time_plus_grace(env, phase, handover):
    d = strict_item(env, [], ahead=0.5)
    env.set_claude([ACTIVE, WRAPS_UP])
    t0 = time.time()
    r = d.session("product", "question", phase, handover)
    assert r.outcome == "interrupted" and r.interrupt_cause == "end_time"
    assert time.time() - t0 >= 0.5 + GRACE * 60 - 0.5 and len(env.claude_calls()) == 1
    assert not log_events(env, "end_time_stop")


# ---- no extension after the end time (task 5.2)

@pytest.mark.parametrize("wrap,answer", [(GRACE, WRAP_UP), (0, None)])
def test_deadline_after_a_strict_end_time_runs_no_limit_check(env, wrap, answer):
    check_limits(env, wrap=wrap)
    d = apply_item(env)
    d.until, d.until_strict = time.time() - 1, True
    on_deadline, _ = d.limit_watch("app", A, "Task", None, None)
    r = SessionResult(run_id="x", session_id="x", team="app", handover=A, phase="apply", started="")
    assert on_deadline(r, 400) == answer
    runs = env.root / "run" / "runs.jsonl"
    assert env.claude_calls() == [] and (not runs.exists() or not log_events(env, "limit_check_start"))


def test_default_mode_keeps_its_extension_and_prints_the_hint_once(env):
    check_limits(env)  # maximum 1.2 s, extension 1 min
    lines = []
    d = apply_item(env)
    d._print = lines.append
    d.until = time.time() + 0.2  # passes while the session runs
    env.set_claude([FINISHES, verdict("progressing")])
    r = run_item(d)
    assert r.outcome == "finished" and r.timeout_reason is None and r.duration_s >= 4
    assert log_events(env, "limit_check")[0]["extension_min"] == 1
    hints = [x for x in lines if x.startswith("Note: the end time ")]
    assert hints == [f"Note: the end time {hm.day_clock(d.until, time.time())} has passed; the running session "
                     "finishes. To end on time, use --until-strict."]
    (event,) = log_events(env, "end_time_passed")
    assert event["sessions_running"] == 1


def test_default_mode_hint_once_with_a_second_session(env):
    check_limits(env, checks=0, wrap=GRACE)  # the time-limit wrap-up is a second session after the end time
    lines = []
    d = apply_item(env)
    d._print = lines.append
    d.until = time.time() + 0.2
    env.set_claude([ACTIVE, WRAPS_UP])
    r = run_item(d)
    assert r.outcome == "finished" and len(env.claude_calls()) == 2
    assert len([x for x in lines if x.startswith("Note: the end time ")]) == 1
    assert len(log_events(env, "end_time_passed")) == 1


def test_no_hint_when_idle_or_without_an_end_time(env):
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.until = time.time() + 0.3
    assert d.loop() == 0 and env.claude_calls() == []
    assert not [x for x in lines if x.startswith("Note:")] and not log_events(env, "end_time_passed")
    assert Dispatcher(env.cfg(), out=lines.append).end_watch(True) == (None, None)


# ---- parallel sessions (task 5.3)

def test_both_parallel_sessions_are_stopped_and_wrap_up(env):
    limits(env, wrap=GRACE)
    parallel(env)
    two_teams(env)
    work = lambda team: {"steps": [START, {"touch": f(env, f"{team}.started")}, {"active": 30, "every": 0.2}],
                         "result": {}}
    env.set_claude({"app": [work("app"), ACTIVE], "backend": [work("backend"), ACTIVE]})
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.until, d.until_strict = time.time() + 4, True
    t0 = time.time()
    assert d.loop() == 0 and time.time() - t0 < 30
    calls = env.claude_calls()
    assert len(calls) == 4 and sum("--resume" in c["argv"] for c in calls) == 2
    assert sorted(e["team"] for e in log_events(env, "end_time_stop")) == ["app", "backend"]
    assert sorted(e["team"] for e in log_events(env, "end_time_wrap_up")) == ["app", "backend"]
    assert len(log_events(env, "run_until_reached")) == 1


# ---- option, configuration and reporting (tasks 5.5, 5.6)

def test_option_turns_strict_mode_on(env, capsys):
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    assert run(env, "dry-run", "--until", "2099-01-01 08:00", "--until-strict") == 0
    assert "Would end: 08:00 on 2099-01-01, in " in (out := capsys.readouterr().out)
    assert "(strict: running sessions wrap up at 08:00, stopped by 08:15)" in out


def test_no_option_overrides_the_configured_default(env, capsys):
    loop_config(env, "until_strict = true")
    assert run(env, "dry-run", "--until", "2099-01-01 08:00", "--no-until-strict") == 0
    assert "(running sessions finish first)" in capsys.readouterr().out
    assert run(env, "dry-run", "--until", "2099-01-01 08:00") == 0
    assert "(strict: running sessions wrap up at 08:00" in capsys.readouterr().out


def test_configured_default_without_an_end_time_has_no_effect(env, capsys):
    loop_config(env, "until_strict = true")
    assert run(env, "dry-run") == 0
    assert "strict" not in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--until-strict", "--no-until-strict"])
@pytest.mark.parametrize("command", [["run"], ["run", "--once"], ["dry-run"]])
def test_option_without_an_end_time_is_refused(env, capsys, flag, command):
    assert run(env, *command, flag) == 2
    assert f"{flag} needs --until (an end time)" in capsys.readouterr().err
    assert env.claude_calls() == [] and not (env.root / "run" / "lock").exists()


def test_invalid_configured_value_is_refused(env, capsys):
    loop_config(env, 'until_strict = "yes"')
    assert run(env, "run", "--until", "2099-01-01 08:00") == 2
    assert "loop.until_strict must be true or false, not 'yes'" in capsys.readouterr().err
    assert env.claude_calls() == []


def test_strict_flag_not_stored(env):
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.until, d.until_strict = time.time() + 3600, True
    d.start_until()
    d.state.save()
    assert "strict" not in (env.root / "run" / "state.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("strict,wrap,suffix", [
    (True, 15, "(strict: running sessions wrap up at 12:00, stopped by 12:15)"),
    (True, 0, "(strict: running sessions stop at 12:00)"),
    (False, 15, "(running sessions finish first)"),
])
def test_start_line(env, monkeypatch, strict, wrap, suffix):
    monkeypatch.setattr(hm.time, "time", lambda: NOW.timestamp())
    loop_config(env, f"wrap_up_minutes = {wrap}")
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.until, d.until_strict = NOW.replace(hour=12, minute=0).timestamp(), strict
    d.start_until()
    assert lines == [f"Run ends at 12:00 today, in 118 min {suffix}"]
    (event,) = log_events(env, "run_until")
    assert event["strict"] is strict


def test_dry_run_with_a_strict_end_time(env, capsys, monkeypatch):
    real = dt.datetime

    class Fixed(real):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(hm.dt, "datetime", Fixed)
    monkeypatch.setattr(hm.time, "time", lambda: NOW.timestamp())
    assert run(env, "dry-run", "--until", "12:00", "--until-strict") == 0
    assert ("Would end: 12:00 today, in 118 min (strict: running sessions wrap up at 12:00, stopped by 12:15)"
            in capsys.readouterr().out)


def test_goal_start_records_the_mode(env):
    from radark.state import GoalRun
    goal = env.root / "goal.md"
    goal.write_text("Finish B-1.", encoding="utf-8")
    d = Dispatcher(env.cfg(), out=lambda *a: None)
    d.until, d.until_strict = time.time() + 3600, True
    d.start_goal(GoalRun(goal, "Finish B-1.", 40, 12))
    assert log_events(env, "goal_start")[0]["until_strict"] is True
