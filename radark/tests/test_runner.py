"""Runner with a fake `claude` that emits recorded streams and calls the real hooks (task 4.1)."""
import json
import threading
import time

from radark import runner as runner_mod
from radark.clock import Sleep
from radark.runner import Runner, SessionResult, apply_event
from radark.tests.conftest import ASK_STEP, START, usage_step


def run(env, scenarios, team="app", **kw):
    env.set_claude(scenarios)
    return Runner(env.cfg()).run(team, "do it", phase="apply", handover="HO-20261016-ab12", **kw)


def test_command_flags_env_and_stream(env):
    r = run(env, [{"steps": [START, {"text": "Working."}], "result": {"result": "All done."}}])
    assert r.outcome == "finished" and r.result_text == "All done." and r.hooks_loaded
    call = env.claude_calls()[0]
    argv = call["argv"]
    assert argv[:2] == ["-p", "do it"]
    assert argv[argv.index("--session-id") + 1] == r.session_id
    for flag, value in [("--output-format", "stream-json"), ("--permission-mode", "auto"), ("--permission-prompts", "none")]:
        assert argv[argv.index(flag) + 1] == value
    assert "--verbose" in argv and "--append-system-prompt" in argv and "--bare" not in argv
    settings = json.loads(open(argv[argv.index("--settings") + 1]).read())
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "AskUserQuestion" and hook["hooks"][0]["args"][0].endswith("ask_user_question.py")
    assert call["cwd"].endswith("app")
    assert call["env"]["ANTHROPIC_API_KEY"] is None and call["env"]["HARNESS_TEAM"] == "app"
    lines = open(r.stream_path).read().splitlines()
    assert json.loads(lines[-1])["type"] == "result" and "Working." in r.assistant_text


def test_error_on_nonzero_exit_or_missing_result(env):
    assert run(env, [{"steps": [START], "exit": 1}]).outcome == "error"
    assert run(env, [{"steps": [START], "result": None}]).outcome == "error"
    assert run(env, [{"steps": [START], "result": {"is_error": True}}]).outcome == "error"


def test_hooks_not_loaded_is_error(env):
    r = run(env, [{"steps": [], "result": {"result": "ok"}}])
    assert r.outcome == "error" and not r.hooks_loaded


def test_usage_limit_from_stop_failure_or_api_retry(env):
    r = run(env, [{"steps": [START, {"hook": "StopFailure", "input": {"error": "rate_limit"}}], "exit": 1}])
    assert r.outcome == "usage_limit"
    r = run(env, [{"steps": [START, {"emit": {"type": "system", "subtype": "api_retry", "error": "rate_limit"}}],
                   "result": {"result": "x"}}])
    assert r.outcome == "usage_limit"


