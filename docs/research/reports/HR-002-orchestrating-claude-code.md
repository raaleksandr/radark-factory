Received: 2026-10-16 · Tool: claude.ai Research

# Running Claude Code agents unattended on one Windows 11 PC: tools and patterns (status 16 October 2026)

**Recommendation: build a small, deterministic dispatcher script of your own. It should loop over `ho inbox --json`, start one `claude -p` per OpenSpec phase in the right repository, and rely on Claude Code's own hooks and permission flags for the automatic answers.** Anthropic now documents every piece this needs. No third-party orchestrator found fits your one-team-at-a-time, hub-driven flow on native Windows better than about 400–600 lines of your own code.

## TL;DR

- **Shortlist:**
  1. **Baseline dispatcher, `claude -p` plus hooks (shapes 4 + 1).** Strongest fit, lowest risk under your plan's terms.
  2. **The same dispatcher on the Python Agent SDK.** Use it when you want `canUseTool` callbacks and in-process control instead of parsing stream-json.
  3. **Archon (coleam00/Archon, MIT, native Windows).** Only worth it if you want a YAML workflow engine with a UI, and only after checking whether its Agent-SDK-on-your-login mode is acceptable under Anthropic's terms.
- **Shape 2 (a Claude Code session as dispatcher, using `/loop` plus cross-session `SendMessage`) is now possible on native Windows, but not for overnight runs.**
  - The building blocks are documented: `/loop` since v2.1.71, cross-session messaging on native Windows since v2.1.234.
  - The combination is not documented as a pattern, it is non-deterministic, and it has documented gaps:
    - Peer messages cannot approve a permission prompt.
    - Held messages in `-p` workers expire after 5 minutes by default.
    - Scheduled tasks fire only while the session is idle.
    - Every wake-up re-sends the dispatcher's full context against your plan.
- **Auto-answering is now first-class in Claude Code:**
  - A `PreToolUse` hook on `AskUserQuestion` can answer a question by returning `updatedInput.answers` (honoured only in `-p` mode) or refuse it with a reason.
  - `--permission-prompts none` (v2.1.259+) removes `AskUserQuestion` entirely and turns every unresolved permission prompt into a logged denial.
  - `Stop` hooks can force a "continue" but must check `stop_hook_active`.
  - Together with `--permission-mode auto` or an allowlist, a `-p` run never sits waiting silently, which is the main failure mode of terminal-driving tools.

## Key Findings

**Shortlist and why:**

1. **Baseline dispatcher, `claude -p` plus hooks.**
   - It meets all four must-haves with documented behaviour:
     - It starts Claude Code in the repository, so `CLAUDE.md`, skills, settings and hooks load.\[1\]
     - It sees the end of the run via the exit code and the final `result` line in stream-json.\[1\]
     - It auto-answers through hooks and flags.
     - It is single-threaded by construction.
   - It uses your own Claude Code installation and login exactly as Anthropic's support article describes: "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits" (Claude Help Center, updated 7 October 2026).\[2\]
   - The orchestrator itself needs no language model. If you add one for classifying stop texts, it runs on its own OpenRouter key and sees only the stop text, team and handover ID.
