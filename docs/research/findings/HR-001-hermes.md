# HR-001 findings — Hermes

[Brief](../briefs/HR-001-hermes.md) · [Report](../reports/HR-001-hermes.md) · summarised 2026-10-29 (late intake: the
decision had already been acted on in `add-python-harness`; see [decision 0001](../../decisions/0001-orchestration-harness.md)).

## What the report establishes

- **Identity (high, project repository and docs):** "Hermes" here is **Hermes Agent** by Nous Research
  (`NousResearch/hermes-agent`), an MIT-licensed Python personal-agent runtime, first released 25 Feb 2026, v0.22.2 on
  15 Oct 2026. Community add-ons (oh-my-hermes, hermes-code-bridge) share its limitations.
- **Driving Claude Code (high):** a bundled `claude-code` skill lets Hermes' own LLM run `claude -p` through a shell tool,
  or screen-scrape interactive sessions through tmux, which native Windows lacks. Hermes wires none of Claude Code's
  control points (`--permission-prompt-tool`, hooks, stream-json denials).
- **Fit (medium):** fails *Answers pre-agreed stops*; only partly meets *Drives Claude Code sessions* (print mode on
  Windows), *One agent at a time* (no global lock) and *Observable and stoppable* (child-process handling on stop
  undocumented). The glue we would still write is about 500 lines — the size of a standalone script.
- **Data and accounts (high for providers):** works with OpenRouter and custom endpoints, but needs a model with
  ≥ 64k context, has no spend cap of its own, and its model sees whole terminal output and memory — more than "stop
  text, team, handover ID". Its `claude-subscription-directsdk` plugin runs Hermes' loop on a Pro/Max login, which
  Anthropic's legal page forbids for third-party tools.
- **Maturity (medium-high):** very fast release cadence (several patches a month, a mis-built release in October) — a
  stability risk for a control loop.

## Sources and dates

Hermes Agent repository, docs and release notes (read 15 Oct 2026); Anthropic Claude Code legal and compliance page and
Agent SDK overview (Oct 2026); The New Stack (16 Jun 2026). Star and contributor counts are third-party snapshots.

## Candidate score (provisional, from the report)

| Requirement | Hermes Agent |
|---|---|
| Drives Claude Code sessions | partly |
| Harness model access separate | partly |
| Wakes the team a handover is waiting for | partly |
| Answers pre-agreed stops | not met |
| One agent at a time | partly / unknown |
| Fresh session per phase | met (through Claude Code flags) |
| Archive only after approval | not met natively |
| Observable and stoppable | partly |

## Still unknown

Hermes' behaviour on native Windows with our `claude` install and orphaned processes on `/stop`. No follow-up: Hermes is
eliminated on a must-have, so the gaps do not affect the decision.
