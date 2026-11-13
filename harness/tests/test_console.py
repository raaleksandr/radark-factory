"""Console progress lines: start / end of a step, marked problem lines, local times (change console-progress)."""
import datetime as dt
import io
import json
import re
import sys
import time

import pytest

from harness import __main__ as main_mod
from harness.__main__ import (Dispatcher, console_print, duration_text, end_line, short_title, stamp, start_lines,
                              sym)
from harness.runner import SessionResult
from harness.tests.conftest import ASK_STEP, START, item, show, stop_step

A = "HO-20261024-sx7z"
B = "HO-20261024-bbbb"
LATER = "2099-01-01T00:00:00.000Z"
TITLE = "The agent is told a slow page is loading, not failed (BL-049)"
HHMM = re.compile(r"^\d\d:\d\d  ")


@pytest.fixture
def utf8(monkeypatch):
    monkeypatch.setattr(main_mod, "utf8_console", lambda: True)


def disp(env, lines):
    return Dispatcher(env.cfg(), out=lines.append)


def log_events(env):
    return [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


def cp1252():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")


# ---- helpers (tasks 1.1, 1.2)

def test_stamp_today_and_another_day():
    now = time.time()
    assert stamp(now) == dt.datetime.fromtimestamp(now).strftime("%H:%M")
    other = now - 3 * 86400
    assert stamp(other) == dt.datetime.fromtimestamp(other).strftime("%d.%m %H:%M")


@pytest.mark.parametrize("seconds, text", [(45, "45 s"), (119.6, "120 s"), (2160, "36 min"), (5400, "90 min"),
                                           (7500, "2 h 05 min")])
def test_duration_text(seconds, text):
    assert duration_text(seconds) == text


def test_long_title_is_shortened(utf8):
    long = "word " * 40
    assert short_title(long, 30) == ("word " * 6).rstrip()[:29].rstrip() + "…" and len(short_title(long, 30)) <= 30
    lines = start_lines("app", "apply", A, long, None)
    assert len(lines) == 1 and len(lines[0]) <= main_mod.LINE_WIDTH and lines[0].endswith('…"')
    lines = start_lines("a-team-with-a-very-long-identifier-" * 2, "apply", A, TITLE, "resume after time limit")
    assert len(lines) == 2 and lines[1] == f'       "{TITLE}"'


def test_ascii_fallback_on_cp1252_stdout(monkeypatch):
    monkeypatch.setattr(sys, "stdout", cp1252())
    assert (sym("·"), sym("→"), sym("…")) == ("-", "->", "...")
    assert " - apply - " in start_lines("app", "apply", A, TITLE, None)[0]
    r = SessionResult(run_id="r", session_id="s", team="app", handover=A, phase="apply", started="",
                      outcome="finished", duration_s=60)
    assert end_line("app", "apply", None, r).endswith("apply -> finished (60 s)")


def test_out_never_raises_on_the_console_encoding(env, monkeypatch):
    stream = cp1252()
    console_print("Привет → done", stream)
    stream.seek(0)
    assert stream.buffer.getvalue().decode("cp1252") == "?????? ? done\n"
    monkeypatch.setattr(sys, "stdout", cp1252())
    d = Dispatcher(env.cfg())
    d.problem("Задача → owner")
    sys.stdout.seek(0)
    assert re.match(r"^\d\d:\d\d  ! \?+ \? owner\n$", sys.stdout.buffer.getvalue().decode("cp1252"))


# ---- start and end lines (tasks 2.1, 2.2)

def test_apply_start_line_names_time_team_phase_id_and_title(env, utf8):
    env.set_hub({"inbox:app": {"action_required": [item(A, title=TITLE, my_state="acknowledged")]},
                 f"show:{A}": show(A, [(LATER, "app", "comment", "ok")], title=TITLE)})
    lines = []
    d = disp(env, lines)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    before = stamp()
    d.loop(once=True)
    assert lines[0] in (f'{t}  app · apply · {A}  "{TITLE}"' for t in (before, stamp()))
    assert HHMM.match(lines[1]) and lines[1].startswith(lines[1][:5] + "  app · apply → finished (")
    assert d.state.get(A)["title"] == TITLE


def test_goal_check_start_line(env, utf8):
    lines = []
    d = disp(env, lines)
    env.set_claude([{"steps": [START], "result": {"result": "{}"}}])
    d.session("product", "Check the goal.", "goal", None)
    assert HHMM.match(lines[0]) and lines[0][7:] == "product · goal check"
    assert "product · goal check → finished (" in lines[1]


def test_finished_end_line_after_36_min(utf8):
    r = SessionResult(run_id="r", session_id="s", team="app", handover=A, phase="apply", started="",
                      outcome="finished", duration_s=36 * 60 + 10)
    line = end_line("app", "apply", None, r)
    assert HHMM.match(line) and line[7:] == "app · apply → finished (36 min)"


# ---- problem lines (task 3.1)

def test_time_limit_error_without_progress(env, utf8):
    env.config_path.write_text(env.config_path.read_text().replace("[loop]", "[loop]\nsession_idle_minutes = 0.03"))
    env.set_hub({"inbox:app": {"action_required": [item(A, title=TITLE, my_state="acknowledged")]},
                 f"show:{A}": show(A, title=TITLE)})
    lines = []
    d = disp(env, lines)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": {}}])
    d.loop(once=True)
    problems = [x[9:] for x in lines if x[5:9] == "  ! "]
    assert "app · apply → error, idle time limit (" in lines[1]
    assert problems[0].startswith(f"app {A}: session ended with an error: idle time limit after ")
    assert problems[1] == f"app {A}: no progress in this session (1 of 2 before the item stalls)"


def test_question_answered_by_triage_technical(env, utf8):
    env.set_hub({"inbox:app": {"action_required": [item(A, title=TITLE)]},
                 f"show:{A}": show(A, [(LATER, "app", "ack", "")], title=TITLE)})
    env.set_claude([{"steps": [START, ASK_STEP, stop_step("Waiting.")], "result": {"result": "Referred."}},
                    {"steps": [START], "result": {"result": "", "structured_output":
                                                  {"verdict": "technical", "answer": "", "reason": "internal"}}},
                    {"steps": [START], "result": {"result": "Continued."}}])
    lines = []
    disp(env, lines).loop(once=True)
    text = [x[7:] for x in lines]
    assert any(x.startswith(f'! app {A}: question for product triage: "Use a Map or a plain') for x in text)
    assert any(x.startswith(f'product · triage consultation · {A}  "The agent is told') for x in text)
    i = text.index(f"! app {A}: question went to product triage, verdict technical")
    assert text[i + 1].startswith(f'app · propose · triage answer · {A}  "The agent is told')
    assert [x for x in lines if len(x) > main_mod.LINE_WIDTH] == []


def test_denial_and_escalation_are_marked(env, utf8):
    env.set_hub({"inbox:app": {"action_required": [item(A, title=TITLE)]}, f"show:{A}": show(A, title=TITLE)})
    env.set_claude([{"steps": [START], "result": {"result": "Blocked.", "permission_denials": [
        {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "git push"}}]}}])
    lines = []
    disp(env, lines).loop(once=True)
    text = [x[9:] for x in lines if x[5:9] == "  ! "]
    assert text[0] == f"app {A}: permission denied: Bash"
    assert text[1].startswith(f"ESCALATED {A} (app): permission denied: Bash")


