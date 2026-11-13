# Design: check long waits

Handover: HO-20261113-ln4m.

## Context

`STANDING_RULE` (`radark/prompts.py`) goes into every phase prompt and, through `--append-system-prompt` in
`Runner.command()` (`radark/runner.py`), into the system prompt of every session the runner starts, resumes
included. The prompt builders have no config; the runner has it (`self.cfg.session_idle_minutes`, a float, default
20, must be positive). The inactivity limit (*Session time limits*) ends a session when its stream carries nothing but
`tool_progress` heartbeats for that long, so one tool call longer than the limit is ended too. A worker that waits on a
background task notification, on a long blocking command, or on a blocking sleep loop makes no events and is cut. See
proposal.md for the case that triggered this.

## Goals / Non-Goals

**Goals:** the worker checks its own long waits and stays under the limit; a real hang shows up as an observation,
not a silent cut.

**Non-Goals:** changing the inactivity limit; counting background waits as activity (the owner rejected this: a
background wait can be a dead hang); killing background processes from the dispatcher.

## Decisions

- **D1: in the system prompt only, built by the runner.** `Runner.command()` passes
  `STANDING_RULE + "\n\n" + long_wait_rule(cfg.session_idle_minutes)` to `--append-system-prompt`. It applies to every
  session and every resume (and so also to triage consultations, limit checks, goal checks and idle asks, where it is
  harmless), and needs no config plumbing into the prompt builders. Alternative: put it in each phase prompt.
  Rejected, because the prompt builders would need the config, and resumes and idle asks would need separate wiring.
  `STANDING_RULE` in the phase prompts stays as it is.
- **D2: interval = max(1, floor(limit / 2)) whole minutes.** Half the limit leaves room for one missed check before
  the cut. A fixed "10 min" text was rejected because it drifts from the config. `session_idle_minutes` is a float:
  the interval is always a whole number of minutes, rounded down (25 → 12, 2.5 → 1, 1 → 1, 20 → 10, 30 → 15). The
  limit is written as configured without a trailing `.0` (`20` for 20.0, `2.5` for 2.5; the `:g` format).
  For a limit under 2 minutes the 1-minute floor is at or above half the limit; such limits are not a realistic
  configuration and the floor keeps the text sensible (assumption, recorded here instead of asking).
- **D3: two checks without progress mean hung.** One quiet check can be normal (a slow test). Two in a row is about the
  same silence the dispatcher would cut anyway, but the worker sees it first and can say what hung.
- **D4: plain words, no tool names.** The rule says "check its latest output, a progress counter, whether the process
  is alive" and does not name Monitor or Bash, so it fits every team's tools. It does say that a running command does
  not count as output, because a long blocking tool call is cut by the limit just like a background wait (an addition
  to the draft, which only spoke of background waits).
- **D5: rule text.** With the default limit the rule reads:

  > Long waits: this session is ended after 20 minutes without output from you (a running command does not count as
  > output). Never wait silently on a command or a background task for longer than 10 minutes: run long commands so
  > that you can check them, and check their progress at least once every 10 minutes (its latest output, a progress
  > counter, whether the process is alive). If two checks in a row show no progress, treat it as hung: stop it, record
  > what was seen, and continue another way or report it.

  Apply may adjust the wording, but it must keep the elements of the spec paragraph and both numbers.

## Risks / Trade-offs

- [Workers check too often and waste turns] → the interval is 10 min by default, and the rule says "at least once
  per interval", not more often.
- [A worker ignores the rule] → the inactivity limit still cuts it as before; nothing gets worse.
- [A longer system prompt for every session] → one short paragraph; negligible.
