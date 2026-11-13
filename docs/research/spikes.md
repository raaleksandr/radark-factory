# Spikes

Hands-on checks behind the `harness-selection` decision (its tasks 4.2–4.3).

## First-party finalist: own Python dispatcher + `claude -p` + hooks (2026-10-17)

Run as the sandbox verification of the `add-python-harness` change (tasks 5.1–5.6) on a throw-away hub and two
throw-away team repositories created by `harness/sandbox/make_sandbox.py`; Claude Code 2.1.302, Windows 11,
the owner's Max login. Full results and deviations: `harness/README.md` → *Verification results*.

| Design D4 check / must-have | Result |
|---|---|
| Start a session in a given directory | yes — `claude -p` with the team repository as working directory; CLAUDE.md, skills and OpenSpec commands load |
| `PreToolUse` hook denying `AskUserQuestion` in headless mode | not testable: `AskUserQuestion` is not offered in `-p` (with or without `--permission-prompts none`). Questions arrive as plain text and are caught by the `Stop` hook |
| `Stop` hook continuing without an endless loop | yes — one nudge, then `stop_hook_active` lets the session end |
| Auto-answer an agreed stop | yes — plain-text questions referred to a read-only `product` consultation (`technical` / `product` verdicts) and the session resumed with the answer; risky ("push") questions escalated |
| Detect session end and outcome | yes — exit code + final `result` event + hook markers; a real usage-limit hit was classified `usage_limit` |
| Read `ho inbox --json` | yes — selection, review and archive gate across a full propose → apply → done → close → archive cycle, one session per phase |
| `SendMessage` to another terminal / desktop session | not tested (shape B not pursued) |
| Plan usage of an idle dispatcher | zero by construction: the dispatcher polls `ho` only and starts no session when idle (idle ask is off by default) |

Session durations: propose 64 s, apply 36 s, review 45 s, archive 49 s, consultation 12–15 s.