# ---- the run log is unchanged (task 3.2)

# events and fields of this scripted run, recorded with the dispatcher before console-progress
BEFORE = [
    ("session_start", "event handover phase prompt repo resume team time"),
    ("question", "event handover question session source team time"),
    ("session_end", "auto_answers denials duration_s escalations event exit_code handover interrupt_cause outcome "
                    "phase progress_sources result session stream team time timed_out timeout_reason"),  # + sleep-aware
    ("session_start", "event handover phase prompt repo resume team time"),
    ("session_end", None),
    ("triage", "consult_session duration_s event handover outcome question session team time verdict"),
    ("session_start", None),
    ("denial", "denial event handover session team time"),
    ("session_end", None),
    ("escalation", "event handover reason team time"),
    ("escalation_sent", "escalation event handover reason team time"),
    ("session_start", None),
    ("session_end", None),
    ("propose_without_change", "event handover outcome session team time"),  # + rerun-propose-without-change
    ("no_progress", "count event handover team time timeout_reason"),
    ("session_start", None),
    ("session_end", None),
    ("propose_without_change", None),
    ("no_progress", None),
    ("stalled", "event handover reason team time"),
    ("escalation_sent", None),
]


def test_run_log_events_and_fields_unchanged(env):
    env.set_hub({"inbox:app": {"action_required": [item(A, title=TITLE)]},
                 f"show:{A}": show(A, [(LATER, "app", "ack", "")], title=TITLE)})
    env.set_claude([{"steps": [START, ASK_STEP, stop_step("Waiting.")], "result": {"result": "Referred."}},
                    {"steps": [START], "result": {"result": "", "structured_output":
                                                  {"verdict": "technical", "answer": "", "reason": "internal"}}},
                    {"steps": [START], "result": {"result": "Continued.", "permission_denials": [
                        {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "git push"}}]}}])
    disp(env, []).loop(once=True)
    env.set_hub({"inbox:app": {"action_required": [item(B, title="Fix the page")]},
                 f"show:{B}": show(B, title="Fix the page")})
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    d = disp(env, [])
    d.loop(once=True)
    d.loop(once=True)
    fields, expected = {}, []
    for event, keys in BEFORE:
        fields[event] = keys or fields[event]
        expected.append((event, fields[event].split()))
    events = log_events(env)
    assert [(e["event"], sorted(e)) for e in events] == expected
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", e["time"]) for e in events)


