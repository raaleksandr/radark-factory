Received: 2026-10-17 · Tool: claude.ai Research

# Driving Claude Code unattended on a Pro/Max plan: interfaces and terms (as of 16 October 2026)

Shape A, where your own script drives Claude Code on your own machine, works. It is also permitted for your own personal use on a Pro/Max login, as long as the script launches the unmodified `claude` binary or uses the Agent SDK locally and never extracts or reuses your login token in another tool. Your working assumption is right about third-party programs, but too broad as you stated it. A program that runs its own agent loop and calls the model with your subscription credentials is not allowed and needs an API key. A script of your own that only launches `claude -p` is explicitly allowed on subscription limits. Shape B (a Claude Code dispatcher session using `/loop`, `SendMessage` and hooks) is technically possible on native Windows. It uses only first-party features, but it is less robust than Shape A and the docs do not describe it as an intended use.

## TL;DR
- **Interfaces:** headless mode, `Stop`/`PreToolUse`/`PermissionRequest`/`Notification` hooks and permission modes all work and are documented in detail (docs as of v2.1.299). `AskUserQuestion` can be answered programmatically with a `PreToolUse` hook (`allow` + `updatedInput`) or the SDK's `canUseTool`. The weak point is Windows. Issue reports on anthropics/claude-code describe hooks failing there: #46601 (v2.1.101, Windows 11) says "The Stop hook does not deliver stdin to the handler script on Windows when using pwsh", #36156 (v2.1.77) says hooks get stdin "as TTY instead of pipe", and #17424 (v2.1.4) says "PreToolUse hooks receive empty stdin on Windows". Test every hook you rely on.
- **Terms:** Anthropic's help centre says (update of 7 Oct 2026) "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits".\[1\] Its Claude Code legal page says OAuth is for "ordinary use of Claude Code and other native Anthropic applications", and that developers building products must use API keys.\[2\] Consumer Terms §3.7 still bans "automated or non-human means" except via API key "or where we otherwise explicitly permit it".\[3\]\[4\] The help-centre article is that explicit permission for `claude -p`/SDK.
- **Recommendation:** build Shape A as a small script with no model in it, using `claude -p --output-format stream-json` in each repo with hooks and `--permission-mode auto`. If the script needs an LLM to classify stops, give that call its own API key. Keep Shape B as an experiment only. Expect five-hour and weekly limits to be the real constraint on overnight runs.

## Key Findings — summary table

**Part 1 — interfaces (Claude Code 2.1.x; docs read 16 Oct 2026, latest version referenced v2.1.299)**

| # | Item | Answer |
|---|---|---|
| 1 | Headless `claude -p` loads CLAUDE.md, skills, slash commands, settings, hooks | **Works** (unless `--bare`) |
| 2 | `AskUserQuestion` in `-p`; deny or answer from hook/SDK | **Works** (answer via `updatedInput`, deny, or `defer`); tool is removed in some versions/flags |
| 3 | `Stop` hook `decision: block` + loop guard | **Works** (`stop_hook_active`, 8-in-a-row cap); Windows stdin bug reported |
| 4 | Permission modes incl. `auto`, `dontAsk`; `PermissionRequest` hook | **Works** |
| 5 | Agent SDK `canUseTool`, AskUserQuestion answering, resume, Windows | **Works** |
| 6 | `/loop`, `CronCreate`, `ScheduleWakeup`, `Monitor` | **Partly** (session-scoped, needs open terminal, 7-day expiry, Monitor needs Git Bash on Windows) |
| 7 | `ListAgents`/`SendMessage` between local sessions | **Works** on native Windows from v2.1.234 (named pipe); receiving session treats it as a peer message, not as the user |
| 8 | `Notification` hook / learning a session waits | **Works** (`idle_prompt`, `permission_prompt`, `agent_needs_input` matchers) |

**Part 2 — terms**

