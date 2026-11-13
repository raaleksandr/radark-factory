# HR-003 — Claude Code headless, hooks, Agent SDK, dispatcher session: what works and what the plan terms allow

Register: [docs/research/README.md](../README.md) · Informs: the must-haves of first-party candidates (design D1 shapes 2a and 2b), the spike plan (design D4) and the account model (design D5) · Written: 2026-10-16

Sources of the context below: [workflow-today.md](../workflow-today.md) (2026-10-16), the `orchestration-harness` spec and design D5 of the change `harness-selection`. Claude Code version on our machine: 2.1.301 (2026-10-16). May be dropped if HR-002 already answers it with primary sources, terms questions included — recorded in the register.

*Paste everything below the line into the research tool.*

---

# Research request: Driving Claude Code unattended on a Pro/Max plan — what the native interfaces allow today, and what Anthropic's terms allow (2025–2026)

## Context (who is asking)

A one-person software company runs its work through **AI "teams"**: each team is one Git repository on one **Windows 11 PC**, worked on by a **Claude Code** agent (CLI, version 2.1.x), logged in with the **owner's own Claude Pro or Max subscription**. Today the owner opens each agent by hand in a terminal in that repository. Teams pass work through a local "handover hub" (a Git repository of Markdown documents, read with a CLI that prints JSON, `ho inbox --json`). Each task phase (propose, apply, archive in the OpenSpec workflow) runs in a fresh session. Agents run one at a time.

We want a **controller ("harness")** that (1) wakes the right repository's agent when the hub has work for it, (2) keeps the agent moving when it stops — a question (the `AskUserQuestion` tool or plain text), a permission prompt, an early end of turn — by answering agreed kinds of stops with "choose the best variant and continue, record the assumption" and escalating the rest to the owner, and (3) starts a fresh session per phase. We want to run one backlog task unattended (e.g. overnight).

We consider two first-party shapes:

- **A. Native interfaces driven by our own script** — headless mode (`claude -p`, `--resume`, `--output-format stream-json`), hooks (`PreToolUse`, `Stop`, `Notification`), a permission allowlist or permission mode `auto`, and possibly the Claude Agent SDK. The script itself either has no model (fixed rules) or calls a cheap model through **its own** OpenRouter or Anthropic API key with a spend limit.
- **B. The dispatcher is itself a Claude Code session** on the owner's plan, left open in the hub directory, pacing itself with `/loop` (and the `Monitor` / `CronCreate` tools), reading `ho inbox --json`, and waking a team by messaging an already-open Claude Code session on the same machine (`ListAgents` / `SendMessage`) or by launching `claude -p` in the team's repository. Hooks inside each team session do the auto-answering. No third-party code.

Our working assumption, to be confirmed or refuted: Pro/Max plans are for the subscriber's own use of Claude Code and claude.ai; using the subscription to power a **third-party** program's agent loop is not allowed, so such a program needs an API key.

## Part 1 — What the interfaces allow today

For each item: is it documented (link, date, version), does it work as documented according to issues or reports, and does it behave differently on **native Windows 11** (PowerShell / Git Bash, not WSL)?

