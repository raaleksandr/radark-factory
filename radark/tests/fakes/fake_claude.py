"""Fake `claude`: plays the next scenario from FAKE_CLAUDE_SCENARIOS (a JSON list) and runs the real
hooks named in the --settings file, so hook scripts and runner are tested together.

Scenario: {"steps": [{"hook": "SessionStart"} | {"hook": "PreToolUse", "input": {...}}
                     | {"hook": "Stop", "input": {...}} | {"hook": "StopFailure", "input": {...}}
                     | {"emit": {...}} | {"text": "..."} | {"sleep": s} (a silent stream)
                     | {"usage": {window: [utilization, resets_at]}, "status": "allowed"} (a rate_limit_event)
                     | {"active": s, "every": i} (an assistant event every i seconds for s seconds)
                     | {"heartbeats": s, "every": i} (a tool_progress heartbeat every i seconds: a hung tool call)
                     | {"cmd": [argv...]} (run in the repository) | {"write": [relative path, text]}
                     | {"ho": [args...]} (the fake `ho` as this session's team, e.g. a `new` handover)],
           "result": {...} | null, "exit": 0}
A Stop hook that blocks is recorded in the stream as {"type": "fake_hook", ...}.
Each call (argv, cwd, selected env) is appended to FAKE_CLAUDE_SCENARIOS + ".calls"."""
import json
import os
import subprocess
import sys
import time

argv = sys.argv[1:]
base = os.environ["FAKE_CLAUDE_SCENARIOS"]
if argv == ["--version"]:
    print("9.9.9 (Fake Claude)")
    sys.exit(0)
with open(base + ".calls", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": argv, "cwd": os.getcwd(),
                         "env": {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "HARNESS_TEAM", "HARNESS_HANDOVER",
                                                                "HARNESS_SESSION", "HARNESS_RUN_ID", "HO_TEAM", "TEMP", "TMP",
                                                                "TMPDIR", "HARNESS_TEMP", "HARNESS_SYSTEM_TEMP",
                                                                "HARNESS_REPO")}}) + "\n")
counter = base + ".n"
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
scenarios = json.load(open(base, encoding="utf-8"))
scenario = scenarios[min(n, len(scenarios) - 1)]
settings = json.load(open(argv[argv.index("--settings") + 1], encoding="utf-8"))
session = argv[argv.index("--session-id") + 1] if "--session-id" in argv else argv[argv.index("--resume") + 1]


def out(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def rate_limit_event(windows, status="allowed"):
    """The shape Claude Code 2.1.302 writes; the first window is the top-level `rateLimitType`."""
    first = next(iter(windows))
    return {"type": "rate_limit_event", "rate_limit_info": {
        "status": status, "resetsAt": windows[first][1], "rateLimitType": first,
        "overageStatus": "rejected", "isUsingOverage": False,
        "unifiedWindows": {w: {"utilization": u, "resetsAt": t} for w, (u, t) in windows.items()}}}


def run_hook(name, payload):
    for group in settings["hooks"].get(name, []):
        for h in group["hooks"]:
            p = subprocess.run([h["command"], *h["args"]], input=json.dumps(payload).encode(), capture_output=True)
            text = p.stdout.decode().strip()
            if text:
                out({"type": "fake_hook", "hook": name, "output": json.loads(text)})


out({"type": "system", "subtype": "init", "session_id": session})
for step in scenario.get("steps", []):
    if "hook" in step:
        payload = {"session_id": session, "hook_event_name": step["hook"], **step.get("input", {})}
        run_hook(step["hook"], payload)
    elif "usage" in step:
        out(rate_limit_event(step["usage"], step.get("status", "allowed")))
    elif "emit" in step:
        out(step["emit"])
    elif "text" in step:
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": step["text"]}]}})
    elif "sleep" in step:
        time.sleep(step["sleep"])
    elif "ho" in step:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_ho.py"),
                        *step["ho"]], capture_output=True, check=True)
    elif "cmd" in step:
        subprocess.run(step["cmd"], capture_output=True, check=True)
    elif "write" in step:
        os.makedirs(os.path.dirname(os.path.abspath(step["write"][0])), exist_ok=True)
        with open(step["write"][0], "w", encoding="utf-8") as fh:
            fh.write(step["write"][1])
    elif "active" in step or "heartbeats" in step:
        end = time.monotonic() + step.get("active", step.get("heartbeats"))
        while time.monotonic() < end:
            if "active" in step:
                out({"type": "assistant", "message": {"content": [{"type": "text", "text": "still working"}]}})
            else:
                out({"type": "tool_progress", "tool_name": "Bash", "heartbeat": True, "elapsed_time_seconds": 30})
            time.sleep(step.get("every", 0.2))
if scenario.get("result", {}) is not None:
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": "", "permission_denials": [], **scenario.get("result", {})})
sys.exit(scenario.get("exit", 0))
