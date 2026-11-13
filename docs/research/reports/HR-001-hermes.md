Received: 2026-10-16 · Tool: claude.ai Research

# Hermes Agent (Nous Research) as an orchestrator for Claude Code teams on one Windows 11 PC — fit assessment, October 2026

**Verdict: Hermes Agent can launch Claude Code, but it does not fit your loop well. It fails one must-have (answering agreed stops), only partly meets two others (one-agent-at-a-time and stoppability), and on native Windows it can only use print mode.** You would write roughly the same glue code with Hermes as without it, plus you would run a general-purpose LLM agent with memory, messaging gateways and fast weekly releases in the middle of your company's control path. Build the small deterministic script (about 400–700 lines of Python) around `claude -p` with stream-json output and a `--permission-prompt-tool` MCP gate. Call a cheap OpenRouter model only to classify ambiguous stops.

## TL;DR

- **Identity:** the relevant "Hermes" is **Hermes Agent** by Nous Research. It is an MIT-licensed, Python, self-improving personal agent runtime first released 25 February 2026, at about 254k GitHub stars, with release v0.22.2 on 15 October 2026. "Hermes" is also Nous Research's LLM family, so the name covers both the models and the agent. Several community projects reuse the name (oh-my-hermes, hermes-code-bridge), but none is a better orchestrator for your case.
- **Driving Claude Code:** Hermes ships a bundled `claude-code` skill. It delegates through its own LLM calling a shell tool (`claude -p …`), or through tmux screen-scraping for interactive sessions, and tmux is not available on native Windows. The official Claude Code docs offer real control points: `--permission-prompt-tool`, `--permission-prompts none|host`, stream-json `permission_denials`, `--resume`/`--session-id`, and hooks. Hermes does not wire any of them, so the stop-answering, the one-at-a-time lock and the archive gate would all be glue code you write anyway.
- **Recommendation:** use a standalone Python loop over `ho inbox --json`. It launches `claude -p` per team and phase, answers stops through an MCP permission gate plus a cheap-model classifier on a capped OpenRouter key, and writes a JSONL log with a pause file. Keep Hermes out of the control path, and do not use Hermes' Claude-subscription plugin: Anthropic's terms bar third-party tools from routing requests through Pro/Max credentials.

## Key Findings

### Q1. Identity — which "Hermes"? (confidence: high)

| Name | Owner | What it is | Relevant? |
|---|---|---|---|
| **Hermes Agent** (`NousResearch/hermes-agent`, docs at hermes-agent.nousresearch.com) | Nous Research | Open-source, self-improving AI agent runtime: CLI/TUI, desktop app, messaging gateway, cron, Kanban multi-agent board, skills, MCP | **Yes — the subject of this report**\[1\]\[2\] |
| Hermes model family (Hermes 3/4 etc.) | Nous Research | Open-weight LLMs, tuned for function calling | No (out of scope; the agent is model-agnostic) |
| oh-my-hermes (`HERMESquant/oh-my-hermes`) | Community | Config generator that writes CLAUDE.md/AGENTS.md "expert team" setups for Claude Code + Codex CLI | No — configures agents, does not run a supervision loop\[3\] |
| hermes-code-bridge (`xuyang-liu16`) | Community | A Hermes Agent skill that routes work to local coding CLIs (Codex, Claude Code, Kimi, etc.) | Add-on to Hermes Agent, same limitations\[4\] |
| hermes-paperclip-adapter | Nous Research | Runs Hermes as a "managed employee" inside Paperclip's task-management system | Hermes-as-worker, not Claude Code orchestration\[5\] |
| Hermes (JavaScript engine) | Meta | JS engine for React Native | Not an agent (name collision only) |

The name refers to both the model family and the agent. Hermes Agent is a harness that runs on any provider's model; it does not require Hermes LLMs.\[2\] Nous Research's GitHub org lists the agent as "The agent that grows with you", MIT licensed, with 253,988 stars and 55,129 forks shown on 15 October 2026.\[6\]

### Q2. Architecture (confidence: high)