1. **Headless mode.** `claude -p` with a prompt in a given working directory: are the project's `CLAUDE.md`, skills, slash commands (e.g. `/opsx:apply`), `.claude/settings.json` allowlist and hooks applied as in an interactive session? How does a headless run report its outcome (exit codes, the final `result` message in `stream-json`, `is_error`, a stop waiting for input)? How do `--resume` / `--continue` / session IDs work for continuing a kept session?
2. **Questions in headless mode.** What happens when the agent calls `AskUserQuestion` in `-p` mode — is the tool available, does it fail, return empty, or hang? Can a **`PreToolUse` hook** matching `AskUserQuestion` deny it with a reason such as "choose the best variant and continue; record the assumption", and does the agent then continue? Any documented way to *answer* the question (rather than deny it) from a hook or the SDK?
3. **Early stops.** Can a **`Stop` hook** block the end of a turn and feed the agent an instruction to continue (`decision: block` + `reason`)? How is an endless loop prevented (`stop_hook_active`, counters)? Same for `SubagentStop`.
4. **Permissions.** Permission modes available in 2026 (`default`, `acceptEdits`, `plan`, `auto`, `bypassPermissions` / `--dangerously-skip-permissions`, `dontAsk` if it exists): what each does, what `auto` decides and how it fails, what happens to a permission request in headless mode when no rule matches, and the `PermissionRequest` hook if it exists.
5. **Agent SDK.** In the Claude Agent SDK (TypeScript / Python): `canUseTool` and other permission or question callbacks, how `AskUserQuestion` reaches the host program and whether the host can answer it, session resume, Windows support.
6. **`/loop` and scheduling.** What `/loop` does (fixed interval vs self-paced), how long a session can keep looping, what it costs in usage while idle, and how `Monitor`, `CronCreate` and similar tools work; whether a looping session survives sleep / terminal close.
7. **Messaging between local sessions.** Do `ListAgents` / `SendMessage` (or any successor) let one Claude Code session send a message to another session running in a **different terminal** or in the **Claude Code desktop app** on the same machine? Does the receiving session act on it as on a user prompt? Requirements (same user, a setting, a feature flag, a plan), limits, Windows behaviour.
8. **Notifications.** The `Notification` hook and other ways for the controller to learn that a session waits for input.

## Part 2 — Terms, with primary sources

Answer each from **primary sources** — Anthropic's Consumer Terms, Commercial Terms, Usage Policy, Claude Code documentation (legal and compliance, authentication, Agent SDK pages), official help-centre articles or official announcements — quoting the relevant sentence with link and date. Keep the four cases apart; secondary reporting (blogs, forums, news) only as context, marked as such.

- **(a) Script-driven agents.** May a script or program that the owner runs on their own machine launch and drive the owner's **own Claude Code sessions** (`claude -p`, hooks) on a Pro/Max plan unattended, e.g. overnight? Any limits on automation, frequency or "non-human" use for subscription logins?
- **(b) A Claude Code dispatcher session.** May a Claude Code session on the plan act as the dispatcher for the owner's other Claude Code sessions using only Claude Code's own features (`/loop`, hooks, headless launches, messaging between local sessions) — shape B? Is this the intended use of those features?
- **(c) Third-party programs.** May the Claude Agent SDK, or a third-party harness (an orchestrator with its own agent loop), authenticate with the Pro/Max subscription (OAuth / Claude Code login token), or must it use an Anthropic API key (or Bedrock / Vertex)? What has Anthropic stated about third-party tools using subscription logins, and when?
- **(d) Usage limits.** Pro and Max usage limits for Claude Code in 2026 (session windows, weekly limits, model-specific limits) as they apply to long unattended runs and to a dispatcher session that stays open for hours: does an idle looping session consume usage, and how much does each wake-up cost roughly? What happens when a limit is hit mid-run (the session stops, waits, errors)?

## Out of scope

- Third-party orchestrators and their features (researched separately), except where their docs state something about Anthropic's terms.
- API pricing details beyond what is needed to compare a subscription with an API key for (c).
- Cloud-only features (Routines, remote / web sessions) except to note they do not see local files.

## Output

- A short summary first: for each of Part 1 items 1–8 a one-line answer (works / partly / no / unknown), and for each of (a)–(d) a one-line answer (allowed / not allowed / unclear) with the quoted source.
- Findings per question with sources (links) and their dates, the Claude Code version they apply to, and a confidence (*high* / *medium* / *low*) with the reason.
- A list of open points we should check ourselves with a quick test on our Windows machine, each with a suggested test.

Cite sources with links and dates. Prefer primary sources and 2025–2026; this area changes monthly, so give the date and version of every claim. Tell documented behaviour, reported experience and opinion apart, and never present a forum answer as a term of service.