def test_permission_denial_waits_for_owner_but_own_ask_denials_do_not(env):
    r = run(env, [{"steps": [START], "result": {"permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "curl x"}}]}}])
    assert r.outcome == "waiting_for_owner" and r.denials[0]["tool_name"] == "Bash"
    r = run(env, [{"steps": [START], "result": {"permission_denials": [{"tool_name": "AskUserQuestion"}]}}],
            team="product")
    assert r.outcome == "finished" and r.denials == []


def test_question_and_escalation_markers(env):
    r = run(env, [{"steps": [START, ASK_STEP], "result": {"result": "Referred."}}])
    assert r.outcome == "question" and r.markers_of("question")
    risky = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion",
                                              "tool_input": {"questions": [{"question": "Deploy to production?"}]}}}
    assert run(env, [{"steps": [START, risky], "result": {}}]).outcome == "waiting_for_owner"


def test_max_time_kills_process(env):
    r = run(env, [{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}], timeout_s=2)
    assert r.timed_out and r.timeout_reason == "max_time" and r.outcome == "error" and r.duration_s < 20


def test_hung_session_cut_early(env):
    r = run(env, [{"steps": [START, {"sleep": 30}], "result": {}}], idle_s=1.5, timeout_s=60)
    assert r.timeout_reason == "idle_timeout" and r.outcome == "error" and r.duration_s < 20



def test_hung_tool_call_with_heartbeats_cut(env):
    r = run(env, [{"steps": [START, {"heartbeats": 30, "every": 0.3}], "result": {}}], idle_s=1.5, timeout_s=60)
    assert r.timeout_reason == "idle_timeout" and r.duration_s < 20

def test_long_productive_session_not_cut(env):
    r = run(env, [{"steps": [START, {"active": 4, "every": 0.3}], "result": {"result": "Done."}}], idle_s=1.5, timeout_s=60)
    assert r.outcome == "finished" and r.timeout_reason is None and not r.timed_out and r.duration_s >= 4


def test_resume_uses_resume_flag_and_new_marker_file(env):
    r = run(env, [{"steps": [START], "result": {}}], resume="sess-abc")
    argv = env.claude_calls()[0]["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-abc" and "--session-id" not in argv
    assert r.session_id == "sess-abc" and r.run_id.startswith("sess-abc-r")


# ---- usage reading (usage-limit-guard, design D1)

OBSERVED = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1792281000, "rateLimitType": "five_hour", "overageStatus": "rejected",
    "isUsingOverage": False, "unifiedWindows": {"five_hour": {"utilization": 0.57, "resetsAt": 1792281000},
                                                "seven_day": {"utilization": 0.34, "resetsAt": 1792652400}}}}


def blank():
    return SessionResult(run_id="r", session_id="s", team="t", handover=None, phase="apply", started="")


def test_rate_limit_event_observed_shape():
    r = blank()
    apply_event(OBSERVED, r, [])
    assert r.usage == {"five_hour": {"utilization": 0.57, "resets_at": 1792281000, "status": "allowed"},
                       "seven_day": {"utilization": 0.34, "resets_at": 1792652400, "status": None}}


def test_rate_limit_event_single_window():
    r = blank()
    apply_event({"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "rateLimitType": "five_hour", "utilization": 1.0, "resetsAt": 1792281000}}, r, [])
    assert r.usage == {"five_hour": {"utilization": 1.0, "resets_at": 1792281000, "status": "rejected"}}


def test_rate_limit_event_malformed_is_ignored(env):
    r = blank()
    for ev in ({"type": "rate_limit_event"}, {"type": "rate_limit_event", "rate_limit_info": "x"},
               {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"five_hour": "x",
                                                                                   "seven_day": {"utilization": "a"}}}}):
        apply_event(ev, r, [])
    assert r.usage == {}
    bad = {"emit": {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": [1, 2]}}}
    s = run(env, [{"steps": [START, bad], "result": {"result": "ok"}}])
    assert s.outcome == "finished" and s.usage == {}


def test_usage_read_from_session_stream_and_callback_order(env):
    seen = []
    r = run(env, [{"steps": [START, usage_step(five_hour=(0.43, 1792281000), seven_day=(0.3, 1792652400)),
                             usage_step(five_hour=(0.61, 1792281000))], "result": {"result": "ok"}}],
            on_usage=lambda *a: seen.append(a))
    assert r.outcome == "finished"
    assert seen == [("five_hour", 0.43, 1792281000), ("seven_day", 0.3, 1792652400), ("five_hour", 0.61, 1792281000)]
    assert r.usage["five_hour"]["utilization"] == 0.61 and r.usage["seven_day"]["utilization"] == 0.3


def test_failing_usage_callback_does_not_break_session(env):
    def boom(*a):
        raise RuntimeError("x")
    r = run(env, [{"steps": [START, usage_step(five_hour=(0.5, 1792281000))], "result": {"result": "ok"}}],
            on_usage=boom)
    assert r.outcome == "finished" and r.usage["five_hour"]["utilization"] == 0.5


# ---- sleep of the computer (sleep-aware-dispatcher, tasks 2.1, 2.2)

def sleep_after(seconds, length=2 * 3600):
    """A sleep_check that reports one sleep of `length` once `seconds` of the session have passed."""
    t0, seen = time.monotonic(), []

    def check():
        if not seen and time.monotonic() - t0 > seconds:
            seen.append(1)
            return Sleep(start=time.time() - length, end=time.time(), seconds=length)
        return None
    return check, seen


def test_sleep_inside_a_session_ends_it_by_no_time_limit(env, monkeypatch):
    check, seen = sleep_after(1)
    real = time.monotonic
    # on Windows monotonic time goes on during a sleep: a jump of 2 h must not reach the limits
    monkeypatch.setattr(runner_mod.time, "monotonic", lambda: real() + (7200 if seen else 0))
    r = run(env, [{"steps": [START, {"active": 3, "every": 0.3}], "result": {"result": "Done."}}],
            idle_s=1.5, timeout_s=60, sleep_check=check, grace_s=1)
    assert seen and r.outcome == "finished" and r.timeout_reason is None and r.interrupt_cause is None
    assert 3 <= r.duration_s < 20


def test_event_within_the_grace_keeps_the_session(env):
    check, seen = sleep_after(1.5)
    r = run(env, [{"steps": [START, {"sleep": 2.5}, {"text": "back"}], "result": {"result": "Done."}}],
            idle_s=60, timeout_s=60, sleep_check=check, grace_s=2)
    assert seen and r.outcome == "finished" and r.interrupt_cause is None


def test_silence_after_a_wake_interrupts(env):
    check, seen = sleep_after(1.5)
    r = run(env, [{"steps": [START, {"sleep": 30}], "result": {}}], idle_s=60, timeout_s=60,
            sleep_check=check, grace_s=1)
    assert seen and r.outcome == "interrupted" and r.interrupt_cause == "sleep" and not r.timed_out
    assert r.duration_s < 20


def test_second_ctrl_c_interrupts_with_cause_owner(env):
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": {}}])
    runner = Runner(env.cfg())
    threading.Timer(1.5, runner.kill).start()
    r = runner.run("app", "do it", phase="propose", handover="HO-20261016-ab12")
    assert r.outcome == "interrupted" and r.interrupt_cause == "owner" and r.killed


def test_on_start_gets_the_session_and_pid(env):
    started = []
    r = run(env, [{"steps": [START], "result": {}}], on_start=lambda *a: started.append(a))
    assert len(started) == 1 and started[0][:2] == (r.session_id, r.run_id) and started[0][2] > 0


# ---- limit check at the maximum duration (check-session-at-time-limit, tasks 2.1, 2.2)

def ev_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def ev_tool(name, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def test_ring_keeps_texts_tool_calls_errors_and_the_running_tool():
    r = blank()
    apply_event(ev_text("Running the e2e suite now.\n\nIt takes a while."), r, [], at=10.0)
    apply_event(ev_tool("Bash", command="pnpm e2e", description="e2e"), r, [], at=11.0)
    apply_event({"type": "tool_progress", "tool_name": "Bash", "heartbeat": True, "elapsed_time_seconds": 600},
                 r, [], at=611.0)
    assert r.running_tool == ("Bash", 600, 611.0)
    apply_event({"type": "user", "message": {"content": [
        {"type": "tool_result", "is_error": True, "content": [{"type": "text", "text": "Exit code 1\nfailed"}]},
        {"type": "tool_result", "is_error": False, "content": "ok"}]}}, r, [], at=700.0)
    apply_event(ev_tool("Read", file_path="src/a.ts"), r, [], at=701.0)
    apply_event(ev_tool("Grep", pattern="TODO", path="src"), r, [], at=702.0)
    assert r.running_tool is None
    assert list(r.recent) == [(10.0, "text", "Running the e2e suite now. It takes a while."),
                              (11.0, "tool", "Bash: pnpm e2e"), (700.0, "error", "Exit code 1 failed"),
                              (701.0, "tool", "Read: src/a.ts"), (702.0, "tool", "Grep: TODO")]


def test_ring_truncates_and_is_bounded():
    r = blank()
    apply_event(ev_text("x" * 1000), r, [], at=1.0)
    apply_event(ev_tool("Bash", command="y" * 1000), r, [], at=2.0)
    assert len(r.recent[0][2]) == 300 and r.recent[0][2].endswith("...")
    assert len(r.recent[1][2]) == 150 and r.recent[1][2].startswith("Bash: yyy")
    for i in range(100):
        apply_event(ev_text(f"t{i}"), r, [], at=float(i))
    assert len(r.recent) == 40 and r.recent[-1][2] == "t99" and r.recent[0][2] == "t60"


def test_ring_filled_from_the_stream_with_awake_times(env):
    r = run(env, [{"steps": [START, {"text": "first"}, {"sleep": 1}, {"emit": ev_tool("Bash", command="ls")},
                             {"emit": {"type": "tool_progress", "tool_name": "Bash", "heartbeat": True,
                                       "elapsed_time_seconds": 30}}], "result": {"result": "ok"}}])
    texts = [x for x in r.recent if x[1] == "text"]
    tools = [x for x in r.recent if x[1] == "tool"]
    assert texts[0][2] == "first" and tools == [(tools[0][0], "tool", "Bash: ls")]
    assert tools[0][0] - texts[0][0] >= 0.9 and texts[0][0] >= r.awake_start
    assert r.running_tool[:2] == ("Bash", 30)
    assert r.last_event_at >= tools[0][0]  # the result came after the heartbeat


def test_deadline_check_extends_then_the_session_finishes(env):
    calls = []

    def on_deadline(r, elapsed):
        calls.append(elapsed)
        time.sleep(0.5)
        return 30
    r = run(env, [{"steps": [START, {"active": 3, "every": 0.2}], "result": {"result": "Done."}}],
            timeout_s=1, idle_s=60, on_deadline=on_deadline)
    assert r.outcome == "finished" and r.timeout_reason is None and r.duration_s >= 3
    assert len(calls) == 1 and calls[0] >= 1


def test_deadline_check_answers_none_ends_by_max_time(env):
    calls = []

    def on_deadline(r, elapsed):
        calls.append(elapsed)
        time.sleep(0.8)  # the session is not cut while the check runs
        return None
    r = run(env, [{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}], timeout_s=1, idle_s=60,
            on_deadline=on_deadline)
    assert r.timeout_reason == "max_time" and r.outcome == "error" and len(calls) == 1
    assert 1.7 <= r.duration_s < 20


def test_second_deadline_asks_again(env):
    calls = []

    def on_deadline(r, elapsed):
        calls.append(elapsed)
        return 1 if len(calls) == 1 else None
    r = run(env, [{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}], timeout_s=1, idle_s=60,
            on_deadline=on_deadline)
    assert r.timeout_reason == "max_time" and len(calls) == 2 and calls[1] >= 2 and r.duration_s < 20


def test_idle_limit_fires_during_a_pending_check(env):
    released, aborted = threading.Event(), []

    def on_deadline(r, elapsed):
        released.wait(30)
        return 600

    def abort():
        aborted.append(1)
        released.set()
    r = run(env, [{"steps": [START, {"active": 1.5, "every": 0.2}, {"sleep": 30}], "result": {}}],
            timeout_s=1, idle_s=1.5, on_deadline=on_deadline, on_deadline_abort=abort)
    assert r.timeout_reason == "idle_timeout" and aborted == [1] and r.duration_s < 20


def test_session_ending_during_the_check_aborts_it(env):
    released, aborted = threading.Event(), []

    def on_deadline(r, elapsed):
        released.wait(30)
        return None  # ignored: the session has ended

    def abort():
        aborted.append(1)
        released.set()
    r = run(env, [{"steps": [START, {"active": 2, "every": 0.2}], "result": {"result": "Done."}}],
            timeout_s=1, idle_s=60, on_deadline=on_deadline, on_deadline_abort=abort)
    assert r.outcome == "finished" and r.timeout_reason is None and aborted == [1]


def test_failing_deadline_callback_ends_by_max_time(env):
    def on_deadline(r, elapsed):
        raise RuntimeError("x")
    r = run(env, [{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}], timeout_s=1, idle_s=60,
            on_deadline=on_deadline)
    assert r.timeout_reason == "max_time" and r.duration_s < 20


def test_deadline_counts_the_runner_clock(env):
    """The deadline uses the runner's (awake) clock: a fast fake clock reaches it before real time does."""
    env.set_claude([{"steps": [START, {"active": 30, "every": 0.2}], "result": {}}])
    runner = Runner(env.cfg())
    start = time.monotonic()
    runner.clock = lambda: (time.monotonic() - start) * 3600  # one real second is an hour
    calls = []
    r = runner.run("app", "do it", phase="apply", handover="HO-20261016-ab12", idle_s=10 ** 9,
                   on_deadline=lambda res, elapsed: calls.append(elapsed) or (3600 if len(calls) == 1 else None))
    assert r.timeout_reason == "max_time" and len(calls) == 2
    assert 180 * 60 <= calls[0] < 200 * 60 and 240 * 60 <= calls[1] < 260 * 60


# ---- long-wait rule in the system prompt (check-long-waits D1)

def system_prompt(env, idle=None, **kw):
    cfg = env.cfg()
    if idle is not None:
        cfg.session_idle_minutes = idle
    env.set_claude([{"steps": [START], "result": {}}])
    Runner(cfg).run("app", "do it", phase="apply", **kw)
    argv = env.claude_calls()[-1]["argv"]
    return argv[argv.index("--append-system-prompt") + 1]


def test_long_wait_rule_in_every_session_system_prompt(env):
    from radark.prompts import STANDING_RULE, long_wait_rule
    for kw in ({}, {"resume": "sess-abc"}):
        text = system_prompt(env, **kw)
        assert text == STANDING_RULE + "\n\n" + long_wait_rule(20)
        assert "ended after 20 minutes" in text and "every 10 minutes" in text
        text = system_prompt(env, idle=30.0, **kw)
        assert STANDING_RULE in text and "ended after 30 minutes" in text and "every 15 minutes" in text