- **What it is:** a Python agent runtime (the codebase is about 88% Python and 9% TypeScript, per a May 2026 repository walkthrough).\[7\] It ships as a CLI/TUI (`hermes`), a messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal, email and 15+ platforms), a web dashboard (port 9119), a desktop app (MSIX on Windows 11 22H2+), an ACP server for editors, and an MCP server/client.\[8\]\[9\]\[10\]
- **How it runs tasks:** its own LLM agent loop with tools (terminal, file, web/browser, memory, skills, `execute_code`, `delegate_task` subagents).\[9\] It adds a self-improvement loop that writes reusable `SKILL.md` files from experience and persistent memory in SQLite (`~/.hermes/state.db`).\[11\]\[12\]\[13\]
- **Automation primitives:**
  - **Cron**: agent jobs, plus "no-agent mode" script-only jobs that need no LLM, with pre-check scripts (`wakeAgent`) that decide whether the agent is woken at all.\[14\]\[15\]
  - **Kanban**: a durable SQLite-backed multi-agent board with a dispatcher inside the gateway, ticking every 60 s by default.\[1\]\[16\]
  - Persistent goals, recurring loops, event hooks.\[1\]
- **Dependencies:** the installer provisions Python (3.11+; the current Windows installer pins Python 3.14 via its package manager), Node.js v22, uv, ripgrep, ffmpeg, and Git Bash on Windows. The footprint is about 1 GB.\[10\]\[17\]

### Q3. Driving Claude Code (confidence: high on what exists; medium on how well it works on Windows)

**What Hermes documents.** The bundled skill `autonomous-ai-agents/claude-code` (v2.2.1, author "Hermes Agent + Teknium", platforms linux/macos/windows) is instructions for Hermes' own LLM, not code.\[18\] It offers two modes:

1. **Print mode (preferred):** Hermes' model calls its `terminal` tool with `claude -p '<task>' --allowedTools … --max-turns N`, `workdir=<repo>`, `timeout=…`.\[19\] Output can be `--output-format json` (`session_id`, `subtype` success/error, `stop_reason`, `total_cost_usd`) or `stream-json`. Sessions can continue with `--resume <id>`, `--continue` or `--fork-session`. The skill states that "Print mode skips ALL interactive dialogs — no workspace trust prompt, no permission confirmations."\[18\] In practice, prompts that nothing pre-approves are **denied**, not answered (see below).\[20\]\[21\]
2. **Interactive mode via tmux:** start `claude` in a tmux pane, `send-keys` the prompt, and poll `capture-pane` to read permission dialogs and answer them with keystrokes. The skill notes "Interactive mode REQUIRES tmux".\[18\] tmux is not part of native Windows, so on native Windows only print mode is realistic. Interactive mode would need WSL, with Claude Code and your repos inside WSL as well.

