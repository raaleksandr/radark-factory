# HR-003 findings — Claude Code headless limits and plan terms

[Brief](../briefs/HR-003-claude-code-headless-limits.md) · [Report](../reports/HR-003-claude-code-headless-limits.md) ·
summarised 2026-10-29 (late intake; see [decision 0001](../../decisions/0001-orchestration-harness.md)). Not dropped:
HR-002 did not answer the terms questions of design D5 with primary sources.

## What the report establishes

### Interfaces (high, Claude Code docs read 16 Oct 2026, up to v2.1.299)

- Headless `-p`, `Stop` / `PreToolUse` / `PermissionRequest` / `Notification` / `StopFailure` hooks and permission
  modes (`auto`, `dontAsk`) work as documented. `AskUserQuestion` can be answered or denied from a hook — where the tool
  is offered at all.
- `/loop`, `CronCreate` and `Monitor` are session-scoped (open terminal, 7-day expiry). `ListAgents` / `SendMessage`
  work on native Windows from v2.1.234; the receiver treats a message as a peer's, so it cannot approve anything.
- Windows is the weak point: several issue reports of hooks getting empty or TTY stdin (#17424, #36156, #46601). Exec-form
  hooks are the recommended workaround.

### Terms (primary sources where marked)

- **(a) Own script driving the owner's own `claude -p` on Pro/Max — allowed for personal use (medium-high).** Help
  Center (primary, updated 7 Oct 2026): "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with
  your subscription limits." The legal page (primary) does not prevent "an end user from signing in to the unmodified
  Claude Code binary with their own Claude subscription". Grey zone: limits "assume ordinary, individual usage", and
  staff advise an API key for "building a business" on the SDK.
- **(b) Claude Code session as dispatcher — allowed in principle, "intended use" unclear (medium).** All features are
  first-party, but no primary source describes this pattern.
- **(c) Third-party loop on subscription OAuth — not allowed (high).** Legal page (primary): no routing "through Free,
  Pro, or Max plan credentials on behalf of their users"; no intermediating session tokens. A harness model needs its
  own API key.
- **(d) Usage limits apply fully (high for structure, low for `-p` behaviour at the limit).** Five-hour and weekly limits,
  shared with Claude; no published token numbers.

## Sources and dates

Anthropic Consumer Terms §3.7; Claude Code legal and compliance page (read 16 Oct 2026); Help Center articles 15036540,
17154008 (7 Oct 2026) and 11145838; Agent SDK overview; staff posts on X (18 Feb and 3 Apr 2026); press (The Register,
TechCrunch, The New Stack). Terms changed five times in 2026 — re-check before relying on them.

## Effect on candidates

Shape A (script + `claude -p`) needs no harness credential and is within (a). Shape B is possible but not robust and
not clearly intended. Hermes' subscription plugin and Archon on the owner's OAuth token fall under (c).

## Still unknown

`-p` behaviour at the usage limit, hook stdin on the owner's build, idle cost of a dispatcher session. The first two
were checked in the sandbox spike ([spikes.md](../spikes.md)); the third is moot because shape B was not chosen.
