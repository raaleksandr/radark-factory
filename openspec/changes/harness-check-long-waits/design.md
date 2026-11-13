# Design

## Context

`STANDING_RULE` (harness/prompts.py) goes into every phase prompt and, through `--append-system-prompt`, into the system prompt of every session the runner starts, resumes included. Prompt builders have no config. The runner does (`self.cfg.session_idle_minutes`, default 20). The inactivity limit (*Session time limits*) ends a session after 20 min with no stream event other than tool heartbeats. A worker that waits on a background task notification, or on a blocking `until … sleep` loop, makes no events and is cut. See proposal.md for the case that triggered this.

## Goals / Non-Goals

**Goals:** the worker checks its own long waits and stays under the limit; a real hang shows up as an observation, not a silent cut.

**Non-Goals:** changing the inactivity limit; counting background waits as activity (the owner rejected this on 2026-11-10: a background wait can be a dead hang); killing background processes from the dispatcher.

## Decisions

- **D1 — In the system prompt only, built by the runner.** The runner appends `long_wait_rule(idle_minutes)` to `STANDING_RULE` in `--append-system-prompt`. It applies to every session and every resume, and needs no config plumbing into the prompt builders. Alternative: put it in each phase prompt. Rejected, because the prompt builders would need the config, and resumes and idle ask would need separate wiring.
- **D2 — Interval = floor(idle / 2), at least 1 min.** Half the limit leaves room for one missed check before the cut. A fixed "10 min" text was rejected because it drifts from the config.
- **D3 — Two checks without progress mean hung.** One quiet check can be normal (a slow test). Two in a row is about the same silence the dispatcher would cut anyway, but the worker sees it first and can say what hung.
- **D4 — Plain words, no tool names.** The rule says "check its latest output, a progress counter, whether the process is alive" and does not name Monitor or Bash, so it fits every team's tools.

## Risks / Trade-offs

- [Workers check too often and waste turns] → the interval is 10 min by default, and the rule says "at least once per interval", not more often.
- [A worker ignores the rule] → the inactivity limit still cuts it as before; nothing gets worse.
