# Proposal

## Why

On 2026-11-10 the app apply session for HO-20261110-7lmg (BL-142) started a full e2e run (283 tests) and then waited for it without any output. After 20 silent minutes the dispatcher's inactivity limit ended the session (42 min in total). The run had almost finished, but the session was lost and counted as no progress (1 of 2 before the item stalls). A silent wait can also hide a real hang. The owner wants the worker to check its long waits itself and spot a hang, rather than have the dispatcher count a background wait as activity.

## What Changes

- Every session the dispatcher starts gets a **long-wait rule** next to the standing rule. It says: never wait silently on a command or background task for longer than a check interval (half the inactivity limit, 10 min by default). Run long commands so that you can check them, and check their progress at least that often (latest output, progress counter, process alive). If two checks in a row show no progress, treat the command as hung: stop it, record what was seen, and continue another way or report it.
- The interval in the rule follows `loop.session_idle_minutes`, so the prompt and the limit cannot drift apart.
- The inactivity limit itself is unchanged. A background wait still does not count as activity.

## Capabilities

### New Capabilities

### Modified Capabilities
- `harness-dispatcher`: *Phase prompts*: every session also carries the long-wait rule, with the check interval taken from the inactivity limit.

## Impact

- `harness/prompts.py`: a new long-wait rule text built from the inactivity limit.
- `harness/runner.py`: append it to the system prompt of every session, next to `STANDING_RULE`.
- Tests in `harness/tests` for the text and the command line.
- No config, hub or team-repo changes.
