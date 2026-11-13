# 0001 — Orchestration harness: our own Python dispatcher over `claude -p`

- **Status:** accepted — approved by the owner on 2026-10-29
- **Date:** 2026-10-29 (the choice was acted on from 2026-10-17 in the `add-python-harness` change; this record writes it
  down after the fact)
- **Change:** `harness-selection`; requirements: `orchestration-harness` spec

## Context

We need a tool that wakes the right Claude Code team agent when the handover hub has work for it, keeps it moving
through agreed stops and hands control on, one agent at a time, on one Windows 11 PC, with the agents on the owner's
Pro/Max plan. Candidates came from design D1 and three research reports, summarised in
[findings/](../research/findings/README.md): [HR-001 Hermes](../research/findings/HR-001-hermes.md),
[HR-002 orchestrating Claude Code](../research/findings/HR-002-orchestrating-claude-code.md),
[HR-003 headless limits and terms](../research/findings/HR-003-claude-code-headless-limits.md). The finalist's open
must-haves were checked by hand ([spikes.md](../research/spikes.md); `radark/README.md` → *Verification results*,
Claude Code 2.1.302, 2026-10-17).

## Candidates

| # | Candidate | Group (design D1) | Outcome |
|---|---|---|---|
| A | **Own Python dispatcher + `claude -p` + hooks** (built as `harness/`) | 2a + 4 (baseline) | **chosen** |
| B | Same dispatcher on the Python Agent SDK | 2a | runner-up |
| C | Claude Code session as dispatcher (`/loop` + `SendMessage` / `-p`) | 2b | rejected |
| D | Archon (coleam00/Archon) | 3 | rejected |
| E | CCManager (kbwo/ccmanager) | 3 | rejected |
| F | Hermes Agent (Nous Research) | 1 | rejected |
| — | Agent Orchestrator, Claude Squad, Vibe Kanban, ralph-loop plugin | 3 | eliminated in HR-002: parallel by design, no native Windows, abandoned upstream, or a pattern rather than a tool |
| — | Claude Desktop chat with computer use; Routines / `/schedule` | set aside (design D1) | too slow and fragile (screenshots); cloud agents cannot see the local hub and `D:\` repositories |

## Scoring matrix

Legend: met / partly / not met / unknown. Sources: H1 = HR-001, H2 = HR-002, H3 = HR-003, S = spike / verification
results. Must-haves (design D3) marked **[M]**.

| Requirement | A. Own dispatcher | B. Agent SDK | C. CC dispatcher | D. Archon | E. CCManager | F. Hermes |
|---|---|---|---|---|---|---|
| **[M]** Drives Claude Code sessions | met (S: CLAUDE.md, skills, hooks load; end and outcome from exit code, `result`, markers) | met (H2) | partly (H2) | met (H2) | partly (H2) | partly (H1: print mode only on Windows) |
| Harness model access separate | met (S: no model of its own; H3 (a)) | met (H2) | not met (H2; H3 (b) unclear) | partly (H2; H3 (c) for OAuth) | not met (H2) | partly (H1) |
| Wakes the team a handover is waiting for | met (S: full propose → archive cycle via `ho`) | met (H2) | partly (H2: model reads inbox) | partly (H2) | not met (H2) | partly (H1) |
| **[M]** Answers pre-agreed stops | met (S: `Stop` hook + product triage; escalation keywords) | met (H2) | partly (H2: messages cannot approve) | unknown (H2) | partly (H2) | not met (H1) |
| **[M]** One agent at a time | met (S: sequential; a read-only limit check may run beside a long session) | met (H2) | partly (H2) | partly (H2) | not met (H2) | partly / unknown (H1) |
| Fresh session per phase | partly (S: fresh per phase; resume only for triage, time limits and owner answers — no per-task "keep one session" flag) | met (H2) | met (H2) | met (H2) | partly (H2) | met (H1) |
| Archive only after approval | met (S: archive only after `close`; return → `apply` on the same change) | met (H2) | partly (H2) | met (H2) | not met (H2) | not met (H1) |
| **[M]** Observable and stoppable | met (S: `runs.jsonl`, per-session streams, console; `PAUSE`, `STOP`, Ctrl+C, `--until`) | met (H2) | partly (H2) | met (H2) | partly (H2) | partly (H1) |

Eliminated on a must-have: C (none met fully, non-deterministic), E and F (a must-have not met). D's stop-answering is
unknown and it would run on the owner's OAuth token (H3 (c)) or need an API key for the agents; it is also built for
parallel worktrees. A beats B on setup effort: same capabilities, but stream-json parsing and exec-form hooks were enough,
and B carries a reported `AskUserQuestion` bug in headless mode (H2, #50728).

## Decision

**Chosen: A — our own Python dispatcher** (`harness/`, spec `harness-dispatcher`). It polls `ho inbox --json`, starts one
`claude -p` per OpenSpec phase in the team repository with exec-form hooks injected through `--settings`, refers
questions to a read-only product-team consultation, escalates the rest to the owner through the hub, and gates
archiving on the author closing the handover.

**Runner-up: B** — the upgrade path if hook behaviour on Windows becomes unreliable or in-process control is needed.

**Hermes verdict:** Hermes Agent (Nous Research, `NousResearch/hermes-agent`) is **not suitable** as our orchestrator. It
fails *Answers pre-agreed stops* (it wires none of Claude Code's control points), can only use print mode on native
Windows, has no global one-at-a-time lock, sends far more than the stop text to its model, and changes several times a
month. The glue we would still write equals the standalone script (H1). Its subscription plugin is against Anthropic's
terms for third-party tools (H1, H3 (c)).

## Account model and cost

- **Agents:** Claude Code as installed, logged in with the owner's Pro/Max plan, launched unmodified as `claude -p` by the
  owner's own script on the owner's machine. Within terms per Help Center 15036540 (primary, 7 Oct 2026: "You can still
  use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits") and the Claude Code legal
  page (primary: signing in to "the unmodified Claude Code binary with their own Claude subscription" is not prevented).
  The dispatcher never reads or passes on the login token and sets no `ANTHROPIC_API_KEY` (H3).
- **Harness:** rule-based, **no model and no credential of its own**. Decisions a rule cannot settle go to a read-only
  `claude -p` consultation in the product team's repository — a Claude Code session of the owner's, the same case (a) as
  the agents, not a third-party agent loop. The OpenRouter option of design D5 was not needed, so no data leaves the
  machine beyond what Claude Code itself sends.
- **Estimated monthly cost:** 0 in API fees. The real cost is plan usage: the five-hour and weekly limits (H3 (d)), which
  the dispatcher reads from `rate_limit_event` lines and respects (`usage_pause_percent`, run budgets, waits after a
  limit hit).

## Risks

- **Terms change** (five changes in 2026, H3) → re-check the cited pages before widening use; a move to API billing for
  `claude -p` would need an Anthropic API key for the agents and a cost estimate.
- **Grey zone of "ordinary, individual usage"** for long unattended runs by a one-person company (H3 (a), medium-high) →
  runs stay the owner's own development work; the dispatcher's usage pause keeps headroom.
- **Claude Code updates change `-p`, hooks or flags** (e.g. `AskUserQuestion` not offered in `-p` on 2.1.302) → the
  `SessionStart` marker stops the loop if hooks do not load; re-run the sandbox after updates (tested on 2.1.302,
  installed now 2.1.312).
- **Windows hook stdin bugs** (H3) → exec-form hooks via `python.exe`, verified in the sandbox.
- **Every session ends with one nudge turn** (the `Stop` hook cannot tell a finished phase from an early stop) → a few
  seconds per session; accepted.
- **Fresh session per phase is only partly met:** no flag marks a task to continue in one session → add it if a real
  case needs it.

No requirement is `unknown` for the chosen platform.

## Open questions for later changes

- A per-task "continue in one session" flag (requirement *Fresh session per phase*).
- Whether the agreed-stops list needs anything beyond the standing rule, escalation keywords and product triage.
- A notification channel besides the hub escalation and the console (toast, phone).