def test_tee_never_raises_and_keeps_unicode_in_the_file(tmp_path):
    console, path = cp1252(), tmp_path / "console.log"
    with open(path, "w", encoding="utf-8") as f:
        tee = main_mod.Tee(console, f)
        tee.write("22:24  app · propose → finished\n")
        assert tee.encoding == "cp1252"
    console.seek(0)
    assert console.buffer.read().decode("cp1252") == "22:24  app · propose ? finished\n"
    assert path.read_text(encoding="utf-8") == "22:24  app · propose → finished\n"


class FakeKernel32:
    def __init__(self, mode):
        self.mode, self.set = mode, None

    def GetStdHandle(self, n):
        return n

    def GetConsoleMode(self, handle, ref):
        if self.mode is None:
            return 0
        ref._obj.value = self.mode
        return 1

    def SetConsoleMode(self, handle, mode):
        self.set = mode
        return 1


def test_quick_edit_off_clears_quick_edit_and_keeps_the_rest():
    k = FakeKernel32(0x1F7)  # QuickEdit on, with insert, mouse, echo, ...
    assert main_mod.quick_edit_off(k)
    assert k.set == (0x1F7 & ~0x40) | 0x80


def test_quick_edit_off_leaves_a_non_console_stdin_alone():
    k = FakeKernel32(None)
    assert not main_mod.quick_edit_off(k)
    assert k.set is None


def test_no_progress_line_names_change_notes(env, utf8):
    """no-loop N2: commits found, but only inside the change's own directory."""
    from harness import select as sel
    env.set_hub({f"show:{A}": show(A, title=TITLE)})
    lines = []
    d = disp(env, lines)
    rec = d.state.ensure(A, "app")
    rec.update(change="add-x", phase="apply")
    cand = sel.Candidate(kind="work", team="app", handover=A, title=TITLE, phase="apply", recency="",
                         team_index=1, change="add-x")
    r = SessionResult(run_id="r", session_id="s", team="app", handover=A, phase="apply", started="",
                      exit_code=0, outcome="finished", has_result=True, hooks_loaded=True, progress_sources=[],
                      progress_ignored="change_notes")
    d.after_session(cand, rec, r)
    problems = [x[9:] for x in lines if x[5:9] == "  ! "]
    assert problems == [f"app {A}: no progress in this session (1 of 2 before the item stalls) "
                        "(commits changed only the change's own files)"]
    [event] = [e for e in log_events(env) if e["event"] == "no_progress"]
    assert event["ignored"] == "change_notes"
    r.progress_ignored = None
    lines.clear()
    d.after_session(cand, rec, r)
    assert not any("change's own files" in x for x in lines)
    assert "ignored" not in [e for e in log_events(env) if e["event"] == "no_progress"][-1]
