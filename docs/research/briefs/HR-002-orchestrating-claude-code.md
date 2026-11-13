# HR-002 — Orchestrating Claude Code agents unattended: the 2025–2026 landscape

Register: [docs/research/README.md](../README.md) · Informs: candidate groups 2 (first-party, shapes 2a and 2b) and 3 (third-party orchestrators) of design D1, and the scoring matrix · Written: 2026-10-16

Sources of the context below: [workflow-today.md](../workflow-today.md) (2026-10-16) and the `orchestration-harness` spec of the change `harness-selection`. Hermes is researched separately (HR-001); the terms and the low-level limits of Claude Code's interfaces mainly in HR-003, so this brief asks for them only as far as they decide fit.

*Paste everything below the line into the research tool.*

---

# Research request: Tools and patterns for running several Claude Code agents unattended on one Windows PC — third-party and Anthropic's own (2025–2026)

## Context (who is asking)

A one-person software company runs its work through **AI "teams"**: each team is one Git repository on one **Windows 11 PC**, worked on by a **Claude Code** agent (Anthropic's CLI coding agent, version 2.1.x, logged in with the owner's Claude **Pro/Max** subscription). Today the owner opens each agent by hand in a terminal in that repository.

| Team | Role |
|---|---|
| `product` | Product manager: keeps the backlog, picks the next task, hands it to a technical team, accepts or returns the result. |
| `app` | Technical team: a Chrome extension (TypeScript). |
| `backend` | Technical team: website and backend (Next.js). |
| `strategy` | Company strategy (occasional). |

Every repository uses **OpenSpec** (a spec-driven workflow: each task is a "change" with propose → apply → archive phases, run through slash commands) and Claude Code project settings (`CLAUDE.md`, `.claude/settings.json` with an allowlist and hooks).

**Teams talk only through a local "handover hub"**: a Git repository of Markdown documents edited with a small Python CLI, `ho`. `ho inbox --json` (with env `HO_TEAM=<team>`) returns JSON arrays `action_required` (work addressed to this team), `to_review` (work this team sent that is finished and needs accepting or returning) and `updates`. Teams act with `ho ack | done | respond | return | close | new`.

**How a task moves:** product sends a handover to `app` → `app` creates an OpenSpec change and implements it → if it needs the backend, it sends its own handover to `backend`, which works and answers → `app` continues and reports `done` → product accepts (`close`) or returns it → only after acceptance does `app` archive the change. By habit each OpenSpec phase runs in a **fresh Claude Code session**; context is restored from files.

**Where the human is today, and what we want to automate:** (1) opening the right repository's agent when the hub has work for it and telling it what to do; (2) answering the agent when it stops — a question such as "which of these two approaches?" (Claude Code's `AskUserQuestion` tool or plain text), a permission prompt, or an early end of turn — for agreed kinds of stops with "choose the best variant and continue, record the assumption", escalating anything else; (3) starting each phase in a new session. Agents run **one at a time**, never two repositories at once. We want an unattended run (e.g. overnight) of one backlog task across these teams.