2. **Agent SDK harness (Python).** Same flow, but:
   - `canUseTool` and in-process hooks replace shell hooks, which sidesteps the Windows Git Bash/PowerShell hook-shell problems.
   - Interrupts and logging are cleaner.
   - Cost: more code, plus a reported SDK bug where `AskUserQuestion` resolved with empty answers in headless mode (anthropics/claude-code #50728, SDK 0.1.63 / CLI 2.1.114). The reporter's workaround was to deny the tool in a `PreToolUse` hook.\[3\]
3. **Archon.** The most mature third-party engine with native Windows binaries and a Claude step:
   - Status: MIT, 23.7k stars and 3.5k forks on the coleam00/Archon GitHub page (star-history.com showed 23.4k on 12 September 2026), CLI v0.10.1 released 30 August 2026; a newer v0.11.1 is listed but its date is unconfirmed.
   - It drives Claude Code through the Claude Agent SDK and can use your Claude Code OAuth token.\[4\]
   - That is exactly the "third-party tool on a subscription login" case your terms research must settle.
   - It is also built around worktree-per-run and parallel workflows, so it needs adaptation for your hub.\[5\]\[6\]

## Details

### Q1. Third-party landscape (confidence: medium)

Repository facts below come from the GitHub repos and release pages as read in September–October 2026. Star counts are approximate snapshots. Most third-party "best tools" round-ups were written by vendors of competing tools (Nimbalyst, Abralo, amux, Munder Difflin, Augment), so their Windows claims were cross-checked against the repos where possible.

| Tool (owner) | What it does | How it controls Claude Code | Licence / latest release | Maturity | Windows | Own model? | Fit for you |
|---|---|---|---|---|---|---|---|
| **Archon** (coleam00/Archon) | YAML DAG workflow engine for coding agents: deterministic bash steps plus AI steps, human approval nodes, web UI, CLI, Slack/Telegram\[4\]\[7\] | Claude Agent SDK; needs Claude Code installed (`CLAUDE_BIN_PATH`) | MIT; CLI v0.10.1, 30 Aug 2026 (v0.11.1 listed, date unverified) | 23.7k stars on GitHub (23.4k on 12 Sep 2026 per star-history.com), frequent releases | **Native** (`install.ps1`, `archon-windows-x64.exe`) | No; uses `CLAUDE_CODE_OAUTH_TOKEN` (your login) or an API key | Closest to a "workflow engine with a Claude step"; worktree-per-run and terms question\[5\]\[8\]\[9\] |
| **Agent Orchestrator** (ComposioHQ → Untrivial-ai → OrchestratorInc) | Fleet of parallel agents, one git worktree and PR each; routes CI failures and review comments back to agents\[10\]\[11\] | Originally tmux/process runtimes; current Go/Electron desktop daemon not confirmed | Apache-2.0 (earlier MIT); stable about v0.13.3, about 1 Oct 2026 | about 12.4k–12.7k stars | Native desktop app, but Windows bugs reported (#5030 "Windows errors, cannot use app at all", AO 0.12.12) | Uses each agent's CLI; orchestrator is itself an agent | Built for parallelism and GitHub/Linear trackers, the opposite of one-at-a-time\[11\]\[12\]\[13\]\[14\]\[15\]\[16\] |
| **Claude Squad** (smtg-ai/claude-squad) | TUI session manager, tmux plus worktrees | tmux + PTY, runs `claude` | AGPL-3.0; v1.0.20, 20 Aug 2026 | 8,607 stars, updated 20 Aug 2026 (smtg-ai org page) | **None natively** (issue #275, opened 7 Apr 2026 against the v1.0.17 Windows build and still open: "Windows binary fails immediately on `n new` — `creack/pty` is unsupported on Windows"); WSL only | No | Human-in-the-loop manager; "AutoYes" is a blanket yes\[17\]\[18\]\[19\]\[20\] |
| **CCManager** (kbwo/ccmanager) | Session manager for Claude Code and 7 other CLIs; shows busy/waiting/idle per session | Own PTY, no tmux | MIT; v4.4.6, 10 Oct 2026 | about 1.2k–1.3k stars, releases every 1–3 weeks\[21\]\[22\] | Probably native (README gives `%APPDATA%` paths, no tmux); one third-party page says WSL2 is required, so unconfirmed\[23\] | Experimental "Auto Approval" runs `claude -p --model haiku` on your login to decide whether to send Enter | Good human console; not an orchestrator\[24\]\[25\]\[26\]\[27\] |
| **Vibe Kanban** (BloopAI/vibe-kanban) | Kanban board where cards dispatch agents into worktrees | Launches agent CLIs (pinned Claude Code 2.1.119) | Apache-2.0; last release v0.1.44, 24 Apr 2026; **sunsetting** after bloop shut down on 10 Apr 2026 ("Goodbye bloop": the project "will live on, open source and community maintained") | about 28k stars | Cross-platform | No | Abandoned upstream; local forks exist (e.g. klaviyo/vibe-kanban-local)\[28\] |
| **ralph-wiggum / ralph-loop plugin** (Anthropic, anthropics/claude-code plugins) | In-session `Stop`-hook loop that re-feeds the same prompt until a "completion promise" appears | Stop hook inside Claude Code | Official plugin | Widely used; reported issues with session bleed across terminals\[29\]\[30\]\[31\] | Hook-shell caveats apply | No | A pattern to copy, not an orchestrator |

Others met but not assessed in depth: Conductor (macOS only), Nimbalyst, Paperclip, opcode, claude-sessions (WSL2 only). None of the tools found reads an external queue like `ho inbox` natively. All of them assume parallel, worktree-isolated tasks rather than your sequential cross-repository hand-offs.

### Q2. Anthropic's first-party options (confidence: high for documented items, medium where noted)

**Documented on code.claude.com (pages read 16 October 2026):**

- **Non-interactive mode (`claude -p`).**
  - Without `--bare` it "discovers and loads" hooks, skills, `CLAUDE.md`, settings and `.mcp.json` from the working directory, as an interactive session would.\[1\]
  - `--bare` skips all of that and "never reads OAuth credentials", so it needs an API key.\[1\] **Do not use `--bare` for your teams.**\[1\]\[32\]
  - Exit code 0 means success; non-zero means failure.\[1\]
  - `--output-format json` gives `result`, `session_id` and `total_cost_usd` (a client-side estimate). In `stream-json` the last line is a `result` message.\[1\]\[33\]\[34\]
  - `--resume <session_id>` works from any directory; `--continue` resumes the latest session.\[1\]\[34\]
  - Other flags: `--json-schema` for structured output, `--max-budget-usd` as a cost cap, and `--append-system-prompt`.\[1\]
  - Slash commands and skills run in `-p` if included in the prompt string, so `/opsx:apply`-style OpenSpec commands work. Built-in UI-only commands do not.\[1\]
  - `--bare` "will become the default for `-p` in a future release".\[34\] Pin your behaviour by checking `system/init` for loaded hooks and plugins.\[1\]
- **Permission handling in `-p`:**
  - Modes: `--permission-mode auto | dontAsk | acceptEdits`, plus allowlists via `--allowedTools` and `permissions.allow`.\[1\]\[33\]\[35\]
  - The docs warn that a `-p` run with no mode set "takes the built-in starting permission mode … which can be `auto`, so pass the one you want".\[1\]
  - **`--permission-prompts none` (v2.1.259+)** is meant for "when nobody is available to answer permission prompts". It denies anything that would prompt unless a `PermissionRequest` hook allows it. It also removes tools that need a person, such as `AskUserQuestion`. Denials appear as `permission_denied` events and in `permission_denials` in the result.\[1\]
- **Hooks reference.**
  - Events relevant to you: `PreToolUse`, `PermissionRequest`, `PermissionDenied`, `Stop`, `StopFailure` (matchers include `rate_limit`, `authentication_failed`, `billing_error`), `Notification` (matchers include `permission_prompt`, `idle_prompt`, `agent_needs_input`, `quota_auto_resume_fired`), `SessionStart` and `SessionEnd`.\[36\]
  - `AskUserQuestion` can be answered programmatically: return `permissionDecision: "allow"` with `updatedInput` containing the original `questions` and an `answers` map. The docs say Claude Code "honors this value only in non-interactive mode with the `-p` flag".\[36\]
- **`/loop` and Cron tools.**
  - Added in v2.1.71 (changelog, 7 March 2026). Self-pacing `/loop` and the `Monitor` tool arrived in the week of 6–10 April 2026 (v2.1.92–v2.1.101).\[37\]\[38\]
  - Tasks "only fire while Claude Code is running and idle".\[39\]
  - A session holds up to 50 tasks.\[39\]
  - Recurring tasks expire (7 days in current docs; earlier write-ups said 3 days).\[40\]\[41\]
  - The Manage costs page warns that a scheduled task "fires on its interval even while the session is idle, sending your full context each time".\[42\]
  - A `-p` run waits for pending `/loop` wake-ups before exiting.\[1\]
- **Cross-session messaging (`ListAgents` / `SendMessage`).**
  - Launched in the week of 3–7 August 2026 (v2.1.224, macOS/Linux/WSL 2); native Windows needs **v2.1.234+**, using a per-session named pipe.\[43\]\[44\]
  - `claude -p` workers bind an inbox; `--bare` sessions do not.\[44\]
  - Documented limits:
    - A message "can't approve anything" and never answers a permission prompt.\[44\]
    - In a `-p` session, a message the default rules hold is dropped after `dialogExpiry`, 5 minutes by default, unless you start the worker with `crossSessionInbound: "accept"` in `--settings`.\[44\]
    - `notify_when_idle` (v2.1.236+) gives the dispatcher one notice when a local session goes idle; the subscription expires after 12 hours.\[44\]
    - On Windows, scripts can post into a session's own pipe with `CLAUDE_CODE_MESSAGING_TOKEN`.\[44\]
    - WSL 2 and native Windows sessions cannot reach each other.\[44\]
- **Desktop app.**
  - Local scheduled tasks need Claude Desktop 1.1.5368+.\[45\]
  - Desktop sessions cannot show the held-message approval dialog.\[44\]
  - Per the Desktop docs, Desktop "can't send cross-session messages from a session nobody is watching, such as a scheduled-task run".\[46\]
- **Other long-run aids:**
  - `/goal`, which keeps working until a model confirms a condition; it also works with `-p`.\[47\]
  - The official ralph-loop plugin.\[48\]
  - Auto mode, the default for new Pro/Max/Team sessions since 14 August 2026 and the built-in interactive starting mode on every plan from v2.1.283.\[49\]\[50\]

**Shapes 1 and 2:**

- **Shape 1 (script or SDK driving headless Claude Code with hooks):** fully documented.
- **Shape 2 (Claude Code session as dispatcher):** every primitive is documented, but the whole pattern is not. Specifically:
  - Waking an open team session by `SendMessage` is documented.
  - Having that message answer the team's permission prompt is explicitly **not possible**.
  - Launching `claude -p` from the dispatcher's Bash tool is ordinary tool use, not a documented orchestration pattern.
  - Agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) and sub-agents run inside one session and one working directory, so they don't give per-repository `CLAUDE.md` and settings.\[51\]

**Terms-related claims found (for your separate legal question):**

- The Agent SDK overview says: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK."\[52\]\[53\]
- The help article (updated 7 October 2026) says personal `claude -p`, Agent SDK and third-party-app use still draws on subscription limits.\[2\]\[53\]\[54\]
- On 7 October 2026 Max and Team plans gained monthly API credits. These cover `claude -p` and the SDK only when run with an API key from the linked Console organization.\[55\]
- The Next Web reported on 4 April 2026 that "users of Claude's Pro and Max subscription tiers can no longer pipe their plan's usage limits through third-party frameworks such as OpenClaw", announced by Boris Cherny, Head of Claude Code, on X (also cited in gsd-build/gsd-2 #3772). Treat these as secondary and partly superseded by the October article.
- The distinction that matters for you: your own script calling your own `claude` binary is first-party use. A tool that holds your OAuth token and runs its own agent loop (Archon, any Agent-SDK harness distributed by someone else) is the grey zone.

### Q3. Auto-answering stops in practice (confidence: high for the mechanisms, medium for reliability)

| Stop type | Documented mechanism | What breaks |
|---|---|---|
| `AskUserQuestion` | `PreToolUse` matcher `AskUserQuestion`: either (a) `allow` + `updatedInput.answers` (choose the option marked recommended or the first, and log it; `-p` only; added around v2.1.85 per community hook references), or (b) `deny` with reason "Decide yourself, record the assumption in `assumptions.md`, continue". Or remove the tool with `--permission-prompts none` | SDK headless empty-answer bug (#50728); a matching `PermissionRequest` hook also fires for `AskUserQuestion`, so skip it there (reported in a Medium hooks guide)\[3\]\[36\]\[56\]\[57\] |
| Plain-text question / early end of turn | `Stop` hook reads `last_assistant_message`; if the handover state in `ho` hasn't advanced, return block plus a "continue" instruction | Endless loops unless you exit 0 when `stop_hook_active` is true. A secondary source reports a built-in cap of 8 consecutive continuations since v2.1.143 (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`).\[58\]\[59\] Anthropic's ralph plugin uses a max-iterations counter plus a completion promise\[60\] |
| Permission prompt | Allowlist in `.claude/settings.json` plus `--permission-mode auto` (classifier) or `dontAsk`; `PermissionRequest` hook for agreed extra cases; `--permission-prompts none` so nothing waits | Auto mode falls back to manual after 3 consecutive or 20 total classifier blocks in interactive sessions; in `-p` it "doesn't stop the run".\[61\]\[62\] `bypassPermissions` / `--dangerously-skip-permissions` removes all guardrails, so avoid it\[63\]\[64\] |
| Escalation | Denials end up in `permission_denials`; `Notification` hooks for `permission_prompt` / `agent_needs_input`; `defer` decision in `-p` (community-documented, v2.1.89+) exits with the pending call kept for a later `--resume`\[56\]\[65\] | Terminal-driving tools (Claude Squad AutoYes, CCManager auto-approval) answer by sending keystrokes after parsing the screen. CCManager's own README warns that AutoYes "bypasses Claude Code's built-in security confirmations"\[25\] |

Prompt convention that pairs with the hooks: use `--append-system-prompt` to add "Never ask the user. When choosing between approaches, pick the one that best fits CLAUDE.md and the OpenSpec change, write the assumption to the change's notes, and continue. Stop only when the phase is complete or you are blocked by something outside the repository." The hooks then enforce what the prompt asks.

### Q4. Session per phase and resume (confidence: high)

- **Starting a phase:** `claude -p "<prompt>" --output-format stream-json --verbose --permission-mode auto --permission-prompts none` with the working directory set to the repository.
- **Recording the session:** capture `session_id` from `system/init` or the final `result`, and store it with the team, handover ID, phase and outcome.
- **Classifying the outcome:**
  - Exit code 0 with a `result` message means finished.
  - A non-zero exit code or `StopFailure` means error.
  - Non-empty `permission_denials` or a recorded escalation means waiting for the owner.
  - `system/api_retry` events with `error: rate_limit` mean a usage limit.\[1\]
- **Resuming:** `claude -p "<follow-up>" --resume <id>` from any directory; set `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` to continue an interrupted turn.\[1\]
- **Default:** a fresh session for each OpenSpec phase. Use `--resume` only for a "return" on the same change when that session is recent.

### Q5. Event-driven waking (confidence: medium)

No published tool reads a JSON-emitting CLI queue and wakes agents one at a time. Closest patterns:

- Agent Orchestrator reacts to GitHub/Linear events and CI, in parallel.\[10\]\[12\]
- Archon starts workflows from CLI, chat or webhooks.\[4\]\[5\]
- EPAM's blog guide to a multi-agent Claude Code team (octobots) says "Production runs are headless. The supervisor polls taskbox and GitHub in the background", with taskbox being a SQLite queue polled within about 15 seconds.
- Claude Code's own `Monitor` tool can stream a watcher's events into one session.\[1\]\[38\]

For your hub, the straightforward loop is:

```
for each team in [product, app, backend, strategy]:
    run `ho inbox --json` with HO_TEAM=team
    take action_required and to_review items in a fixed order
    pick the first item, map it to a phase prompt
    run it to completion, then re-poll
```

A lock file guarantees one session at a time. A `PAUSE` file is checked between sessions. Archive and return rules sit in the dispatcher's state table:

- Send "archive change X" only after the product team has `close`d the handover.
- On `return`, send "continue change X per returned comments".

### Q6. Windows specifics (confidence: medium-high)

- **Hook shell.**
  - Claude Code runs `command` hooks through Git Bash when it is installed and falls back to PowerShell otherwise. The fallback was added in v2.1.120; source: an analysis of the 2.1.292 binary in openwong2kim/wmux #1880.\[66\]
  - The model is told "Shell: PowerShell" while hooks run under bash (anthropics/claude-code #59225, 14 May 2026).\[67\]
  - `commandWindows` is ignored (reported in claude-code #90122, 27 August 2026).\[68\]
  - Third-party hook packs broke on exactly this (AgentDeck #331, 14 September 2026; jfrog/boost #92, 26 September 2026).\[69\]\[70\]
  - **Fix:** write hooks in exec form (`"command": "python"`, `"args": [...]`, v2.1.139+). This needs no shell, and the docs' Windows example uses `powershell.exe` with `args`.\[36\]\[66\]
  - An open report (#72636, 1 July 2026) describes hooks on Windows running `git` instead of the configured command, failing silently.\[71\] **Verify your hooks fire** with a log line on `SessionStart`.
- **Process control.**
  - The docs describe SIGTERM (exit 143, pending prompt left unanswered) and SIGINT (ends the turn) in POSIX terms.\[1\]
  - On Windows, stopping a child cleanly is harder. Prefer the Agent SDK's `interrupt()`, or let the dispatcher finish the current session before pausing; use `taskkill /T` only as a last resort.
  - Before v2.1.211, an unreadable stdin on Windows could crash `-p` or make it exit silently, so stay on a current 2.1.x.\[1\]
- **Tool support:** Claude Squad has no native Windows build;\[72\] Agent Orchestrator has open Windows defects; cross-session messaging needs v2.1.234+ on native Windows; WSL and native sessions are isolated from each other.\[15\]\[19\]\[44\]

### Q7. Pitfalls (confidence: medium; mostly user reports)

- **Runaway loops.**
  - `Stop` hooks without a `stop_hook_active` guard loop forever.\[73\]
  - Ralph-style loops can burn plan quota for hours.\[31\]
  - Before v2.1.281, failed `/loop` deliveries re-fired every second (fix reported via the changelog).\[74\]
- **Silent waits.**
  - Interactive sessions behind terminal managers wait indefinitely on a prompt.
  - `-p` with a `canUseTool` host waits for the host unless you pass `--permission-prompts none`.\[1\]
- **Usage limits.**
  - Pro/Max limits are shared across Claude, Claude Code and `claude -p`.\[75\]\[76\]
  - A night of sequential phases can hit the 5-hour window. Detect `rate_limit` (from `StopFailure` or `api_retry`) and sleep until reset rather than retrying.
  - The `quota_auto_resume_*` notification types suggest Claude Code has a built-in auto-resume; its behaviour was not researched here.\[36\]
- **Context exhaustion.** Fresh sessions per phase avoid most of it. For a long apply phase, keep the plan in OpenSpec files, which you already do.
- **Cost surprises.**
  - A `/loop` dispatcher re-sends its full context on every tick.\[42\]
  - `total_cost_usd` is an estimate.\[1\]\[33\]
  - Background work can keep a `-p` run open for up to 10 minutes after the turn, or longer for background commands.\[1\]

### Q8. Fit scoring

Legend: ✅ met, ◐ partly met, ❌ not met, ? unknown.

| Requirement | A. Baseline script + `claude -p` + hooks | B. Agent SDK (Python) harness | C. Claude Code dispatcher (`/loop` + `SendMessage`/`-p`) | D. Archon | E. CCManager |
|---|---|---|---|---|---|
| 1 [M] Drives Claude Code in repo, observes end, Windows | ✅ headless docs (exit code, `result`, loads project settings) | ✅ SDK docs (same loop as Claude Code); setting sources must include project | ◐ launches `-p` via Bash tool or messages open sessions; end seen via `notify_when_idle` (messaging docs) | ✅ Agent SDK, native Windows binaries (repo) | ◐ PTY sessions, status by screen parsing (README); no prompt API |
| 2 Own model access, minimal data out | ✅ no LLM needed; optional OpenRouter classifier | ✅ same | ❌ dispatcher is Claude on your plan | ◐ engine itself needs no LLM; agents use your OAuth token or an API key (Archon docs) | ❌ auto-approval uses Haiku on your login |
| 3 Wakes right team from `ho inbox` | ✅ your loop | ✅ your loop | ◐ model reads inbox each tick; non-deterministic | ◐ bash node can call `ho`; scheduling outside Archon | ❌ manual |
| 4 [M] Answers agreed stops, escalates rest | ✅ hooks reference + `--permission-prompts none` | ✅ `canUseTool` + hooks (watch #50728) | ◐ hooks in team sessions work; `SendMessage` cannot approve prompts (messaging docs) | ? not documented beyond workflow approval nodes | ◐ auto-approve or manual only |
| 5 [M] One agent at a time | ✅ sequential by construction | ✅ | ◐ relies on the model obeying instructions | ◐ possible, but designed for parallel worktrees | ❌ parallel by design |
| 6 Fresh session per phase, optional resume | ✅ `-p` / `--resume` | ✅ `resume` option | ✅ `-p` per phase | ✅ per-node sessions | ◐ manual |
| 7 Archive gate / return to same change | ✅ dispatcher state table | ✅ | ◐ in prompt only | ✅ expressible as DAG conditions | ❌ |
| 8 [M] Observable and stoppable | ✅ stream-json log per session; pause file between sessions | ✅ plus `interrupt()` | ◐ transcript only; Esc cancels `/loop`; mid-run control is fuzzy | ✅ web UI, logs | ◐ live view, no audit log |
| **Glue code** | about 300–500 lines Python + 3 exec-form hook scripts (about 50–100 lines each) | about 400–600 lines | about 150 lines (skill/prompt + launcher) + hooks, plus prompt tuning | YAML workflows + `ho` bash nodes (about 200 lines) + adapting away from worktrees; unknown effort | n/a (not an orchestrator) |

Agent Orchestrator and Claude Squad fail requirement 5 by design, and Claude Squad also fails requirement 1 on native Windows.\[19\]\[77\]

## Recommendations

1. **Build A first; keep B as the upgrade path.**
   - Dispatcher in Python, sequential, with a JSONL log line per session: team, handover ID, phase, prompt hash, start, end, exit code, `session_id`, auto-answers, denials.
   - Launch flags: `--permission-mode auto` (or `acceptEdits` plus your allowlist), `--permission-prompts none`, `--output-format stream-json --verbose`, `--append-system-prompt` with the "decide and record" rule, and `--max-budget-usd` as a runaway guard (whether this cap is enforced on a subscription login is unverified).
   - Hooks per repository, exec form:
     - `PreToolUse:AskUserQuestion` (answer or deny, and log it).
     - `Stop`, which continues once if `ho` shows no state change, guarded by `stop_hook_active`.
     - `StopFailure:rate_limit`, which writes a marker the dispatcher reads.
   - Escalation: write an `ho new` addressed to the owner, raise a Windows toast, and leave the item unprocessed.
2. **Use only `ho`'s state transitions for the archive gate.** Never let an agent decide when to archive.
3. **Treat shape 2 as a daytime convenience, not the overnight engine.** If you try it, start `-p` workers with `crossSessionInbound: "accept"` and expect the dispatcher's ticks to use plan quota.
4. **Evaluate Archon only after your terms question is answered**, and only if you want its UI and YAML workflows enough to adapt them to a non-worktree, hub-driven flow.

## Caveats

- **Owner's version:** many features need a specific 2.1.x minimum: `--permission-prompts` 2.1.259, Windows messaging 2.1.234, exec-form hooks 2.1.139, `AskUserQuestion` answers about 2.1.85. Run `claude --version` before choosing.
- **Docs pages are living, undated documents.** Statements above reflect the pages as read on 16 October 2026.
- **Community-sourced facts:** the 8-continuation `Stop` cap, `defer` in v2.1.89, and the `AskUserQuestion` answer version came from secondary sources (blogs, community hook references), not Anthropic pages.
- **Unconfirmed tool facts:** CCManager's native Windows status, the newest Archon and Agent Orchestrator release dates, and how Agent Orchestrator's desktop app launches Claude Code on Windows.

**Gaps and quick tests on your machine (about an hour in total):**

1. `claude -p "print the hooks you were loaded with" --output-format stream-json --verbose` in each repository. Check `system/init` shows your hooks and that a `SessionStart` hook writes its log line. This catches the Windows hook-shell bugs.
2. Ask a `-p` run to "use AskUserQuestion to choose between A and B". Confirm the `PreToolUse` hook's `updatedInput.answers` is accepted on your version; also try `--permission-prompts none`.
3. Write a `Stop` hook that blocks once. Confirm `stop_hook_active` is true on the second stop and that the run ends.
4. Start a `-p` run, then kill the dispatcher with Ctrl+C and with `taskkill /T`. Check what the transcript and `--resume` show.
5. Run three phases back to back and watch `/usage` to estimate how many phases a 5-hour window allows on your plan.

## Sources

1. [Run Claude Code programmatically - Claude Code Docs](https://code.claude.com/docs/en/headless)
2. [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
3. [AskUserQuestion auto-resolves with empty answers in headless/no-TTY mode (Python Agent SDK) · Issue #50728 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/50728)
4. [Archon/CLAUDE.md at dev · coleam00/Archon · GitHub](https://github.com/coleam00/Archon/blob/dev/CLAUDE.md)
5. [GitHub - coleam00/Archon: The first open-source harness builder for AI coding. Make AI coding deterministic and repeatable.](https://github.com/coleam00/archon)
6. [Archon: Complete Rewrite - AI Workflow Engine for Coding Agents · Issue #957 · coleam00/Archon · GitHub](https://github.com/coleam00/Archon/issues/957)
7. [coleam00/Archon](https://deepwiki.com/coleam00/Archon/1-overview)
8. [Releases · coleam00/Archon](https://github.com/coleam00/Archon/releases)
9. [AI Assistants](https://archon.diy/getting-started/ai-assistants/)
10. [GitHub - mnemom/composio-ao: Agentic orchestrator for parallel coding agents — plans tasks, spawns agents, and autonomously handles CI fixes, merge conflicts, and code reviews. · GitHub](https://github.com/mnemom/composio-ao)
11. [9 Open-Source Agent Orchestrators for AI Coding (2026)](https://www.augmentcode.com/tools/open-source-agent-orchestrators)
12. [The Self-Improving AI System That Built Itself](https://composio.dev/blog/the-self-improving-ai-system-that-built-itself)
13. [Open-Sourcing Agent Orchestrator: Effectively Manage 30 Parallel Agents — pkarnal.com](https://pkarnal.com/blog/open-sourcing-agent-orchestrator)
14. [Untrivial.ai · GitHub](https://github.com/Untrivial-ai)
15. [Windows errors, cannot use app at all · Issue #5030 · Untrivial-ai/agent-orchestrator · GitHub](https://github.com/Untrivial-ai/agent-orchestrator/issues/5030)
16. [Releases · Untrivial-ai/agent-orchestrator](https://github.com/Untrivial-ai/agent-orchestrator/releases)
17. [Releases · smtg-ai/claude-squad · GitHub](https://github.com/smtg-ai/claude-squad/releases)
18. [Claude Squad · tomrochette.com](https://tomrochette.com/agents/claude-squad/)
19. [Windows binary fails immediately on \`n new\` — \`creack/pty\` is unsupported on Windows · Issue #275 · smtg-ai/claude-squad · GitHub](https://github.com/smtg-ai/claude-squad/issues/275)
20. [Claude Squad Alternatives Compared (2026): Desktop Agent Managers, No tmux](https://runpane.com/alternatives/claude-squad)
21. [Releases · kbwo/ccmanager · GitHub](https://github.com/kbwo/ccmanager/releases)
22. [CCManager - AI Agent Session Manager — FollowAgents](https://followagents.com/en/agents/ccmanager)
23. [Multiple Claude Sessions Chaotic? ccmanager Runs 8 AI CLIs in Parallel Worktrees](https://www.x-cmd.com/install/ccmanager/)
24. [ccmanager/README.md at main · kbwo/ccmanager · GitHub](https://github.com/kbwo/ccmanager/blob/main/README.md)
25. [GitHub - kbwo/ccmanager: Coding Agent Session Manager for Claude Code / Gemini CLI / Codex CLI / Cursor Agent / Copilot CLI / Cline CLI / OpenCode / Kimi CLI](https://github.com/kbwo/ccmanager)
26. [Solving 'Approval Fatigue' in Coding Agents Like Claude Code Using AI](https://zenn.dev/kbwok/articles/d9d1b14a0dc55a?locale=en)
27. [Release v4.4.6 · kbwo/ccmanager · GitHub](https://github.com/kbwo/ccmanager/releases/tag/v4.4.6)
28. [GitHub - klaviyo/vibe-kanban-local: Get 10X more out of Claude Code, Codex or any coding agent · GitHub](https://github.com/klaviyo/vibe-kanban-local)
29. [claude-code/plugins/ralph-wiggum at main · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum)
30. [Ralph Wiggum: Autonomous Loops for Claude Code](https://paddo.dev/blog/ralph-wiggum-autonomous-loops/)
31. [Ralph Wiggum Plugin for Claude Code: Install, Commands, and Stop Hook Loop Guide](https://vibetools.net/posts/say-goodbye-to-babysitting-ai-the-ultimate-guide-to-the-ralph-wiggum-plugin-for-claude-code)
32. [Glossary - Claude Code Docs](https://code.claude.com/docs/en/glossary)
33. [Run Claude Code Headless in Docker, Plus Codex and OpenCode](https://camelai.com/blog/claude-code-headless-docker)
34. [Claude Code Headless Mode (claude -p): Flags, Costs, Failures](https://www.swareco.com/blog/claude-code-headless-mode)
35. [Headless mode - Claude Documentation](https://cld-docs.onlinetool.cc/en/docs/claude-code/headless.html)
36. [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
37. [Claude Code Changelog on X: "Claude Code CLI 2.1.71 changelog: New features: • Added /loop command to run a prompt or slash command on a recurring interval (e.g. /loop 5m check the deploy) • Added cron scheduling tools for recurring prompts within a session • Added voice:pushToTalk keybinding to m… / X](https://x.com/ClaudeCodeLog/status/2030075374915240189)
38. [Week 15 · April 6–10, 2026 - Claude Code Docs](https://code.claude.com/docs/en/whats-new/2026-w15)
39. [Run prompts on a schedule - Claude Code Docs](https://code.claude.com/docs/en/scheduled-tasks)
40. [/loop in Claude Code: the cron that lives and dies with your terminal](https://www.frr.dev/posts/claude-code-loop-vs-cron-scheduling/)
41. [Stop Wasting Time Operating AI and Waiting for Outputs! How to Run Claude on Autopilot: /loop, Routines｜Claude Code研究所](https://note.com/claudecode_lab/n/n4b81e2d360ef?hl=en)
42. [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
43. [Week 32 · August 3–7, 2026 - Claude Code Docs](https://code.claude.com/docs/en/whats-new/2026-w32)
44. <https://code.claude.com/docs/en/cross-session-messaging>
45. [Schedule recurring tasks in Claude Code Desktop - Claude Code Docs](https://code.claude.com/docs/en/desktop-scheduled-tasks)
46. [Desktop application - Claude Code Docs](https://code.claude.com/docs/en/desktop)
47. [Keep Claude working toward a goal - Claude Code Docs](https://code.claude.com/docs/en/goal)
48. [Ralph Wiggum Loop for Claude Code - Technique & /loop Guide (2026) - Awesome Claude](https://awesomeclaude.ai/ralph-wiggum)
49. [Choose a permission mode - Claude Code Docs](https://code.claude.com/docs/en/permission-modes)
50. [Claude Code Permissions: What Auto Mode Really Does](https://felloai.com/claude-code-permissions/)
51. [The Code Agent Orchestra - what makes multi-agent coding work](https://addyosmani.com/blog/code-agent-orchestra/)
52. [Agent SDK overview - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview)
53. [Claude for AI Agents Review: API Costs, SDK & Limits](https://hermes-agent.ai/blog/claude-for-ai-agents-review)
54. [Settings, Claude: sign in inside the environment first, subscription-token custody limited to an allowlist until Anthropic approves, Max/Team API-credits path · Issue #11235 · OpenAgentsInc/openagents · GitHub](https://github.com/OpenAgentsInc/openagents/issues/11235)
55. [Monthly API credits for Max and Team plans - Claude support](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans)
56. [claude-code-hooks/.claude/hooks/HOOKS-README.md at main · shanraisshan/claude-code-hooks · GitHub](https://github.com/shanraisshan/claude-code-hooks/blob/main/.claude/hooks/HOOKS-README.md)
57. [Claude Code Hooks: A Practical Guide to Not Staring at Your Terminal](https://medium.com/@ashmitbbiswas/claude-code-hooks-a-practical-guide-to-not-staring-at-your-terminal-71873d2f3f06)
58. [Claude Code hooks: every event, with examples to copy](https://www.cubic.dev/blog/claude-code-hooks)
59. [Claude Code Hooks Explained: PreToolUse, PostToolUse, Stop and Exit Codes — Munder Difflin Blog](https://munderdiffl.in/blog/claude-code-hooks-explained/)
60. [ralph-loop (Iterative Development)](<https://deepwiki.com/anthropics/claude-plugins-official/6.2-ralph-loop-(iterative-development)>)
61. [Claude Code Auto Mode: Complete Guide to Autonomous Mode](https://institute.sfeir.com/en/articles/claude-code-auto-mode-permissions-autonomy/)
62. [Best practices for Claude Code - Claude Code Docs](https://code.claude.com/docs/en/best-practices)
63. [Claude Code Makes Auto Mode the Default on August 14](https://www.digitalapplied.com/blog/claude-code-auto-mode-default-permission-model-shift)
64. [Claude Code Just Shipped "Auto Mode" — And It Changes Everything About Agentic Development - Kingy AI](https://kingy.ai/news/claude-code-just-shipped-auto-mode-and-it-changes-everything-about-agentic-development/)
65. [7 Claude Code Hacks That Turn the April 2026 Release Into an Unfair Advantage](https://medium.com/@tatsuru.okada/7-claude-code-hacks-that-turn-the-april-2026-release-into-an-unfair-advantage-b585e42bd02e)
66. [Windows: brain hooks fail to parse under PowerShell when Claude Code has no Git Bash · Issue #1880 · openwong2kim/wmux · GitHub](https://github.com/openwong2kim/wmux/issues/1880)
67. [\[BUG\] Windows: model is told Shell=PowerShell while hooks execute under bash — cross-shell foot-gun for hook authors · Issue #59225 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/59225)
68. [commandWindows does nothing; hooks fall back to Git Bash on Windows · Issue #857 · DietrichGebert/ponytail · GitHub](https://github.com/DietrichGebert/ponytail/issues/857)
69. [Windows: every Claude Code hook fails — Git Bash strips \$variables from the inline PowerShell -Command · Issue #331 · puritysb/AgentDeck · GitHub](https://github.com/puritysb/AgentDeck/issues/331)
70. [Windows + Git Bash hosted Claude Code: PowerShell-only hook commands and Bash-tool rewrites break (claudeUsesPowerShell misdetects) · Issue #92 · jfrog/boost · GitHub](https://github.com/jfrog/boost/issues/92)
71. [\[BUG\] Windows: Claude Code never executes configured hook commands — hook runner invokes \`git\` instead and silently swallows the failure · Issue #72636 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/72636)
72. [Claude Code and Codex Session Managers: Mac, Windows, Linux](https://nimbalyst.com/blog/best-session-managers-for-claude-code-and-codex/)
73. [GitHub - disler/claude-code-hooks-mastery: Master Claude Code Hooks · GitHub](https://github.com/disler/claude-code-hooks-mastery)
74. [Claude Code /loop: The Complete Guide](https://www.getorchestra.io/knowledge-hub/glossary/claude-code-loop)
75. [Use Your Claude Pro/Max Subscription for Coding Agents](https://runpane.com/use-your-claude-subscription)
76. [support.anthropic.com](https://support.anthropic.com/en/articles/11145838)
77. [Claude Squad on Windows? Alternatives That Run Natively (2026)](https://runpane.com/alternatives/claude-squad-windows)
