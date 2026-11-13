"""Loop, post-session update, triage and owner commands with fake `ho` and `claude` (tasks 4.2–4.6)."""
import json
import os

import pytest

from radark.__main__ import Dispatcher, Lock, main
from radark.tests.conftest import ASK_STEP, START, item, show, stop_step

A = "HO-20261016-aaaa"
LATER = "2099-01-01T00:00:00.000Z"  # an event newer than any session start


def disp(env):
    return Dispatcher(env.cfg(), out=lambda *a: None)


def log_events(env):
    return [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


def hub_with_new_task(events=()):
    return {"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A, events)}


def test_propose_records_change_and_progress(env):
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    env.set_claude([{"steps": [START, {"text": "Created.\nCHANGE: add-export"}], "result": {"result": "Created.\nCHANGE: add-export"}}])
    d = disp(env)
    assert d.loop(once=True) == 0
    rec = d.state.get(A)
    assert (rec["change"], rec["phase"], rec["no_progress"]) == ("add-export", "propose", 0)
    assert rec["sessions"][0]["outcome"] == "finished"
    kinds = [e["event"] for e in log_events(env)]
    assert kinds == ["session_start", "session_end"]
    start = log_events(env)[0]
    assert start["team"] == "app" and start["handover"] == A and start["phase"] == "propose"
    assert A in start["prompt"] and start["repo"].endswith("app")


def test_change_name_fallback_search(env):
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    change = env.root / "repos" / "app" / "openspec" / "changes" / "add-thing"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text(f"Implements {A}.")
    env.set_claude([{"steps": [START], "result": {"result": "Created the change."}}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.get(A)["change"] == "add-thing"


# ---- propose that created no change (rerun-propose-without-change)

def test_propose_cut_before_the_change_proposes_again(env):
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    env.set_claude([{"steps": [START], "result": None, "exit": 1}])
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.loop(once=True)
    rec = d.state.get(A)
    assert rec["sessions"][0]["outcome"] == "error"
    assert (rec["change"], rec["phase"], rec["no_progress"]) == (None, None, 0)
    (event,) = [e for e in log_events(env) if e["event"] == "propose_without_change"]
    assert (event["team"], event["handover"], event["outcome"]) == ("app", A, "error")
    assert event["session"] == rec["sessions"][0]["id"]
    assert any(f"app {A}: propose created no OpenSpec change; the next session is propose again" in x
               for x in lines)
    (cand,) = d.plan()
    assert (cand.handover, cand.phase) == (A, "propose")


def test_failed_propose_with_a_change_in_the_repository_goes_to_apply(env):
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    change = env.root / "repos" / "app" / "openspec" / "changes" / "fix-scroll"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text(f"Implements {A}.")
    env.set_claude([{"steps": [START], "result": None, "exit": 1}])
    d = disp(env)
    d.loop(once=True)
    rec = d.state.get(A)
    assert (rec["change"], rec["phase"]) == ("fix-scroll", "propose")
    assert "propose_without_change" not in [e["event"] for e in log_events(env)]
    (cand,) = d.plan()
    assert (cand.phase, cand.change) == ("apply", "fix-scroll")


def test_repeated_propose_without_change_or_progress_stalls(env):
    env.set_hub(hub_with_new_task())
    env.set_claude([{"steps": [START], "result": None, "exit": 1}])
    d = disp(env)
    d.loop(once=True)
    d.loop(once=True)
    assert [c["phase"] for c in d.state.get(A)["sessions"]] == ["propose", "propose"]
    assert d.state.get(A)["flags"]["stalled"]
    kinds = [e["event"] for e in log_events(env)]
    assert kinds.count("propose_without_change") == 2 and "stalled" in kinds


@pytest.mark.parametrize("outcome,reason", [("interrupted", None), ("error", "max_time")])
def test_cut_propose_without_change_resumes_as_propose(env, outcome, reason):
    from radark.runner import SessionResult
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    d = disp(env)
    (cand,) = d.plan()
    rec = d.state.ensure(A, "app")
    r = SessionResult(run_id="run-1", session_id="sess-cut", team="app", handover=A, phase="propose",
                      started="2026-10-26T10:00:00.000Z", outcome=outcome, progress_sources=["hub"],
                      interrupt_cause="sleep" if outcome == "interrupted" else None, timeout_reason=reason)
    d.after_session(cand, rec, r)
    assert rec["phase"] is None and rec["resume_after_timeout"]["phase"] == "propose"
    (cand,) = d.plan()
    assert (cand.phase, cand.resume_session) == ("propose", "sess-cut")


def test_done_moves_record_to_done(env):
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]},
                 f"show:{A}": show(A, [(LATER, "app", "done", "ok")])})
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    d.loop(once=True)
    assert d.state.get(A)["phase"] == "done"
    assert "Implement the OpenSpec change `add-x`" in log_events(env)[0]["prompt"]


