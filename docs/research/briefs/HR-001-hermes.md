# HR-001 — Hermes: what it is and whether it can run our Claude Code teams

Register: [docs/research/README.md](../README.md) · Informs: candidate group 1 (design D1) and the explicit verdict on Hermes in the decision record · Written: 2026-10-16

Sources of the context below: [workflow-today.md](../workflow-today.md) (2026-10-16) and the `orchestration-harness` spec of the change `harness-selection`. The owner heard of "Hermes" as an agent platform; we expect Nous Research's *Hermes Agent*, but have not checked.

*Paste everything below the line into the research tool.*

---

# Research request: "Hermes" as an orchestrator for several Claude Code agents on one Windows PC (2025–2026)

## Context (who is asking)

A one-person software company runs its work through **AI "teams"**: each team is one Git repository on one **Windows 11 PC**, worked on by a **Claude Code** agent (Anthropic's CLI coding agent, version 2.1.x, logged in with the owner's Claude **Pro/Max** subscription). Today the owner opens each agent by hand in a terminal in that repository.

| Team | Role |
|---|---|
| `product` | Product manager: keeps the backlog, picks the next task, hands it to a technical team, accepts or returns the result. |
| `app` | Technical team: a Chrome extension (TypeScript). |
| `backend` | Technical team: website and backend (Next.js). |
| `strategy` | Company strategy (occasional). |

Every repository uses **OpenSpec** (a spec-driven workflow: each task is a "change" with propose → apply → archive phases, run through slash commands) and Claude Code settings (`CLAUDE.md`, `.claude/settings.json` with an allowlist and hooks).

**Teams talk only through a local "handover hub"**: a Git repository of Markdown documents edited with a small Python CLI, `ho`. `ho inbox --json` (with env `HO_TEAM=<team>`) returns JSON arrays `action_required` (work addressed to this team), `to_review` (work this team sent that is finished and needs accepting or returning) and `updates`. Teams act with `ho ack | done | respond | return | close | new`.

**How a task moves:** product sends a handover to `app` → `app` creates an OpenSpec change and implements it → if it needs the backend, it sends its own handover to `backend`, which works and answers → `app` continues and reports `done` → product accepts (`close`) or returns it → only after acceptance does `app` archive the change. By habit each OpenSpec phase runs in a **fresh Claude Code session**; context is restored from files.

**Where the human is today, and what we want to automate:** (1) opening the right repository's agent when the hub has work for it and telling it what to do; (2) answering the agent when it stops — a question such as "which of these two approaches?" (Claude Code's `AskUserQuestion` tool or plain text), a permission prompt, or an early end of turn — for agreed kinds of stops with "choose the best variant and continue, record the assumption", escalating anything else; (3) starting each phase in a new session. Agents run **one at a time**, never two repositories at once.

**Accounts:** the agents must stay Claude Code as they are (the owner's installation and plan). If the orchestrator needs a language model of its own (to read a stop and choose an answer, or decide who goes next), it should use **its own key with a spend limit** — the owner has an **OpenRouter** account and would use a cheap model (DeepSeek, Qwen, GLM, Kimi families), or a separate Anthropic API key. We presume a third-party tool may **not** run its own agent loop on the Claude Pro/Max subscription; tell us if Hermes' docs say otherwise.

## Evaluation frame — the requirements

Must-haves (failing one eliminates a candidate) are marked **[M]**.

1. **[M] Drives Claude Code sessions** — starts a Claude Code session with a given repository as working directory, gives it a prompt, observes it until it ends (normally, with an error, or waiting for input), on Windows 11. The agents are the existing Claude Code, not a replacement agent.
2. **Own model access** — any model the orchestrator uses runs on its own credential with a spend limit (OpenAI-compatible / OpenRouter endpoint preferred); only the stop text, team and handover ID leave the machine; the agents' Claude Code login is untouched.
3. **Wakes the right team** — polls `ho inbox --json` per team and pings the team that has work with a prompt naming the handover and next step; carries no task content between repositories itself.
4. **[M] Answers agreed stops** — detects a question, a permission prompt or an early stop, answers agreed kinds automatically, escalates the rest to the owner (left waiting, with a notice).
5. **[M] One agent at a time** — at most one team session working at any moment; others wait in order.
6. **Fresh session per phase** — new session per OpenSpec phase by default, optional resume of the same session.
7. **Archive gate** — tells a team to archive only after the task's author closed the handover; on return, sends it back to the same change.
8. **[M] Observable and stoppable** — a readable log of each session (team, prompt, start/end, outcome, automatic answers); the owner can pause or stop the loop without leaving a session half-controlled.

## Questions

1. **Identity.** Which project(s) called "Hermes" are AI agent platforms or orchestrators in 2025–2026? We expect Nous Research's *Hermes Agent*; confirm or correct it and list any other plausible "Hermes" (name, owner, URL, one-line description), then focus the rest on the one(s) that are agent orchestrators. Is "Hermes" the model family, the agent, or both?
2. **Architecture.** What is it: agent runtime, framework, CLI, desktop app, server? How does it run tasks — its own agent loop with tools, sub-agents, schedules, messaging gateways? What languages, what dependencies?
3. **Driving Claude Code.** Can it start and control **external Claude Code sessions** (the `claude` CLI, its headless mode `claude -p`, the Claude Agent SDK, or a terminal) rather than only its own agent? Is there a documented integration, plugin, skill or example? If only indirectly (e.g. a shell tool running `claude -p`), how would it see a question or a permission prompt from Claude Code and answer it?
4. **Our flow.** Could it poll a CLI that returns JSON (`ho inbox --json`) on a schedule, decide which repository acts next, run strictly one session at a time, and start a new session per phase? Does it have scheduling, a queue or a loop primitive?
5. **Models and accounts.** Which model providers does it support (OpenRouter, OpenAI-compatible endpoints, Anthropic API, local)? Can it run with a cheap model for its own decisions? Does it offer or encourage logging in with a Claude subscription, and what do its docs or Anthropic's terms say about that?
6. **Windows.** Does it run natively on Windows 11, only under WSL, or not at all? Known Windows issues?
7. **Observability and control.** Logs, transcripts, a UI or dashboard; pause / stop; how it handles a crash in the middle of a task.
8. **Licence, maturity, cost.** Licence; first release and latest release dates; release cadence; GitHub stars and contributors; documentation quality; community size; known production users; any paid tiers or hosting costs.
9. **Fit verdict.** Score it against each of the eight requirements above (met / partly / not met / unknown, with the source), and say how much glue code we would have to write for the gaps. Compare briefly with the simplest alternative: a small script that loops over `ho inbox --json` and launches `claude -p` per team.

## Out of scope

- Hermes language models as models for our coding agents (the agents stay Claude Code).
- Cloud hosting, multi-machine or multi-user setups.
- General reviews of AI agents not related to orchestrating Claude Code.

## Output

- A short summary with the verdict on fit first.
- Findings per question, each with sources (links) and their dates, and a confidence (*high* / *medium* / *low*) with the reason.
- A table: the eight requirements × Hermes, with met / partly / not met / unknown and a source per cell.
- Gaps: what you could not establish and how we could check it ourselves (a quick test on our machine).

Cite sources with links and dates. Prefer 2025–2026 and primary sources (the project's repository, docs, release notes, Anthropic's docs and terms). Tell documented behaviour apart from reported experience and opinion. Several products share this name; say for each claim which one it is about.
