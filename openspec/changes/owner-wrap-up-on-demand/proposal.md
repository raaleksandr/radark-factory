# Proposal: wrap up on demand ("finish the current command, save the work, stop")

Handover: **HO-20261120-z32m** (RB-033, "wrap up on demand - finish the current command, save the work, stop"), from
`radark-product`, asked by the owner on 2026-11-20.

## Why

The owner wants to start a run without an end time and later tell it "finish what you are doing right now, save the
work and stop", without a hard interrupt. Today `STOP` / `PAUSE` stop only new starts (a running apply phase goes on
for 1-3 hours), and `--until WHEN --until-strict` needs the time at the start and kills the running command (often a
long test run whose result is then lost).

## What Changes

- New owner request **wrap-up on demand**: command `radark wrap-up [--within MIN]` (with `--config` like every
  command), or a `WRAP_UP` file in the run directory next to `PAUSE` / `STOP`. The command writes the file; the file
  may also be created by hand (then without `--within`). Without a running dispatcher for that configuration the
  command writes nothing and says so (exit 1).
- Once the running dispatcher sees the request (between sessions, during waits and about every second while sessions
  run):
  1. no new step starts (as with `STOP`); a wait (poll, `PAUSE`, usage wait, back-off) ends at once;
  2. every running **work session** gets the wrap-up request **after the tool call it is in** has finished: a new
     `PostToolUse` hook adds the request to the session's context; a session that ends its turn first gets it from
     the `Stop` hook instead of the "continue" nudge. The text is the end-time wrap-up's: start no new work (wait for
     a command it started in the background, e.g. a test run, and use its result), commit what works, for apply check
     off finished tasks and write the open ones under `Left for a later run` in `tasks.md`, no `ho done` unless the
     phase is complete;
  3. the session is **not killed while its command runs**. Safety limits: the normal `session_idle_minutes` /
     `session_max_minutes` rules stay; after the request no limit check and no extension is given; once delivered the
     session has `wrap_up_minutes` to end, then it is stopped; with `--within MIN` a session that has not received
     the request MIN minutes after it is stopped and resumed with the wrap-up prompt (the existing hard wrap-up),
     limited to `wrap_up_minutes`;
  4. a session that ends without completing its phase is `interrupted` with the new cause **`owner_wrap_up`** (not
     an error, not "no progress"); the next run resumes it in its own context, as after a strict end time;
  5. the run ends after the last session (exit 0; a goal run ends `stopped`) and removes the `WRAP_UP` file.
- Console / `console.log`: request seen (with the sessions asked), each delivery, each session's end (cause `owner
  wrap-up`), the run's end. `runs.jsonl`: `owner_wrap_up_requested`, `owner_wrap_up_delivered`,
  `owner_wrap_up_stop`, `owner_wrap_up_done`. `status` shows a pending wrap-up; the cockpit **Now** tab shows it on
  the pipeline's card.
- A `WRAP_UP` file present when a run starts is left from an earlier run: removed with a console note.
- `STOP`, `PAUSE`, `--until` and `--until-strict` keep their behaviour.
- `radark/README.md` (commands, **Pause / stop**, **Wrap-up**) and `README.md` (run control line) updated.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `harness-dispatcher`: new requirements *Wrap-up on demand*, *Requesting a wrap-up on demand*, *Wrap-up request without a
  running run*, *Delivering a wrap-up on demand between
  tool calls*, *Wrap-up on demand text*, *Safety limits of a wrap-up on demand*,
  *Limit for reaching the sessions*, *Outcome of a session wrapped up on
  demand*, *Reporting a wrap-up on demand*.
- `owner-cockpit`: new requirement *Now pending wrap-up*.

## Impact

- `radark/hooks/post_tool_use.py` (new) and `radark/hooks/stop.py`; `radark/runner.py`: the `PostToolUse` hook in the
  session settings, a per-tick callback in `Runner.run`; cause `owner_wrap_up`.
- `radark/__main__.py`: `wrap-up` command, request detection, stopping new starts, delivery watch and safety limits
  per session, outcome, run end, `status` line, console texts.
- `radark/prompts.py`: on-demand wrap-up text (shared with the end-time wrap-up), `INTERRUPT_LABELS["owner_wrap_up"]`.
- `radark/cockpit_now.py`: the pending wrap-up on a card.
- Tests: new `radark/tests/test_owner_wrap_up.py`; fake `claude` gets a `PostToolUse` step that waits for a file the
  test controls (a long tool call without real waits).
- No change to the hub, the `ho` contract, the selection or the state format beyond the new cause.