def test_two_sessions_without_progress_stall(env):
    env.set_hub(hub_with_new_task())
    env.set_claude([{"steps": [START], "result": {"result": "Thinking."}}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 1 and not d.state.blocked(A)
    d.loop(once=True)
    assert d.state.get(A)["flags"]["stalled"]
    assert "stalled" in [e["event"] for e in log_events(env)]
    calls = len(env.claude_calls())
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls  # nothing selectable any more


def test_risky_question_escalates_and_clear_restores(env, capsys):
    env.set_hub(hub_with_new_task())
    risky = {"hook": "PreToolUse", "input": {"tool_name": "AskUserQuestion",
                                              "tool_input": {"questions": [{"question": "Push to the remote?"}]}}}
    env.set_claude([{"steps": [START, risky, stop_step("The owner must decide whether to push.")], "result": {}}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.get(A)["flags"]["escalated"]
    assert [e["event"] for e in log_events(env)].count("escalation") == 2  # the hook marker and the item escalation
    assert main(["--config", str(env.config_path), "escalations"]) == 0
    assert A in capsys.readouterr().out
    assert main(["--config", str(env.config_path), "clear", A]) == 0
    assert not disp(env).state.blocked(A)


def test_usage_limit_starts_backoff(env):
    """No usage reading with a future reset: the doubling back-off (usage-limit-guard D4 fallback)."""
    env.set_hub(hub_with_new_task())
    env.set_claude([{"steps": [START, {"hook": "StopFailure", "input": {"error": "rate_limit"}}], "exit": 1}])
    d = disp(env)
    d.loop(once=True)
    assert d.state.meta["backoff_minutes"] == 30 and "usage_wait" not in d.state.meta
    calls = len(env.claude_calls())
    assert d.loop(once=True) == 0 and len(env.claude_calls()) == calls
    d.start_backoff()
    assert d.state.meta["backoff_minutes"] == 60


def test_hooks_not_loaded_stops_loop(env):
    env.set_hub(hub_with_new_task())
    env.set_claude([{"steps": [], "result": {"result": "ok"}}])
    assert disp(env).loop(once=False) == 3
    assert "hooks_not_loaded" in [e["event"] for e in log_events(env)]


def test_stop_and_pause_files(env):
    env.set_hub(hub_with_new_task())
    run = env.root / "run"
    run.mkdir(exist_ok=True)
    (run / "STOP").write_text("")
    assert disp(env).loop() == 0
    assert env.claude_calls() == []


def test_dry_run_starts_nothing(env, capsys):
    env.set_hub(hub_with_new_task())
    assert main(["--config", str(env.config_path), "dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Would start: app" in out and "phase propose" in out and A in out
    assert [c for c in env.claude_calls() if c["argv"] != ["--version"]] == []
    assert all(c["args"][0] in ("--version", "inbox", "show", "list", "teams") for c in env.ho_calls())


def test_lock_refuses_second_instance_and_replaces_stale(env, tmp_path):
    lock = Lock(tmp_path / "lock")
    lock.acquire()
    with pytest.raises(SystemExit, match="holds"):
        Lock(tmp_path / "lock").acquire()
    lock.release()
    (tmp_path / "lock").write_text("999999")
    Lock(tmp_path / "lock").acquire()
    assert (tmp_path / "lock").read_text() == str(os.getpid())


def test_keep_session_resumes_previous(env):
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]},
                 f"show:{A}": show(A, [(LATER, "app", "comment", "progress")])})
    d = disp(env)
    rec = d.state.ensure(A, "app")
    rec.update(change="add-x", phase="propose")
    rec["sessions"].append({"id": "sess-prop", "team": "app", "phase": "propose"})
    d.state.save()
    assert main(["--config", str(env.config_path), "keep", A]) == 0
    env.set_claude([{"steps": [START], "result": {}}])
    disp(env).loop(once=True)
    argv = env.claude_calls()[0]["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-prop"


def test_archive_after_close(env):
    env.set_hub({f"show:{A}": show(A, [("2026-10-16T10:00:00.000Z", "app", "done", "ok"),
                                        ("2026-10-16T11:00:00.000Z", "product", "close", "")], status="closed")})
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="done")
    d.state.save()
    env.set_claude([{"steps": [START], "result": {"result": "Archived."}}])
    d.loop(once=True)
    assert "/opsx:archive" in log_events(env)[0]["prompt"]
    assert d.state.get(A)["phase"] == "archived"  # the change directory does not exist (any more)


def test_idle_ask_once_per_new_activity(env):
    env.cfg_text = env.config_path.read_text()
    env.config_path.write_text(env.cfg_text.replace("[loop]", "[loop]\nidle_ask = true"))
    env.set_hub({"list:product": {"items": [{"id": A, "last_activity": "2026-10-16T10:00:00.000Z"}]}})
    env.set_claude([{"steps": [START], "result": {"result": "none"}}])
    d = disp(env)
    d.loop(once=True)
    d.loop(once=True)
    assert len(env.claude_calls()) == 1
    assert env.claude_calls()[0]["cwd"].endswith("product")
    assert [e["event"] for e in log_events(env)].count("idle_ask") == 1


# ---- product triage (design D10)

def triage_run(env, verdict, resume=True):
    env.set_hub(hub_with_new_task([(LATER, "app", "ack", "")]))
    scenarios = [{"steps": [START, ASK_STEP, stop_step("Waiting for the answer.")], "result": {"result": "Referred."}},
                 {"steps": [START], "result": {"result": "", **({"structured_output": verdict} if verdict is not None else {})}}]
    if resume:
        scenarios.append({"steps": [START], "result": {"result": "Continued."}})
    env.set_claude(scenarios)
    d = disp(env)
    d.loop(once=True)
    return d, env.claude_calls()


def test_triage_technical_resumes_with_default(env):
    d, calls = triage_run(env, {"verdict": "technical", "answer": "", "reason": "internal detail"})
    assert len(calls) == 3
    consult = calls[1]["argv"]
    assert calls[1]["cwd"].endswith("product")
    assert consult[consult.index("--tools") + 1] == "Read,Grep,Glob" and "--json-schema" in consult
    assert "Use a Map or a plain object" in consult[1]
    assert calls[1]["env"]["HARNESS_TEAM"] == "product"
    resumed = calls[2]["argv"]
    asked_session = calls[0]["argv"][calls[0]["argv"].index("--session-id") + 1]
    assert resumed[resumed.index("--resume") + 1] == asked_session
    assert "Choose the best variant" in resumed[1] and calls[2]["cwd"].endswith("app")
    tri = [e for e in log_events(env) if e["event"] == "triage"][0]
    assert tri["verdict"]["verdict"] == "technical"
    assert not d.state.blocked(A) and d.state.get(A)["triage_count"] == 1


def test_triage_product_answer(env):
    d, calls = triage_run(env, {"verdict": "product", "answer": "on first install", "reason": "drives activation"})
    msg = calls[2]["argv"][1]
    assert "Product decision: on first install" in msg and "drives activation" in msg and "product decision" in msg


def test_triage_owner_escalates_without_resume(env):
    d, calls = triage_run(env, {"verdict": "owner", "answer": "", "reason": "changes pricing"}, resume=False)
    assert len(calls) == 2 and d.state.get(A)["flags"]["escalated"]
    assert "changes pricing" in d.state.get(A)["reason"]


@pytest.mark.parametrize("verdict", [None, {"verdict": "maybe", "answer": "", "reason": ""},
                                     {"verdict": "product", "answer": "", "reason": "no answer given"}])
def test_triage_malformed_escalates(env, verdict):
    d, calls = triage_run(env, verdict, resume=False)
    assert len(calls) == 2 and d.state.get(A)["flags"]["escalated"]


def test_triage_limit_escalates(env):
    env.set_hub(hub_with_new_task())
    d = disp(env)
    d.state.ensure(A, "app")["triage_count"] = 3
    env.set_claude([{"steps": [START, ASK_STEP], "result": {}}])
    d.loop(once=True)
    assert len(env.claude_calls()) == 1 and d.state.get(A)["flags"]["escalated"]


def test_progress_counts_from_first_session_across_triage(env, monkeypatch):
    """The ack happened in the asking session; the resumed session made no hub change."""
    d, calls = triage_run(env, {"verdict": "technical", "answer": "", "reason": "r"})
    first_start = log_events(env)[0]["time"]
    env.set_hub(hub_with_new_task([(first_start, "app", "ack", "")]))
    d2 = disp(env)
    d2.state.records.clear()
    assert d2.made_progress("app", A, "2000-01-01T00:00:00.000Z") == ["hub"]
    assert d2.made_progress("app", A, LATER) == []


def test_replay_p3uj_change_notes_stall_after_two_sessions(env):
    """2026-10-31 (no-loop N2): each apply session committed only a "still gated" note to the change's tasks.md."""
    import subprocess
    p3 = "HO-20261031-p3uj"
    change = "app-faster-provider"
    repo = env.root / "repos" / "backend"
    tasks = repo / "openspec" / "changes" / change / "tasks.md"
    tasks.parent.mkdir(parents=True)
    tasks.write_text("- [x] 1.1 done\n- [ ] 2.1 paid bench\n", encoding="utf-8")
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                ["add", "-A"], ["commit", "-q", "-m", "start"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    env.set_hub({"inbox:backend": {"action_required": [item(p3, sender="product", my_state="acknowledged")]},
                 f"show:{p3}": show(p3)})
    path = tasks.relative_to(repo).as_posix()
    env.set_claude([{"steps": [START, {"write": [path, f"- [x] 1.1 done\n- [ ] 2.1 paid bench\nre-check {n}\n"]},
                               {"cmd": ["git", "commit", "-q", "-am", "apply re-check, still gated"]}],
                     "result": {"result": "Still gated."}} for n in range(3)])
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    d.state.ensure(p3, "backend").update(change=change, phase="apply")
    d.state.save()
    for _ in range(3):
        d.loop(once=True)
    rec = d.state.get(p3)
    assert len(env.claude_calls()) == 2  # no third session
    assert rec["flags"]["stalled"] and rec["no_progress"] == 2
    assert [e.get("ignored") for e in log_events(env) if e["event"] == "no_progress"] == ["change_notes"] * 2
    assert sum("(commits changed only the change's own files)" in x for x in lines) == 2
    assert [e["reason"] for e in log_events(env) if e["event"] == "stalled"] == ["stalled: 2 sessions without progress"]
    assert [c for c in env.ho_calls() if c["args"][:3] == ["new", "--to", "owner"]]
