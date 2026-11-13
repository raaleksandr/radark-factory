# HR-002 findings — orchestrating Claude Code

[Brief](../briefs/HR-002-orchestrating-claude-code.md) · [Report](../reports/HR-002-orchestrating-claude-code.md) ·
summarised 2026-10-29 (late intake; see [decision 0001](../../decisions/0001-orchestration-harness.md)).

## What the report establishes

- **Recommendation (high for documented mechanisms):** a small deterministic dispatcher of our own that loops over
  `ho inbox --json` and starts one `claude -p` per OpenSpec phase in the team repository, with Claude Code's hooks and
  permission flags doing the auto-answering. Estimated 300–600 lines of Python plus hook scripts.
- **First-party mechanisms (high, Claude Code docs as of 16 Oct 2026):** headless `-p` loads CLAUDE.md, skills, settings
  and hooks; the end is seen through the exit code and the final stream-json `result`; `PreToolUse` on `AskUserQuestion`
  can answer or deny; `--permission-prompts none` (v2.1.259+) turns unresolved prompts into logged denials; `Stop` hooks
  can force one "continue", guarded by `stop_hook_active`; `--session-id` / `--resume` cover session per phase.
- **Claude Code session as dispatcher (medium):** `/loop` plus cross-session `SendMessage` works on native Windows
  (v2.1.234+), but is non-deterministic, peer messages cannot approve prompts, scheduled tasks fire only while idle, and
  every wake-up spends plan usage. Fit for daytime use, not overnight runs.
- **Third-party landscape (medium, vendor round-ups cross-checked against repositories):** Archon (MIT, native Windows,
  Agent SDK, worktree-per-run, can use the owner's OAuth token — terms question), Agent Orchestrator and Claude Squad
  (parallel by design; Claude Squad has no native Windows), CCManager (a human console, not an orchestrator), Vibe Kanban
  (abandoned upstream), the ralph-loop plugin (a pattern, not an orchestrator). None reads an external queue like
  `ho inbox`; all assume parallel worktrees.

## Sources and dates

Claude Code docs (headless, hooks, permissions, messaging, scheduling; read 16 Oct 2026); Claude Help Center article on
`claude -p` and subscriptions (updated 7 Oct 2026); tool repositories and release pages (Sep–Oct 2026); GitHub issues
(e.g. anthropics/claude-code #50728). Community-sourced: the 8-continuation `Stop` cap and some version minimums.

## Candidate scores (provisional, from the report's fit table)

| Requirement | A. Script + `claude -p` + hooks | B. Agent SDK harness | C. Claude Code dispatcher | D. Archon | E. CCManager |
|---|---|---|---|---|---|
| Drives Claude Code sessions | met | met | partly | met | partly |
| Harness model access separate | met | met | not met | partly | not met |
| Wakes the right team | met | met | partly | partly | not met |
| Answers pre-agreed stops | met | met | partly | unknown | partly |
| One agent at a time | met | met | partly | partly | not met |
| Fresh session per phase | met | met | met | met | partly |
| Archive only after approval | met | met | partly | met | not met |
| Observable and stoppable | met | met | partly | met | partly |

## Still unknown

Behaviour on the owner's Claude Code version (hook stdin on Windows, `AskUserQuestion` in `-p`, `Stop` loop guard,
kill and resume, plan usage per phase). Each was checked in the sandbox spike — see [spikes.md](../spikes.md).