**Accounts:** the agents must stay Claude Code as they are (the owner's installation and plan). If the orchestrator needs a language model of its own, it should use **its own key with a spend limit** — the owner's **OpenRouter** account with a cheap model, or a separate Anthropic API key. We presume a third-party tool may **not** run its own agent loop on the Claude subscription. Whether a **Claude Code session itself** may act as the dispatcher on the same plan is an open question (asked in detail elsewhere; note what you find).

## Candidate shapes we already know of

1. **Claude Code's native interfaces driven by a script or program** — headless mode (`claude -p`, `--resume`, `--output-format stream-json`), hooks (`Stop` to block an early stop and give a "continue" instruction; `PreToolUse` on `AskUserQuestion` to deny the question with "choose the best variant"; `Notification`), a permission allowlist or permission mode `auto`, and the Claude Agent SDK (permission / question callbacks such as `canUseTool`).
2. **A dispatcher that is itself a Claude Code session** — a long-running session in the hub directory that paces itself with `/loop` (plus `Monitor` / `CronCreate` scheduling tools), reads `ho inbox --json`, and wakes a team either by messaging an already-open Claude Code session on the same machine (`ListAgents` / `SendMessage` between local sessions) or by launching `claude -p` in that team's repository for a fresh phase. Hooks inside each team session do the auto-answering. Team sessions may run in a terminal or the Claude Code desktop app.
3. **Third-party orchestrators / Claude Code managers** — tools that run several Claude Code instances (session managers, terminal-multiplexer drivers, "agent farms", workflow engines with a Claude Code step, kanban-style agent boards).
4. **Baseline:** a small self-written script that loops over `ho inbox --json` and launches `claude -p` per team with a fixed prompt plus hooks for stops.

Set aside on purpose: Claude Desktop chat with computer use (drives windows by screenshots — too slow and fragile), and cloud-only scheduled agents (Claude Code Routines / `/schedule`, they cannot see the local hub and `D:\` repositories).

## Evaluation frame — the requirements

Must-haves (failing one eliminates a candidate) are marked **[M]**.

1. **[M] Drives Claude Code sessions** — starts a Claude Code session with a given repository as working directory (so its `CLAUDE.md`, skills and settings apply), gives it a prompt, observes it until it ends (normally, with an error, or waiting for input), on Windows 11. The agents are the existing Claude Code, launched within the plan's terms.
2. **Own model access** — any model the orchestrator uses runs on its own credential with a spend limit (OpenAI-compatible / OpenRouter endpoint preferred); only the stop text, team and handover ID leave the machine; the agents' Claude Code login is untouched.
3. **Wakes the right team** — polls `ho inbox --json` per team and pings the team that has work with a prompt naming the handover and next step; carries no task content between repositories itself.
4. **[M] Answers agreed stops** — detects a question, a permission prompt or an early stop, answers agreed kinds automatically, escalates the rest to the owner (left waiting, with a notice).
5. **[M] One agent at a time** — at most one team session working at any moment; others wait in order.
6. **Fresh session per phase** — new session per OpenSpec phase by default, optional resume of the same session.
7. **Archive gate** — tells a team to archive only after the task's author closed the handover; on return, sends it back to the same change.
8. **[M] Observable and stoppable** — a readable log of each session (team, prompt, start/end, outcome, automatic answers); the owner can pause or stop the loop without leaving a session half-controlled.

## Questions

1. **Third-party landscape.** Which tools exist in 2025–2026 for running and controlling one or several Claude Code sessions unattended (orchestrators, session managers, tmux/terminal drivers, agent boards, workflow engines with a Claude Code step, Agent-SDK-based harnesses)? For each: name, URL, owner, what it does, how it controls Claude Code (CLI headless, Agent SDK, terminal emulation, MCP), licence, latest release date, maturity signals (stars, contributors, cadence), Windows support (native / WSL / none), whether it needs its own model and which providers it accepts, cost. Aim for the 5–10 most relevant, not an exhaustive list.
2. **Anthropic's first-party options.** What does Anthropic itself document for unattended and multi-session use of Claude Code as of 2026: headless mode, hooks, the Agent SDK, `/loop`, scheduling tools, sub-agents and agent teams, messaging between local sessions (`ListAgents` / `SendMessage`), the desktop app? Which of shapes 1 and 2 above are documented, which are only reported by users, and which are not possible? Note version numbers and dates.
3. **Auto-answering stops in practice.** How do people keep a Claude Code agent moving without a human: intercepting `AskUserQuestion`, `Stop` hooks that continue the agent (and how they avoid endless loops), permission allowlists vs `auto` mode vs skipping permissions, Agent SDK callbacks, prompt conventions ("never ask, decide and record the assumption")? What works, what breaks?
4. **Session-per-task and resume.** Patterns for one session per task phase, passing a prompt, detecting the end and its outcome (finished / error / waiting for input), resuming a kept session (`--resume`, session IDs).
5. **Event-driven waking.** Examples of a loop that watches an external queue or a CLI with JSON output and wakes the right agent in the right directory, one at a time.
6. **Windows specifics.** Known problems running these tools or Claude Code headless/hooks on native Windows 11 (shells, paths, process control, terminals).
7. **Pitfalls.** Reported failure modes of unattended Claude Code runs: runaway loops, stuck sessions, silent permission waits, usage-limit cut-offs on Pro/Max during long runs, context exhaustion, cost surprises.
8. **Fit.** Score the strongest 3–5 candidates (including shapes 1, 2 and the baseline 4) against the eight requirements above, and estimate the glue code each needs for our flow.

## Out of scope

- Hermes (researched separately).
- Replacing Claude Code with another coding agent; multi-machine, cloud or team-of-humans setups.
- Detailed reading of Anthropic's legal terms (asked separately) — but note any terms-related claim you meet, with its source.

## Output

- A short summary with a recommended shortlist of 2–3 candidates first, and why.
- Findings per question, each with sources (links) and their dates, and a confidence (*high* / *medium* / *low*) with the reason.
- A table: candidates × the eight requirements, with met / partly / not met / unknown and a source per cell.
- Gaps: what you could not establish and how we could check it ourselves with a quick test on our machine.

Cite sources with links and dates. Prefer 2025–2026 and primary sources (official docs, repositories, release notes, changelogs). This area changes monthly: give the date of every claim and the Claude Code version it applies to where known. Tell documented behaviour apart from reported experience and opinion.