**What does not exist.** Hermes has an opt-in "Codex App-Server Runtime" that hands turns to the Codex CLI,\[1\]\[22\] but **no equivalent runtime for Claude Code**. It has no plugin that answers Claude Code's permission prompts or `AskUserQuestion` through `--permission-prompt-tool` or the SDK's `canUseTool`. Its `delegate_task(acp_command=…)` path works only with ACP-speaking CLIs such as GitHub Copilot: Claude Code has no `--acp` flag (Hermes issues #19055 and #15300, April–May 2026).\[23\]\[24\]

**Claude Code's own mechanisms (Anthropic docs, current October 2026), which any orchestrator has to use:**

- **Headless `-p`:** exit code 0 means success and non-zero means failure. `--output-format json|stream-json`; the last stream line is a `result` message with cost and session metadata.\[21\] `--session-id <uuid>`, `--resume`, `--continue` and `--fork-session` are available.\[25\] Without `--bare`, `-p` loads the project's `CLAUDE.md`, `.claude/settings.json` hooks and MCP servers, so your OpenSpec slash commands and allowlists still apply. `--bare` skips OAuth and requires an API key, so **do not use `--bare`** with your subscription login.\[21\]
- **Permission prompts in `-p`:**
  - With the default `--permission-prompts host`, a prompt that rules and modes don't resolve goes to the "permission host": an Agent SDK `canUseTool` callback, or an MCP tool named with `--permission-prompt-tool`. The run waits for the host's answer.\[21\]\[26\]
  - "In a `-p` run with no host, these requests are denied either way."\[20\]\[21\]
  - `--permission-prompts none` (v2.1.259+) denies them and "removes the tools that need an answer from a person, such as `AskUserQuestion`."\[21\]
  - Denials appear as `permission_denied` system messages, and the final result lists them in `permission_denials`.\[21\]
- **AskUserQuestion:** in the SDK it reaches `canUseTool` with `tool_name == "AskUserQuestion"` and "always fall[s] through to the callback, even when an allow rule matches".\[21\]\[27\]\[28\]\[29\] The docs I read do not say explicitly that it routes to `--permission-prompt-tool` in CLI print mode. There is conflicting field evidence: one project reported on Claude Code 2.1.280 that headless `claude -p` "does not offer `AskUserQuestion` at all", while an Anthropic issue (#50728, CLI 2.1.114) reported it auto-resolving with empty answers in no-TTY SDK runs.\[30\]\[31\] **Treat this as unverified and test it** (see Gaps). Plain-text questions ("which of these two approaches?") simply end the turn with `stop_reason: end_turn`; you have to detect them from the result text.
- **Hooks:**
  - `Stop` fires whenever Claude finishes responding. Exit code 2 or `{"decision":"block"}` forces it to continue, so it can serve as an "early stop" guard.\[32\]\[33\]\[34\]
  - `Notification` has matchers `permission_prompt` and `idle_prompt`. In SDK sessions `permission_prompt` fires once a request has waited about six seconds on `canUseTool`, and `idle_prompt` is emitted only by the interactive UI.\[35\]
  - `PreToolUse`/`PermissionRequest` hooks can allow or deny programmatically.\[32\]\[35\]
- **Stopping:** SIGTERM gives exit 143 and leaves the turn unfinished. SIGINT (or the SDK's `interrupt()`) ends the turn cleanly. A prompt pending at SIGTERM is left unanswered.\[21\]

**What this means:** with Hermes, your "answer agreed stops" logic would sit inside a cheap LLM's interpretation of terminal output. Print-mode permission prompts would never reach that LLM at all, because they are silently denied. The reliable mechanism is a permission-prompt MCP tool, or the Agent SDK `canUseTool`, plus result parsing. Hermes provides neither, so you would write it yourself in both designs.

### Q4. Your flow: polling, choosing the next team, one at a time, a fresh session per phase (confidence: medium)

- **Polling:** Hermes cron supports intervals ("every 5m"). A pre-check script can run `ho inbox --json` and wake the agent only when there is work, and a no-agent job can run a script with zero LLM calls.\[15\]\[36\] **Caveat:** cron scripts must live under `~/.hermes/scripts/` (or `%LOCALAPPDATA%\hermes` on Windows) and get a sanitized environment, so set `HO_TEAM` inside the script. Agent jobs only fire while the gateway is running.\[15\]\[37\]
- **Deciding who goes next:** either Hermes' LLM decides, which is nondeterministic, or your script decides, in which case Hermes adds nothing.
- **Strictly one session at a time:** no documented global mutex for cron agent jobs. Kanban has `dispatch --max N` per pass and concurrency settings, but Kanban workers are *Hermes profiles*, not Claude Code processes.\[38\]\[39\] A single Hermes turn running a blocking `terminal(… claude -p …)` serializes work only within that turn, and long Claude sessions run into terminal-tool timeouts and background-process handoffs. **You would need your own lock file.**
- **New session per phase:** this comes from Claude Code (`claude -p` starts a new session; `--resume <id>` continues one).\[25\] Hermes can pass these flags.
- **Carrying no task content between repositories:** Hermes' persistent memory and self-written skills *will* accumulate content from Claude Code's output across repositories by design.\[13\]\[40\]\[41\] That directly conflicts with your requirement 3. You can disable memory and skill generation, but then much of the reason to choose Hermes disappears.

### Q5. Models and accounts (confidence: high for providers; medium for how terms will be enforced)

- **Providers:** Nous Portal (subscription, 300+ models), OpenRouter (`OPENROUTER_API_KEY`), the OpenAI API, Anthropic (API key, or "Claude Max + extra usage credits via OAuth"), GitHub Copilot, any **custom OpenAI-compatible endpoint** (`hermes model` → Custom endpoint, `base_url` ending in `/v1`), and local Ollama/LM Studio/llama-server.\[42\]\[43\]\[44\] Fallback chains are configurable.\[44\]\[45\]\[46\]\[47\]
- **Cheap models:** this works (DeepSeek, Qwen, GLM and Kimi via OpenRouter), but the official Hermes Agent Quickstart sets a hard floor: "Hermes Agent requires a model with at least 64,000 tokens of context. Models with smaller windows … will be rejected at startup" (GitHub issue #53347 calls it "a hard minimum of 64,000 tokens for model.context_length"). Set the spend limit on the OpenRouter key itself; I found no Hermes-side spend cap. Data egress is **broader than you want**: Hermes' model receives its whole system prompt, memory, skills and every terminal output it reads, including Claude Code results, not just "stop text, team and handover ID".
- **Claude subscription:**
  - **Hermes does offer it.** Its official plugin `claude-subscription-directsdk` (experimental, listed 20 September 2026, v0.3.3 updated 14 October 2026) runs Hermes' own agent loop on a Pro/Max plan by driving the unmodified `claude` CLI as a model client. Its docs say "Hermes keeps its normal agent loop, tools, approvals and compaction."\[48\]
  - **Anthropic's Legal and compliance page (current October 2026)** says OAuth "is intended exclusively for … ordinary use of Claude Code and other native Anthropic applications". It also says: "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users … Anthropic reserves the right to take measures to enforce these restrictions … without prior notice." It adds that "Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and the Agent SDK."\[49\]\[50\]\[51\]\[52\]
  - The Agent SDK overview adds: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK."\[53\]\[54\]\[55\]
  - **Your presumption matches Anthropic's text:** do not run Hermes' own loop on your subscription.
  - **Running your own `claude` binary from your own script on your own PC** is the case the page carves out ("an end user signing in to the unmodified Claude Code binary with their own Claude subscription").\[49\]\[56\] Anthropic staff said publicly that "we want to encourage local development and experimentation with the Agent SDK and `claude -p`", reported by The New Stack.\[50\]\[57\] Unattended loops still draw on your plan limits.
  - **The separate credit pool was paused:** Anthropic had announced on 13 May 2026 that subscription Agent SDK usage would move to a separate monthly credit ($20 for Pro up to $200 for top-tier Max/Enterprise), but The New Stack (16 June 2026) reported that Anthropic told subscribers "We're pausing the changes to Claude Agent SDK usage" on the day it was due, with support docs updated to confirm "Agent SDK usage continues to draw from standard subscription limits and that no separate credit exists to claim." Check your own plan page.

### Q6. Windows (confidence: medium)

- **Officially native now.** The Windows (Native) Guide says "Hermes runs natively on Windows 10 and Windows 11 — no WSL, no Cygwin, no Docker", with a PowerShell installer (no admin), `hermes gateway install` as a Scheduled Task, and a feature matrix showing CLI, gateway, cron, MCP and dashboard all supported. Its terminal tool runs commands through **Git Bash**.\[10\]\[58\]
- **History matters.** Earlier 2026 guides (LumaDock, OpenClaw Launch) say the installer rejected native Windows.\[59\]\[60\] A community install guide calls native Windows "early beta" since v0.10.0.\[61\] Older articles are outdated, but support is young.
- **Known Windows issues relevant to you (from the Hermes issue tracker):**
  - #16425/#16426 (v0.11, April 2026): terminal commands returned empty output.\[58\]\[62\]
  - #31419: argv metacharacters re-parsed when spawning `.cmd` shims, which "most common case is `claude` … resolving to `claude.cmd`". This matters if Claude Code was installed through npm.\[63\]
  - #73403 and #135977: ACP/terminal hangs caused by `subprocess.run(timeout)` with Git for Windows.\[64\]\[65\]
  - #42544 and #131719: console windows flashing or lingering.\[66\]\[67\]
  - #121150: CLAUDE.md/AGENTS.md subdirectory hints don't load from native Windows paths.\[68\]
  - Several of these are fixed, but they show a steady flow of Windows edge cases.
- **tmux-based interactive control is not available natively.**

### Q7. Observability and control (confidence: medium)

- **Logs and transcripts:** `hermes logs` (agent/gateway/errors logs, with filters by `--session` and `--since`); `hermes sessions list/export --format html|jsonl`; the web dashboard (sessions, cron jobs, metrics, logs); Kanban event rows and per-task worker logs; `hermes cron pause/resume`; `/stop` to cancel a turn; plugin hooks such as `on_session_end` and `agent_loop_stopped`.\[8\]\[12\]\[69\]\[70\]
- **Crash handling:** Kanban reclaims crashed workers (PID gone) and auto-blocks after `failure_limit` spawn failures.\[1\] For an external `claude` child started through the terminal tool, I found no documentation on whether stopping Hermes terminates or orphans it.
- **A live bug report (#136713, October 2026):** a dashboard re-attach hard-interrupted in-flight turns and destroyed the work.\[71\] That is precisely the "half-controlled session" risk you want to avoid.
- **Claude Code's own transcripts:** saved per session under `~/.claude/projects/…`, independent of the orchestrator.

### Q8. Licence, maturity, cost (confidence: medium-high)

- **Licence:** MIT, per Nous' org page and the README; the bundled claude-code skill is also MIT.\[6\]\[18\]
- **First release:** 25 February 2026, announced in Nous Research's own launch post on X (@NousResearch): "Meet Hermes Agent, the open source agent that grows with you… Hermes Agent is open source and built in Python."
- **Latest:** v0.22.2 on 15 October 2026. The release notes say "v0.22.1 was built from the wrong commit … 0.22.2 is the release 0.22.1 was meant to be."\[72\]
- **Cadence:** very fast. v0.21.0 (31 August, "~5,800 commits … 760+ contributors" since v0.20) was followed by patches on 7, 11, 14 and 24 September and 8 and 11 October, and v0.22.0 on 13/14 October. v0.21.6 alone rolled up about 2,100 merged PRs.\[73\]\[74\]\[75\]
- **Stars and contributors:** 253,988 stars and 55,129 forks per GitHub's org page on 15 October 2026.\[6\] Contributors are around 4,200 per a third-party scan of 3 October 2026; I found no primary figure.\[76\]
- **Community:** Discord; r/hermesagent claims 75,000+ members per a community guide.\[77\] A third-party ecosystem index lists 250+ projects.\[78\]
- **Production users:** mostly blog and LinkedIn self-reports. A claim that NVIDIA chose Hermes as the reference runtime for Nemotron 3 Ultra comes from a secondary blog and is unverified.\[11\]
- **Cost:** the software is free. Optional paid Nous Portal subscription;\[79\] "Hermes Cloud" hosting is mentioned in release notes.\[47\]\[80\]\[81\] Your cost would be OpenRouter tokens.
- **Documentation:** extensive and current, though agent-generated in tone. The volume of change is a stability risk for a control loop.

## Q9. Fit verdict — requirements × Hermes Agent

| # | Requirement | Hermes Agent | Source / reason |
|---|---|---|---|
| 1 [M] | Drives Claude Code sessions on Windows 11 | **Partly** | Bundled claude-code skill (print mode via the LLM-driven `terminal` tool; tmux interactive mode not native on Windows); Windows (Native) Guide; issue #31419 (`claude.cmd` argv)\[18\] |
| 2 | Own model on own capped key; minimal egress; CC login untouched | **Partly** | Configuring Models/Providers docs (OpenRouter, custom endpoint); no Hermes spend cap; its LLM sees full terminal output and memory; the optional subscription plugin is a terms risk |
| 3 | Polls `ho inbox --json`, wakes the right team, carries no content | **Partly** | Cron docs (pre-check scripts, no-agent mode); persistent memory/skills accumulate cross-repo content by design |
| 4 [M] | Answers agreed stops, escalates the rest | **Not met** | Skill: print mode "skips" dialogs (they are denied, per Claude Code headless docs); no `--permission-prompt-tool`/`canUseTool` integration; only tmux screen-scraping |
| 5 [M] | Strictly one agent at a time | **Partly / unknown** | No documented global lock for cron agent jobs; Kanban `--max` applies to Hermes workers, not `claude` processes |
| 6 | Fresh session per phase, optional resume | **Met (via Claude Code flags)** | Skill documents `claude -p`, `--resume`, `--session-id`, `--fork-session`\[18\] |
| 7 | Archive gate (archive only after `close`; on return, back to the same change) | **Not met natively** | Would live in prompts/skills (LLM-enforced) or in your script; nothing in the docs |
| 8 [M] | Readable log per session; pause/stop without half-controlled sessions | **Partly** | `hermes logs`, sessions export, dashboard, cron pause, `/stop`; child-process handling on stop undocumented; bug #136713 |

**Glue code you would write even with Hermes:**
- the permission/question gate (an MCP server for `--permission-prompt-tool`, about 150 lines)
- the stop classifier and policy (about 100 lines)
- the single-run lock and queue (about 50 lines)
- the archive-gate state machine (about 80 lines)
- per-session structured logging (about 50 lines)
- Windows process-group stop handling (about 50 lines)

That is roughly 500 lines, the same as the standalone script, plus prompt engineering to keep Hermes' LLM from improvising.

**Simplest alternative (recommended):** one Python process, launched by hand or by Task Scheduler.

1. Check a `PAUSE` file, take a lock file, then for each team in priority order (product → app → backend → strategy) run `HO_TEAM=<team> ho inbox --json`.
2. Pick the first item. Map it to an action: for `action_required`, start or continue the change; for `to_review`, accept or return; once `close` is seen, issue the archive prompt. Build a prompt naming only the handover ID and next step.
3. Run `claude -p "<prompt>" --output-format stream-json --verbose --session-id <uuid> --permission-prompt-tool mcp__gate__decide --mcp-config gate.json` with `cwd=<repo>`, using `subprocess.Popen(..., creationflags=CREATE_NEW_PROCESS_GROUP)`. Run one at a time.
4. The gate MCP tool applies your allowlist policy. For agreed question types it answers "choose the best variant, record the assumption"; for anything else it denies with "escalated to owner" and raises a notice (toast, email or Telegram).
5. When the run ends, parse `result.subtype`, `stop_reason` and `permission_denials`. If `ho` state is unchanged and the text ends in a question, send only the final text to a cheap OpenRouter model (a capped key) to classify it. Then auto-continue with `--resume <id>` or escalate.
6. Append one JSONL line per session (team, handover ID, prompt, start/end, outcome, automatic answers, cost) and store the Claude transcript path.
7. Stop: send CTRL_BREAK (equivalent to SIGINT, so the turn ends cleanly) and release the lock.

This meets all eight requirements with code you fully understand, and it keeps `claude` exactly as the owner installed it.

## Recommendations

1. **Do not adopt Hermes Agent as the orchestrator.** Reconsider only if you later want phone/Telegram notifications and a dashboard. Even then, have Hermes *observe* (for example, a no-agent cron job that relays your script's escalation file to Telegram) rather than control `claude`.
2. **Build the script in three steps:** (a) the `claude -p` stream-json runner with logging, lock and pause; (b) the permission-prompt MCP gate; (c) the `ho`-driven state machine with the archive gate. Start with `--permission-mode default` plus your existing `.claude/settings.json` allowlists, so the gate sees only genuine prompts.
3. **Keep the subscription clean:** your script launches the unmodified `claude` binary under your own login and never reads its tokens. The orchestrator's LLM uses a separate OpenRouter key with a credit limit. Do not install `claude-subscription-directsdk`.
4. **Use Claude Code hooks as a backstop:** a `Stop` hook in each repo that writes a marker file (handover ID, last message) gives your script a second signal for early stops. Do not use exit-2 auto-continue until you have measured loop behaviour.

## Caveats and gaps (with quick tests on your machine)

- **AskUserQuestion in `claude -p` on your 2.1.x build: unverified, with conflicting reports.**
  - Test: `claude -p "Use the AskUserQuestion tool to ask me to pick A or B, then print my choice" --output-format stream-json --verbose --permission-prompt-tool mcp__gate__decide --mcp-config gate.json`.
  - Check whether the gate receives `tool_name: "AskUserQuestion"`, whether its answer is used, and what `permission_denials` contains without the gate.
- **`--permission-prompts` availability:** run `claude --help | findstr permission-prompt`. It needs v2.1.259 or later.\[21\]
- **Hermes on Windows with your `claude` install:** if you still want to try it, install it in a throwaway Windows user profile. Ask it to "run `claude -p 'print hello' --output-format json` in C:\repos\app" and check for empty output, `.cmd` quoting issues and console flashes. Then press `/stop` mid-run and check in Task Manager whether `claude.exe`/`node.exe` is orphaned.
- **One-at-a-time in Hermes cron:** create two agent cron jobs due at the same minute and watch whether they overlap. The docs don't say.
- **Subscription pool for `claude -p`:** The New Stack (16 June 2026) reported Anthropic paused the planned separate Agent SDK credit, and that support docs now confirm "Agent SDK usage continues to draw from standard subscription limits." Check your Claude account's usage page after a few unattended runs.
- **Hermes contributor count and production users:** only third-party figures were available. Star counts change daily.
- **Fast-moving targets:** both Hermes (several releases a week) and Claude Code (2.1.2xx) change flags and behaviour often. Pin your Claude Code version for the orchestrator and re-run the tests above after each update.

## Sources

1. [Kanban (Multi-Agent Board) | Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
2. [Hermes Agent — Use, configure, theme, extend, and orchestrate Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-hermes-agent)
3. [GitHub - HERMESquant/oh-my-hermes: Unified multi-agent orchestration for Claude Code + Codex CLI. One setup, both tools, seamless handoff. · GitHub](https://github.com/HERMESquant/oh-my-hermes)
4. [GitHub - xuyang-liu16/hermes-code-bridge: Use Hermes Agent as the control plane for local coding agents like Codex, Kimi Code, Claude Code, OpenCode, and Gemini CLI. · GitHub](https://github.com/xuyang-liu16/hermes-code-bridge)
5. [GitHub - 0xNyk/awesome-hermes-agent: Independent directory of useful skills, plugins, memory providers, tools, surfaces, and guides for Nous Research's open-source Hermes Agent. · GitHub](https://github.com/0xNyk/awesome-hermes-agent)
6. [Nous Research · GitHub](https://github.com/nousresearch)
7. [Hermes Agent GitHub Repo: Architecture and Contributing Guide](https://fast.io/resources/hermes-agent-github-open-source/)
8. [CLI Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)
9. [ACP Host Integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)
10. [Windows (Native) Guide | Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)
11. [The Complete Hermes Agent Guide for 2026](https://espressio.ai/blog/hermes-agent-guide/)
12. [Hermes Agent Session Management: Resume, Compress, Branch, and Prune · nyk](https://www.nyk.dev/blog/hermes-agent-session-management-guide)
13. [Hermes Agent Masterclass - by Avi Chawla](https://blog.dailydoseofds.com/p/hermes-agent-masterclass)
14. [Scheduled Tasks (Cron) - Hermes Agent - Nous Research](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)
15. [hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
16. [Release Timeline](https://hermesagents.net/evolution/)
17. [Install Hermes Agent](https://hermesagents.net/install/)
18. [Claude Code — Delegate coding to Claude Code CLI (features, PRs)](https://hermes-agent.nousresearch.com/docs/user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-claude-code)
19. [claude-code-hermes-delegation](https://lobehub.com/skills/xiaoquqi-hermes-agent-skills-claude-code-hermes-delegation)
20. [Claude Code Headless and Approvals: Unattended Without the Bypass Flag](https://agenticcontrolplane.com/blog/claude-code-headless-approvals)
21. [Run Claude Code programmatically - Claude Code Docs](https://code.claude.com/docs/en/headless)
22. [Codex App-Server Runtime (optional)](https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime)
23. [\[Feature\]: claude-code-print and cursor-agent-print SKILL.md for non-ACP coding CLI delegation · Issue #15300 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/15300)
24. [Bug: delegate\_tool.py docs claim 'claude --acp --stdio' works — Claude Code CLI has no --acp flag · Issue #19055 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/19055)
25. <https://code.claude.com/docs/en/cli-reference>
26. [--permission-prompts none in Claude Code (2026 Guide)](https://www.getclaudeskills.com/blog/claude-code-permission-prompts-none-flag)
27. [Handle approvals and user input - Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/user-input)
28. [Configure permissions - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/permissions)
29. [Handle approvals and user input - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/user-input)
30. [Permission prompts and questions through --permission-prompt-tool · Issue #163 · johnjuuljensen/GodMode · GitHub](https://github.com/johnjuuljensen/GodMode/issues/163)
31. [AskUserQuestion auto-resolves with empty answers in headless/no-TTY mode (Python Agent SDK) · Issue #50728 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/50728)
32. [Claude Code Hooks - prg.sh](https://prg.sh/notes/Claude-Code-Hooks)
33. [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
34. [Claude Code Hooks (2026): Block Claude Reading .env + 30 Hook Events, JSON Input, Exit Codes](https://www.morphllm.com/claude-code-hooks)
35. [Intercept and control agent behavior with hooks - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/hooks)
36. [Script-Only Cron Jobs (No LLM)](https://hermes-agent.nousresearch.com/docs/guides/cron-script-only)
37. [Scheduled Tasks (Cron)](https://hermes-agent.lzw.me/docs/en/user-guide/features/cron)
38. [Kanban in Hermes Agent for Self Hosted LLM Workflows - Rost Glukhov](https://www.glukhov.org/ai-systems/hermes/kanban-in-hermes/)
39. [Kanban (Multi-Agent Board)](https://docs.gormes.ai/upstream-hermes/user-guide/features/automation/kanban/)
40. [what is hermes agent openclaw alternative](https://www.mindstudio.ai/blog/what-is-hermes-agent-openclaw-alternative)
41. [GitHub - forkgitss/NousResearch-hermes-agent: The agent that grows with you · GitHub](https://github.com/forkgitss/NousResearch-hermes-agent)
42. [How to Add a Custom Provider to Hermes Agent (2026)](https://haimaker.ai/blog/hermes-custom-provider-setup/)
43. [FAQ & Troubleshooting](https://hermes-agent.nousresearch.com/docs/reference/faq)
44. [LLM and Model Providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)
45. [hermes-agent/website/docs/integrations/providers.md at main · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md)
46. [Hermes Agent Quickstart - Nous Research](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)
47. [GitHub - praxstack/NousResearch-hermes-agent: The agent that grows with you · GitHub](https://github.com/praxstack/NousResearch-hermes-agent)
48. [claude-subscription-directsdk · Plugin Catalog | Hermes Agent](https://hermes-agent.nousresearch.com/docs/plugins/claude-subscription-directsdk)
49. <https://code.claude.com/docs/en/legal-and-compliance>
50. [Anthropic: You can still use your Claude accounts to run OpenClaw, NanoClaw and Co. - The New Stack](https://thenewstack.io/anthropic-agent-sdk-confusion/)
51. [Anthropic Bans Claude Subscription OAuth in Third-Party Apps](https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/)
52. [Is This Allowed? Claude Code Terms of Service Explained · Autonomee](https://autonomee.ai/blog/claude-code-terms-of-service-explained/)
53. [Anthropic subscription blocked as third-party app — default provider should route through Claude Code CLI · Issue #3772 · gsd-build/gsd-2 · GitHub](https://github.com/gsd-build/gsd-2/issues/3772)
54. [Agent SDK overview - Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
55. [Agent SDK overview - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview)
56. [Claude Pro/Max Subscription with Hermes Agent — Why We Don’t Offer It](https://openclawlaunch.com/guides/hermes-claude-subscription)
57. [Or can you? It's my understanding that you cannot use your subscription with the...](https://news.ycombinator.com/item?id=47446703)
58. [\[Windows\] Terminal tool returns empty output on native Windows · Issue #16426 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/16426)
59. [Hermes Agent on Windows: WSL2 vs Desktop app guide - LumaDock](https://lumadock.com/tutorials/hermes-agent-windows-wsl2-vs-desktop)
60. [Run Hermes Agent on Windows — WSL2 + Docker Setup Guide](https://openclawlaunch.com/guides/hermes-agent-windows)
61. [How to Install Hermes Agent: Complete 2026 Setup Guide (macOS, Linux, Windows WSL2)](https://hermesatlas.com/guide/install/)
62. [\[Bug\]: Windows local terminal commands can complete without returning any output · Issue #16425 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/16425)
63. [\[Bug\] Windows: asyncio.subprocess\_exec misparses argv metacharacters when target is a .cmd/.bat shim · Issue #31419 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/31419)
64. [\[Bug\]: Windows ACP adapter hangs when executing terminal tool · Issue #73403 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/73403)
65. [\`hermes acp\`: \`session/new\` hangs forever on Windows - \`subprocess.run(timeout=5)\` never returns when a grandchild holds the stdout pipe · Issue #135977 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/135977)
66. [Windows: terminal tool flashes cmd window on every command execution · Issue #42544 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/42544)
67. [Windows: PTY terminal path spawns a visible console window (pipe path is correctly hidden) · Issue #131719 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/131719)
68. [bug(agent): subdirectory hints never load from native Windows paths in terminal commands · Issue #121150 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/121150)
69. [Event Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
70. [Hermes Agent Dashboard: Web UI Setup and Localhost Troubleshooting](https://hermes-agent.ai/tools/hermes-web-ui)
71. [\[Bug\]: Dashboard chat page re-attach (PTY/WS client disconnect) hard-interrupts the in-flight turn — work is destroyed, sessions close with end\_reason=tui\_shutdown · Issue #136713 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/issues/136713)
72. [Releases · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/releases)
73. [Hermes Agent: The Practitioner's Reference (2026)](https://blakecrosley.com/guides/hermes)
74. [Hermes Agent v0.21.0 The Pantheon Release](https://www.corpusiq.io/docs/hermes/changelog/v0.21.0)
75. [Hermes Agent 0.21.6](https://freedom.tech/posts/2026-10-08-hermes-agent-0-21-6/)
76. [Hermes Agent: The Self-Improving AI Agent From Nous Research (GitHub, Scanned)](https://www.mrtechking.com/hermes-agent-github/)
77. [hermes-agent-community/guides/windows-install.md at main · AtlasOmnia/hermes-agent-community · GitHub](https://github.com/AtlasOmnia/hermes-agent-community/blob/main/guides/windows-install.md)
78. [Hermes Agent Ecosystem — 250+ open-source tools, skills & integrations](https://hermesatlas.com/ecosystem/)
79. [Hermes Agent Desktop App: Everything You Need to Know About Nous Research’s Self-Improving AI Agent Going Mainstream](https://medium.com/@tentenco/hermes-agent-desktop-app-everything-you-need-to-know-about-nous-researchs-self-improving-ai-agent-3cb59bd31e5f)
80. [Hermes Agent by Nous Research: The Self-Improving Open-Source AI Agent, Explained](https://aiengineerinsights.com/blog/hermes-agent-nous-research-guide/)
81. [Hermes Agent Changelog (October 2026)](https://www.gradually.ai/en/changelogs/hermes-agent/)
