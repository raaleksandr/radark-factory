"""Progress from commits and checked tasks; resume after a time limit (design T3, T4)."""
import json
import subprocess
import sys

from radark.__main__ import Dispatcher
from radark.tests.conftest import START, item, show

A = "HO-20261016-aaaa"
TASKS = "## 1. Work\n\n- [ ] 1.1 one\n- [ ] 1.2 two\n- [ ] 1.3 three\n"


def disp(env):
    return Dispatcher(env.cfg(), out=lambda *a: None)


def log_events(env, kind=None):
    events = [json.loads(x) for x in (env.root / "run" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    return [e for e in events if kind is None or e["event"] == kind]


def repo(env):
    return env.root / "repos" / "app"


def git_init(env):
    r = repo(env)
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                ["commit", "-q", "--allow-empty", "-m", "start"]):
        subprocess.run(["git", "-C", str(r), *cmd], check=True, capture_output=True)


def apply_item(env, tasks=None):
    """A handover in apply phase for change add-x, with no hub activity during the session."""
    env.set_hub({"inbox:app": {"action_required": [item(A, my_state="acknowledged")]}, f"show:{A}": show(A)})
    if tasks is not None:
        d = repo(env) / "openspec" / "changes" / "add-x"
        d.mkdir(parents=True, exist_ok=True)
        (d / "tasks.md").write_text(tasks, encoding="utf-8")
    d = disp(env)
    d.state.ensure(A, "app").update(change="add-x", phase="propose")
    d.state.save()
    return d


def limits(env, idle=20, maximum=360, checks=0):
    """Session limits; limit checks off unless `checks` is given (check-session-at-time-limit)."""
    text = env.config_path.read_text()
    env.config_path.write_text(text.replace("[loop]", f"[loop]\nsession_idle_minutes = {idle}\n"
                                                      f"session_max_minutes = {maximum}\nlimit_checks = {checks}"))


def test_work_without_hub_activity_counts(env):
    git_init(env)
    d = apply_item(env)
    d.state.get(A)["no_progress"] = 1
    env.set_claude([{"steps": [START, *committed(("src/a.py", "x = 1\n"), msg="one"),
                               *committed(("src/a.py", "x = 2\n"), msg="two")],
                     "result": {"result": "Partly done."}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0
    assert log_events(env, "session_end")[0]["progress_sources"] == ["commits"]
    assert d.state.get(A)["sessions"][0]["base"]["heads"]


def test_checked_tasks_count(env):
    d = apply_item(env, TASKS)
    done = TASKS.replace("- [ ]", "- [x]")
    env.set_claude([{"steps": [START, {"write": ["openspec/changes/add-x/tasks.md", done]}], "result": {}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0
    assert log_events(env, "session_end")[0]["progress_sources"] == ["tasks"]


def test_agent_going_in_circles(env):
    """Uncommitted edits and unchanged tasks are not progress: two such sessions stall the item."""
    git_init(env)
    d = apply_item(env, TASKS)
    env.set_claude([{"steps": [START, {"write": ["notes.txt", "again"]}], "result": {"result": "Thinking."}}])
    d.loop(once=True)
    d.loop(once=True)
    rec = d.state.get(A)
    assert rec["flags"]["stalled"] and rec["no_progress"] == 2
    assert [e["progress_sources"] for e in log_events(env, "session_end")] == [[], []]


def test_reset_branch_is_not_progress(env):
    git_init(env)
    subprocess.run(["git", "-C", str(repo(env)), "commit", "-q", "--allow-empty", "-m", "second"], check=True)
    d = apply_item(env)
    env.set_claude([{"steps": [START, {"cmd": ["git", "reset", "-q", "--hard", "HEAD~1"]}], "result": {}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 1


def test_continue_after_a_limit(env):
    git_init(env)
    limits(env, maximum=0.05)  # 3 s
    d = apply_item(env)
    env.set_claude([{"steps": [START, *committed(("src/a.py", "one\n"), msg="part one"), {"active": 30, "every": 0.2}],
                     "result": {}},
                    {"steps": [START, {"cmd": [sys.executable, "-c", "import os; os.remove('.git/index.lock')"]},
                               *committed(("src/a.py", "two\n"), msg="part two")], "result": {"result": "Finished."}}])
    d.loop(once=True)
    rec = d.state.get(A)
    first = rec["sessions"][0]["id"]
    end = log_events(env, "session_end")[0]
    assert (end["outcome"], end["timeout_reason"], end["progress_sources"]) == ("error", "max_time", ["commits"])
    assert rec["no_progress"] == 0 and rec["resume_after_timeout"]["session"] == first
    (repo(env) / ".git" / "index.lock").write_text("")
    d = disp(env)
    d.loop(once=True)
    call = env.claude_calls()[1]["argv"]
    assert call[call.index("--resume") + 1] == first
    msg = call[1]
    assert "`max_time`" in msg and "git status" in msg and "(one exists now)" in msg and f"ho done {A}" in msg
    assert log_events(env, "resume_after_timeout")[0]["session"] == first
    assert log_events(env, "stale_index_lock")
    rec = d.state.get(A)
    assert "resume_after_timeout" not in rec and rec["no_progress"] == 0


def test_timeout_without_progress(env):
    git_init(env)
    limits(env, idle=0.03)  # 1.8 s
    d = apply_item(env)
    env.set_claude([{"steps": [START, {"sleep": 30}], "result": {}},
                    {"steps": [START], "result": {}}])
    d.loop(once=True)
    rec = d.state.get(A)
    assert log_events(env, "session_end")[0]["timeout_reason"] == "idle_timeout"
    assert rec["no_progress"] == 1 and "resume_after_timeout" not in rec
    d.loop(once=True)
    argv = env.claude_calls()[1]["argv"]
    assert "--resume" not in argv and "Implement the OpenSpec change `add-x`" in argv[1]
    assert d.state.get(A)["flags"]["stalled"]


def test_failed_timeout_resume_starts_fresh(env):
    d = apply_item(env)
    d.state.get(A)["resume_after_timeout"] = {"session": "sess-cut", "team": "app", "phase": "apply",
                                              "reason": "max_time", "duration_s": 600}
    d.state.save()
    env.set_claude([{"steps": [START], "result": None, "exit": 1},
                    {"steps": [START], "result": {"result": "Done."}}])
    d = disp(env)
    d.loop(once=True)
    first, second = (c["argv"] for c in env.claude_calls())
    assert first[first.index("--resume") + 1] == "sess-cut" and "10 min" in first[1]
    assert "--session-id" in second and "Implement the OpenSpec change `add-x`" in second[1]
    assert "resume_after_timeout" not in d.state.get(A)


# ---- harness-no-loop-while-blocked N2: commits only inside the change do not count

NOTE = "openspec/changes/add-x/tasks.md"


def committed(*writes, msg="note"):
    """Steps: write the files, then commit them all."""
    return [{"write": [path, text]} for path, text in writes] + [
        {"cmd": ["git", "add", "-A"]}, {"cmd": ["git", "commit", "-q", "-m", msg]}]


def tracked(env):
    git_init(env)
    subprocess.run(["git", "-C", str(repo(env)), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo(env)), "commit", "-q", "-m", "change"], check=True, capture_output=True)


def test_commit_to_the_change_only_is_no_progress(env):
    d = apply_item(env, TASKS)
    tracked(env)
    env.set_claude([{"steps": [START, *committed((NOTE, TASKS + "\nre-check: still pending\n"))],
                     "result": {"result": "Still waiting."}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 1
    assert log_events(env, "session_end")[0]["progress_sources"] == []
    [event] = log_events(env, "no_progress")
    assert event["ignored"] == "change_notes"


def test_change_notes_with_real_work_count(env):
    d = apply_item(env, TASKS)
    tracked(env)
    env.set_claude([{"steps": [START, *committed((NOTE, TASKS + "\nnote\n"), ("tests/test_x.py", "def test(): pass\n"))],
                     "result": {}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0
    assert log_events(env, "session_end")[0]["progress_sources"] == ["commits"]
    assert log_events(env, "no_progress") == []


def test_checked_tasks_in_a_change_commit_still_count(env):
    d = apply_item(env, TASKS)
    tracked(env)
    env.set_claude([{"steps": [START, *committed((NOTE, TASKS.replace("- [ ] 1.1", "- [x] 1.1")))], "result": {}}])
    d.loop(once=True)
    assert d.state.get(A)["no_progress"] == 0
    assert log_events(env, "session_end")[0]["progress_sources"] == ["tasks"]


def test_propose_commit_to_its_change_still_counts(env):
    """Other phases are unchanged: a propose that commits only its change's files makes progress."""
    git_init(env)
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    d = disp(env)
    env.set_claude([{"steps": [START, *committed(("openspec/changes/add-x/proposal.md", "# Proposal\n"))],
                     "result": {"result": "Proposed.\nCHANGE: add-x"}}])
    d.loop(once=True)
    assert log_events(env, "session_end")[0]["progress_sources"] == ["commits"]
    assert d.state.get(A)["no_progress"] == 0



def test_made_progress_without_a_change_counts_commits(env):
    """An apply item without a known change: any new commit counts, as before."""
    from radark.__main__ import snapshot
    git_init(env)
    env.set_hub({f"show:{A}": show(A)})
    d = disp(env)
    base = snapshot(repo(env), None)
    subprocess.run(["git", "-C", str(repo(env)), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    ignored = []
    assert d.made_progress("app", A, "2026-10-16T09:00:00.000Z", base, phase="apply",
                           ignored=ignored) == ["commits"]
    assert ignored == []


def test_hub_timeout_in_the_progress_check_is_a_problem_line(env):
    """harness-survive-sleep D5: `ho show` with no answer is an ordinary hub error; the loop goes on."""
    from radark.hub import HoTimeout
    env.set_hub({"inbox:app": {"action_required": [item(A)]}, f"show:{A}": show(A)})
    env.set_claude([{"steps": [START], "result": {"result": "Done."}}])
    lines = []
    d = Dispatcher(env.cfg(), out=lines.append)
    real_show = d.hub.show

    def show_after_session(hid, team=None):
        if env.claude_calls():
            raise HoTimeout("no answer within 120 s")
        return real_show(hid, team=team)

    d.hub.show = show_after_session
    assert d.loop(once=True) == 0
    assert any(x.endswith(f"  ! ho show {A} failed: no answer within 120 s") for x in lines)
    assert log_events(env, "session_end")