| Case | Answer | Key primary source |
|---|---|---|
| (a) Own script drives own `claude -p` unattended | **Allowed** (personal use) | Help centre: "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits."\[1\] |
| (b) Claude Code session as dispatcher | **Allowed in principle / unclear as "intended"** | Legal page: limits "assume ordinary, individual usage of Claude Code and the Agent SDK."\[2\] |
| (c) Third-party harness with own agent loop on subscription OAuth | **Not allowed** — use API key/Bedrock/Vertex | Legal page: no routing "through Free, Pro, or Max plan credentials on behalf of their users."\[2\] |
| (d) Usage limits for long runs | **Applies fully**: five-hour session + weekly limit (+ separate Fable weekly limit on Max) | Help centre: "Both Pro and Max plans have a five-hour session limit and a weekly limit."\[5\] |

## Details — Part 1: what the interfaces allow

### 1. Headless mode
- **Documented** (code.claude.com/docs/en/headless, living page, read 16 Oct 2026). Without `--bare`, `claude -p` "discovers and loads them as an interactive session would". That covers hooks, skills, custom commands, subagents, plugins, MCP servers, auto memory and CLAUDE.md. Project `.claude/settings.json` hooks run "even in a folder you've never trusted". User-invoked skills and custom commands work: "Include `/skill-name` in the prompt string", so `/opsx:apply` should expand. `--bare` skips all of this, and it "doesn't use your subscription login" (it needs `ANTHROPIC_API_KEY`). The docs say `--bare` "will become the default for `-p` in a future release".\[6\] That is a planned change, not current behaviour, but you should pin your flags because of it.
- **Outcome reporting:** "exits with code 0 on success and a non-zero code when the run fails". In-run failures such as missing authentication print as the result on stdout. With `stream-json`, the last line is a `result` message carrying the final text, cost and `session_id`. Denied permissions appear as `permission_denied` system messages and are listed in `permission_denials`. Retryable API errors emit `system/api_retry` with an `error` category (for example `rate_limit`). SIGTERM exits 143 and leaves the turn unfinished.\[6\] Resuming a session Claude ended exits 1.\[7\]
- **Resume:** `--continue` resumes the most recent conversation. `--resume <session_id>` resumes a specific one and "finds the session by its ID in any project on this machine".\[6\] `-p` sessions are hidden from the picker and from plain `--continue`, but `claude -p --continue` includes them.\[8\]
- **Reported issues:** v2.1.83 returned an empty `result` with `is_error:false` (issues #38805 and #38623, March 2026, macOS; fixed by downgrading at the time).\[9\]\[10\] A Stop hook caused an empty `-p` result (#38651, closed as duplicate April 2026).\[11\] These are fixed or closed, but they show you should check that `result` is non-empty rather than trusting `subtype: success` alone.
- **Windows:** no `-p`-specific differences are documented, apart from a fix for unreadable stdin before v2.1.211. The docs' example uses escaped double quotes "to keep the script portable to Windows".\[6\]
- **Confidence: high** (primary docs, plus issue history for the caveats).

### 2. Questions in headless mode
- **Documented behaviour.** The hooks reference says AskUserQuestion and ExitPlanMode "normally block in non-interactive mode with the -p flag".\[12\] Three documented answers exist:
  - **Answer it:** a `PreToolUse` hook matching `AskUserQuestion` returns `permissionDecision: "allow"` with `updatedInput` that echoes the `questions` array and adds an `answers` object.\[12\] This is the documented way to answer rather than deny.
  - **Deny it:** `permissionDecision: "deny"` with a `permissionDecisionReason`. Claude Code "shows Claude the reason", so the agent continues with that text. This fits your "choose the best variant and continue; record the assumption" rule.
  - **Defer it:** `permissionDecision: "defer"`. "The process exits with `stop_reason: "tool_deferred"`" and the pending call is kept,\[12\] so your controller can collect an answer from the owner and resume.
- **Tool availability varies:** `--permission-prompts none` (v2.1.259+) removes AskUserQuestion entirely, and `dontAsk` mode denies it even when an allow rule matches.\[6\] Issue #77994 reports the tool was callable in `-p` in v2.1.185 and removed in later versions.\[13\] Treat its presence in `-p` as version-dependent and check the `tools` list in `system/init`. Auto mode also "nudges Claude to keep working without stopping for clarifying questions".\[14\] When the tool is absent, the agent asks in plain text and ends the turn, which your `Stop` hook must handle (item 3).
- **Reported issues:** reports of AskUserQuestion returning empty answers interactively include #9854 (opened 18 Oct 2025, Linux), #29547 (v2.1.63, with plugin skills and `--dangerously-skip-permissions`) and #47114 (v2.1.104 on Windows 11 with bypassPermissions, described as a "regression from v2.1.101"). In #13439 a configured `PreToolUse` hook caused empty responses; #30523 says that was "fixed in 2.0.76". Validate your hook output carefully.
- **SDK:** AskUserQuestion reaches `canUseTool` with `toolName == "AskUserQuestion"`.\[15\] You answer by returning allow with `updatedInput` containing the answers.\[15\]
- **Confidence: high** for the documented mechanisms; **medium** for the exact behaviour in your 2.1.x build.

### 3. Early stops
- **Documented:** a `Stop` hook returning `decision: "block"` with a `reason` "prevents Claude from stopping". The reason is fed back to the agent, and `additionalContext` can give non-error feedback. Loop prevention: the input carries `stop_hook_active` (true when "already continuing as a result of a stop hook"), and Claude Code applies an "8-consecutive-continuation cap".\[16\] `SubagentStop` uses the same pattern. Stop input also includes `last_assistant_message`, `background_tasks` and `session_crons`,\[16\] so your hook can tell a question in plain text apart from a finished task.
- **Windows reports:** #46601 (Windows 11, v2.1.101, stale): the Stop hook received no stdin under pwsh.\[17\] #88896 (v2.1.240, open at time of reading): PreToolUse hooks never fired on Windows, though Stop and SubagentStop were reported unaffected.\[18\] #90077 (v2.1.247): `shell: "powershell"` spawns `pwsh` with no fallback to `powershell.exe`, so hooks silently never run on a stock box.\[19\] Hooks default to Git Bash when it is installed.\[16\]
- **Confidence: high** (docs); **medium** on Windows reliability.

### 4. Permissions
- **Modes (permission-modes doc):**
  - `default` (labelled "Manual"): reads only.\[14\]
  - `acceptEdits`: file edits plus common filesystem commands.\[14\]
  - `plan`: no source edits.
  - `auto`: a classifier reviews actions and blocks scope escalation, unknown infrastructure and hostile-content-driven actions.\[20\]
  - `dontAsk`: anything that would prompt is denied.\[14\]
  - `bypassPermissions` / `--dangerously-skip-permissions`: for "Isolated containers and VMs only".\[14\]
- **Starting mode:** auto is the default starting mode for interactive sessions from v2.1.283, but `claude -p` starts in `default` in sessions that fetch feature flags, so pass `--permission-mode` explicitly. The auto default on native Windows needs v2.1.233+.\[14\]
- **How auto fails:** if the classifier blocks "3 times in a row or 20 times total", auto pauses. In `-p` without a prompt host, the blocked action "doesn't run and the run continues".\[14\]\[21\]
- **Unmatched requests in headless:** in a `-p` run with no host, "these requests are denied either way".\[6\]
- **`PermissionRequest` hook:** exists. It returns `decision.behavior` allow or deny,\[16\] and fires "when it would otherwise auto-deny a call that can't prompt".\[16\]
- **Actions no mode auto-approves:** ask rules, AskUserQuestion, and critical-path `rm`.\[14\]
- **Confidence: high.**

### 5. Agent SDK
- `canUseTool` fires for unapproved tools and for AskUserQuestion. It "can stay pending indefinitely", and the docs suggest a `defer` PreToolUse hook if the user may take long. It never fires for auto-approved tools, so use `PreToolUse` hooks for logic that must see every call.\[15\]\[22\]
- Resume is by session ID. Hooks include Stop, SubagentStop and PermissionRequest. Windows is documented: the Python quickstart has a PowerShell `Activate.ps1` path.\[23\]\[24\]
- Use of the SDK is governed by the Commercial Terms.\[25\] Subscription use of the SDK is covered in Part 2.
- **Confidence: high.**

### 6. `/loop` and scheduling
- **Documented (scheduled-tasks doc):**
  - `/loop 5m <prompt>` runs on a fixed cron schedule.\[26\]
  - `/loop <prompt>` is self-paced: Claude picks a delay "between one minute and one hour" through `ScheduleWakeup`, and can end the loop with `stop: true`.\[26\]
  - A bare `/loop` runs a maintenance prompt or `loop.md`.\[26\]
  - Fires happen "between your turns", "only while Claude Code is running and idle".\[26\]
  - "Closing the terminal or letting the session exit stops them firing."\[26\]
  - There is no catch-up for missed fires.\[26\]
  - Recurring tasks "expire 7 days after creation", with a maximum of 50 tasks per session.\[26\]
  - A self-paced loop isn't restored on `--resume`.\[26\]
  - Jitter applies: hourly tasks may run up to 30 minutes late.\[26\]
- **Monitor:** watches have a 5-minute default, a 30-minute maximum, and 10 minutes in a single-prompt `-p` run. "On Windows, the tool is available only when Git Bash is installed."\[7\]
- **Sleep / terminal close:** not explicitly documented for sleep. Since tasks fire only while the process runs and there is no catch-up, expect a missed fire after sleep followed by a single catch-up fire when the session becomes idle again. Backgrounding the session keeps `/loop` running without a terminal.\[26\]
- **Idle cost:** between fires nothing runs. Each fire is a full turn that counts toward usage "like a prompt you type".\[27\] The main conversation on a subscription within plan limits uses a one-hour prompt-cache TTL, so wake-ups within an hour mostly re-read a cached prefix. Anthropic does not publish how cache reads weigh against quota (secondary source),\[28\] so the per-wake-up cost is **unknown** and has to be measured with `/usage`.
- **Confidence: high** (mechanics); **low** (quota cost per wake-up).

### 7. Messaging between local sessions
- **Documented (cross-session-messaging doc):**
  - Requires "v2.1.224 or later" on macOS/Linux/WSL and "v2.1.234 or later on native Windows". It is on by default with no flag and works on every plan and provider.\[27\]
  - On native Windows it uses a per-session named pipe, and connections must authenticate with `CLAUDE_CODE_MESSAGING_TOKEN`.\[27\]
  - WSL 2 and native Windows sessions "can't reach each other".\[27\]
  - An idle receiving session starts a new turn with the message; during a turn it reads the message between tool calls.\[27\]
  - The message is labelled as coming from another session, "can't approve anything", and slash commands in it "arrive as plain text",\[27\] so `/opsx:apply` cannot be triggered this way.
  - Default inbound policy depends on permission modes. A bypassing receiver holds messages for approval.\[27\]
  - `claude -p` sessions bind an inbox too. Set `crossSessionInbound: "accept"` via `--settings` for unattended workers.\[27\]
  - Loops are throttled, with at most 50 queued messages.\[27\]
  - `notify_when_idle` gives one notice when a session goes idle (12-hour expiry).\[27\]
  - Desktop-app sessions "can't send cross-session messages from a session nobody is watching".\[29\]
  - The auto-mode classifier reviews each `SendMessage`.\[14\]
- **Confidence: high** (docs); **medium** for Windows in practice, since the Windows feature is newer.

### 8. Notifications
- The `Notification` hook matches `permission_prompt`, `idle_prompt`, `agent_needs_input`, `agent_completed` and others. `StopFailure` fires when a turn ends on an API error,\[29\] with matchers including `rate_limit`. Notification hooks cannot block. `terminalSequence` is ignored in `-p`,\[16\] so use the hook to write a file or call your controller over HTTP (`type: "http"` hooks exist).
- For headless runs the simpler signal is process exit plus the final `result` line. For interactive sessions, use the `Notification` and `Stop` hooks.
- **Confidence: high.**

## Details — Part 2: terms (primary sources first)

### (a) Script-driven agents on your own machine — **allowed for personal use**
- **Consumer Terms §3.7** (anthropic.com/legal/terms, in force since at least Feb 2024 per The Register) bans automated access "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it".\[3\]\[4\]\[30\]
- **Explicit permission:** help-centre article 15036540 (updated 7 Oct 2026): "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits."\[1\] Article 17154008 also says that when signed in with your plan, "`claude -p` and Agent SDK usage still draw from your plan's usage limits."\[31\]
- **Staff statement (primary, X, 18 Feb 2026, Thariq Shihipar, Claude Code team):** "We want to encourage local development and experimentation with the Agent SDK and claude -p." and "If you're building a business on top of the Agent SDK, you should use an API key instead."\[32\]
- **Limit on "non-human" use:** the legal page says advertised limits "assume ordinary, individual usage of Claude Code and the Agent SDK".\[2\] There is no stated frequency cap beyond the plan limits.
- **Conflict to note (secondary):** a GitHub issue on multica-ai/multica (#1497) quotes an Anthropic support reply. It says a third-party tool invoking the CLI with Pro/Max credentials, including on cron, "would not be permitted".\[33\] That is a forum report of a support email, not a term. It is about a third-party orchestrator, and it conflicts with the later help-centre wording.
- **Your case:** you run a commercial one-person company. The Consumer Terms note that organisations fall under the Commercial Terms,\[34\] and staff advise an API key for "building a business". You are using Claude Code for your own development work, not reselling it, which reads as ordinary individual use. This is still the grey zone of (a).
- **Confidence: medium-high.**

### (b) A Claude Code dispatcher session — **allowed in principle; "intended use" unclear**
- Every feature in Shape B is first-party and documented for unattended-ish use. `/loop` is for "quick polling during a session". Cross-session messaging exists so "sessions you run yourself can pass findings and status between themselves".\[26\]\[35\] `-p` workers are expressly supported as message receivers.\[27\]
- No primary source describes a Claude dispatcher orchestrating other sessions on a schedule. The same "ordinary, individual usage" limit framing applies.
- The auto-mode classifier treats driving Claude Code's own interface (for example, sending keystrokes to its own tmux pane) as Claude changing its own oversight.\[36\] A dispatcher that tries to auto-approve other sessions would collide with this. Messages also "can't approve anything".\[27\]
- **Confidence: medium.**

### (c) Third-party programs and subscription OAuth — **not allowed; use an API key (or Bedrock/Vertex)**
- **Legal page (live, read 16 Oct 2026):**
  - OAuth is "designed to support ordinary use of Claude Code and other native Anthropic applications".\[2\]
  - Developers building products "including those using the Agent SDK, should use API key authentication".\[2\]
  - "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications".\[2\]
  - Developers "may not collect, store, or intermediate Claude.ai credentials or session tokens".\[2\]
  - The page does not prevent "an end user from signing in to the unmodified Claude Code binary with their own Claude subscription".\[2\]
- **Agent SDK overview:** "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products".\[25\]
- **Timeline (secondary unless noted):**
  - 9 Jan 2026: server-side block of spoofed Claude Code clients.\[37\]
  - 18–20 Feb 2026: docs added a sentence calling OAuth use "including the Agent SDK" a violation.\[30\] On X on 18 Feb 2026, Thariq Shihipar (@trq212) wrote: "Apologies, this was a docs clean up we rolled out that's caused some confusion. Nothing is changing about how you can use the Agent SDK and MAX subscriptions!" (primary). The sentence is no longer on the live page; removal date unknown.
  - 3 Apr 2026: Boris Cherny (primary, X): "Claude subscriptions will no longer cover usage on third-party tools like OpenClaw." Anthropic's customer email, posted on Hacker News, set the start as "April 4 at 12pm PT / 8pm BST". TechCrunch quotes the same email: the policy "applies to all third-party harnesses and will be rolled out to more shortly." In the same X thread, Cherny wrote: "You can still use these tools with your Claude login via extra usage bundles (now available at a discount), or with a Claude API key."
  - May–Jun 2026: a planned separate Agent SDK credit was announced, then "paused" on 15 Jun (primary).\[1\]\[38\]\[39\]\[40\]
  - 7 Oct 2026: Max/Team plans include monthly API credits that cover the SDK and `claude -p` when used with an API key from the linked Console org (primary).\[1\]\[31\]\[38\]
- **`claude setup-token`:** documented for CI and scripts (GitHub Actions: "authenticates with your Claude subscription, available on Pro, Max").\[41\] Handing that token to a non-Anthropic harness is what the "intermediate ... session tokens" rule forbids.
- **Inconsistency:** the 7 Oct help text says "third-party apps" may use subscription limits. Against that, Cherny's April post excludes third-party tools, and an Anthropic spokesperson told The Register (6 Apr 2026): "Starting April 4, third-party tools will draw from extra usage instead of subscription limits… Using Claude subscriptions with third-party tools isn't permitted under our Terms of Service". Read "third-party apps" as apps built on the Agent SDK running the official runtime under your own login. Do not rely on it for a custom loop.
- **Practical answer for your shape A:** a cheap classifier model inside your controller must use its own OpenRouter or Anthropic API key, which is what you planned. Max-plan API credits can fund it.\[42\]
- **Confidence: high** that a third-party loop needs an API key; **medium** on the exact boundary of "third-party apps".

### (d) Usage limits — **apply fully to unattended runs**
- **Help centre 11145838 (updated this week):**
  - "Both Pro and Max plans have a five-hour session limit and a weekly limit." Max also has a separate Fable weekly limit.\[5\]
  - Limits are "shared across Claude and Claude Code".\[5\]
  - Hitting the session limit mid-response may allow a capped "wrap-up" ("Usage limit reached · wrapping up").\[5\] This is rolling out gradually.\[5\]
  - After that you either enable usage credits (pay-as-you-go) or wait for the reset.\[5\]
- **Max plan article:** Anthropic "may limit your usage in other ways, such as weekly and monthly caps ... at our discretion".\[43\] It publishes no token numbers.
- **Idle dispatcher:** zero usage between fires. Each wake-up costs a turn whose size grows with the conversation. The one-hour subscription cache softens this, but there is no published conversion to quota (unknown).\[28\]
- **Mid-run behaviour in `-p`:** not fully documented. Expect `api_retry`/`StopFailure` with `rate_limit`, then a failed or ended run. Test it (see Open points).
- **Confidence: high** (limit structure); **low** (exact `-p` behaviour at the limit).

## Recommendations
1. **Build Shape A.** Use a PowerShell or Python controller that polls `ho inbox --json` and starts one `claude -p "/opsx:<phase> ..." --output-format stream-json --verbose --permission-mode auto` per phase in the right repo. It should read the final `result`/`is_error`/`permission_denials`, and use `--resume <id>` only when a phase must continue.
2. **Put the auto-answer policy in project hooks:**
   - `PreToolUse` on `AskUserQuestion`: `deny` with "choose the best variant and continue; record the assumption in <file>", or `allow`+`updatedInput` for agreed question types, or `defer` to escalate.
   - `Stop`: block once on plain-text questions or premature ends, guarded by `stop_hook_active`.
   - `PermissionRequest`: allow or deny by rule.
   - `Notification`/`StopFailure`: write to a log your controller reads.
3. **Escalation:** treat `tool_deferred`, a non-zero exit, `rate_limit`, or a second Stop block as "wake the owner".
4. **Write hooks for native Windows** as exec form (`"command": "powershell.exe", "args": [...]`), match `Bash|PowerShell`, and install Git Bash, which Monitor needs.\[16\]
5. **Keep any LLM in the controller on its own API key** with a spend cap. Never reuse `setup-token` output outside Claude Code.
6. **Treat Shape B as an experiment**, because of the session-scoped schedules, terminal dependency, 7-day expiry and unknown idle cost. If you want a local, durable schedule, Desktop scheduled tasks are first-party and see local files. Routines run in the cloud on a fresh clone and do not see local files.\[26\]

## Caveats
- Docs pages are living documents with no per-page dates. Everything here was read on 16 Oct 2026, when docs referenced versions up to v2.1.299. Your 2.1.x build may predate features such as `--permission-prompts` (v2.1.259), native-Windows messaging (v2.1.234) or `onFailure` (v2.1.295).
- Terms in this area changed in January, February, April, June and October 2026. Re-check before relying on (a)–(c).
- GitHub issues and blogs are reported experience, not terms or confirmed behaviour.

## Open points to test on your Windows machine
1. **Config loading in `-p`:** run `claude -p "/opsx:apply --dry" --output-format stream-json --verbose` in a team repo. Check that `system/init` lists your skills, slash commands and hooks, and that a test hook writes a marker file.
2. **AskUserQuestion availability:** run `claude -p "Call AskUserQuestion with two options"`. Check the `tools` list and whether your `PreToolUse` hook fires (deny, `updatedInput` answer, and `defer` → `stop_reason: tool_deferred`).
3. **Stop hook stdin on Windows:** register a Stop hook that dumps stdin to a file under both Git Bash and `powershell.exe` exec form. Confirm `stop_hook_active` and `last_assistant_message` arrive (relevant reports: #46601, #88896, #90077).
4. **Permission fallback:** run with `--permission-mode auto` and a deliberately unallowed command such as a network call. Check `permission_denials`, and that the run continues and exits 0.
5. **Exit codes:** compare normal completion, a forced auth failure (log out), and Ctrl+C or SIGTERM-equivalent kill on Windows (documented as 143 on SIGTERM).
6. **Cross-session messaging:** open two terminals on v2.1.234+, run `/list-agents`, send a message, and confirm the idle receiver starts a turn. Repeat with a `-p` worker started with `--settings '{"crossSessionInbound":"accept"}'`.
7. **`/loop` and sleep:** start `/loop 10m check ho inbox --json`, sleep the PC for 30 minutes, wake it, and count fires. Check `/usage` before and after a few idle fires to measure the cost per wake-up.
8. **Limit behaviour:** near a five-hour limit, run a long `-p` task and record the `api_retry` events, final `result`, `is_error` and exit code.
9. **Auth source:** make sure no `ANTHROPIC_API_KEY` is set in the controller's environment. In `-p` it always overrides your subscription and bills the API.\[5\]\[44\]

## Sources

1. [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
2. <https://code.claude.com/docs/en/legal-and-compliance>
3. [Consumer Terms of Service](https://anthropic.com/legal/terms)
4. [Is This Allowed? Claude Code Terms of Service Explained](https://autonomee.ai/blog/claude-code-terms-of-service-explained/)
5. [Use Claude Code with your Pro or Max plan | Claude Help Center](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan)
6. <https://code.claude.com/docs/en/headless>
7. <https://code.claude.com/docs/en/tools>
8. [Manage sessions - Claude Code Docs](https://code.claude.com/docs/en/sessions)
9. [claude -p returns empty result field despite model generating response · Issue #38805 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/38805)
10. [\[BUG\] v2.1.83: -p (print) mode returns empty result while tokens are generated and billed · Issue #38623 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/38623)
11. [\[BUG\] Stop hook causes empty result in print mode (-p) · Issue #38651 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/38651)
12. [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks?amp=&amp=)
13. [\[BUG\] \[-p / print mode\] AskUserQuestion tool was available in 2.1.185 but removed in later versions — please make it opt-in instead of hard-disabling · Issue #77994 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/77994)
14. [Choose a permission mode - Claude Code Docs](https://code.claude.com/docs/en/permission-modes)
15. [Handle approvals and user input - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/user-input)
16. [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
17. [Bug Report: Claude Code Stop hook does not receive stdin on Windows (PowerShell 5.1 + pwsh 7) · Issue #46601 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/46601)
18. [PreToolUse hooks never fire on Windows (v2.1.240) · Issue #88896 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/88896)
19. [\[BUG\] Hooks with \`shell: "powershell"\` spawn \`pwsh\` with no \`powershell.exe\` fallback, so hooks silently never run on a stock Windows box · Issue #90077 · anthropics/claude-code · GitHub](https://github.com/anthropics/claude-code/issues/90077)
20. [Best practices for Claude Code - Claude Code Docs](https://code.claude.com/docs/en/best-practices)
21. [Error reference - Claude Code Docs](https://code.claude.com/docs/en/errors)
22. [Configure permissions - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/permissions)
23. [Quickstart - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/quickstart)
24. [Agent SDK reference - Python - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/python)
25. [Agent SDK overview - Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview)
26. [Run prompts on a schedule - Claude Code Docs](https://code.claude.com/docs/en/scheduled-tasks)
27. <https://code.claude.com/docs/en/cross-session-messaging>
28. [Claude Code idle compaction: idleCompaction, CLAUDE\_CODE\_IDLE\_COMPACT\_MIN\_TOKENS and the 1-hour prompt cache](https://max.nardit.com/articles/claude-code-idle-compaction-prompt-cache)
29. [Desktop application - Claude Code Docs](https://code.claude.com/docs/en/desktop)
30. [Anthropic clarifies ban on third-party tool access to Claude](https://www.theregister.com/software/2026/02/20/anthropic-clarifies-ban-on-third-party-tool-access-to-claude/5014546)
31. [Monthly API credits for Max and Team plans](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans)
32. [Thariq on X: "We want to encourage local development and experimentation with the Agent SDK and claude -p. If you’re building a business on top of the Agent SDK, you should use an API key instead. We’ll make sure that’s clearer in our docs." / X](https://twitter.com/trq212/status/2024212380142752025)
33. [\[Question\] Does using multica violate Anthropic's Consumer Terms of Service? · Issue #1497 · multica-ai/multica · GitHub](https://github.com/multica-ai/multica/issues/1497)
34. [ce2bf436 0a91 4da2 a756 b2289fc755cd](https://www.anthropic.com/legal/archive/ce2bf436-0a91-4da2-a756-b2289fc755cd)
35. [Run agents in parallel - Claude Code Docs](https://code.claude.com/docs/en/agents)
36. [https://code.claude.com/docs/en/permission-modes?s...](https://code.claude.com/docs/en/permission-modes?campaign=dsass&plan=custom&interval=annually)
37. [Why 157,000 developers are hedging against Anthropic with OpenCode - The New Stack](https://thenewstack.io/anthropic-claudecode-opencode-split/)
38. [Claude Agents SDK will no longer use subscription; API credits included in plans](https://news.ycombinator.com/item?id=49997654)
39. [Anthropic splits billing again: Agent SDK gets separate credit pools - The New Stack](https://thenewstack.io/anthropic-agent-sdk-credits/)
40. [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026)
41. [Claude Code GitHub Actions - Claude Code Docs](https://code.claude.com/docs/en/github-actions)
42. [Free Claude API Credits on Max and Team Plans: How to Claim Up to \$500 a Month](https://aicatchup.com/news/claude-max-team-free-monthly-api-credits)
43. [What is the Max plan?](https://support.claude.com/en/articles/11049741-what-is-the-max-plan)
44. <https://code.claude.com/docs/en/authentication>
