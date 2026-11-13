# Proposal: sessions check their long waits

Handover: **HO-20261113-ln4m** (backlog item RB-004), from `radark-product`. Based on the product team's draft
`harness-check-long-waits`, updated to the current code (package `radark`) and with the private details removed.

## Why

A session waiting silently on a full end-to-end test run was ended by the inactivity limit after 42 minutes, close to
the end of the run. The run had almost finished, but the session was lost and counted as no progress. Today a worker
that starts a long command and waits for it without output (a blocking call, a background task it waits on, a sleep
loop) makes no stream event other than tool heartbeats, so `session_idle_minutes` (20 by default) ends it. A silent
wait can also hide a real hang. The owner wants the worker to check its long waits itself and spot a hang, rather
than have the dispatcher count a background wait as activity.

## What Changes

- Every session the dispatcher starts (new and resumed) gets a **long-wait rule** in its system prompt, next to the
  standing rule. It says: never wait silently on a command or a background task for longer than a check interval;
  run long commands so that they can be checked, and check their progress at least once per interval (latest
  output, a progress counter, whether the process is alive); if two checks in a row show no progress, treat it as
  hung: stop it, record what was seen, and continue another way or report it.
- The check interval is half the inactivity limit, rounded down to whole minutes, at least 1 minute (10 minutes with
  the default 20). It follows `loop.session_idle_minutes`, so the prompt and the limit cannot drift apart; the rule
  names both numbers.
- The inactivity limit itself and what counts as activity are unchanged. A background wait still does not count as
  activity.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: *Phase prompts*: every session also carries the long-wait rule, with the check interval
  taken from the inactivity limit.

## Impact

- `radark/prompts.py`: a new `long_wait_rule(idle_minutes)` built from the inactivity limit.
- `radark/runner.py`: `Runner.command()` appends it to `STANDING_RULE` in `--append-system-prompt` for every session.
- `radark/README.md`: the inactivity-limit text ("Time limits") names the rule and the interval formula.
- Tests in `radark/tests` for the text and the command line.
- No config, hub or team-repository changes.
