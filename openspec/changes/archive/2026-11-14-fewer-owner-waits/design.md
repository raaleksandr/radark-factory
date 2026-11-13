# Design: fewer and shorter owner waits

Handover HO-20261113-armh (RB-014). Run unattended: every choice below that the handover left open was made here
and is marked **Assumption**.

## Context

- Sessions run `claude -p … --permission-mode auto --permission-prompts none --settings <run_dir>/session-settings.json`
  in the team repository. Our hooks today: `SessionStart`, `PreToolUse:AskUserQuestion`, `Stop`, `StopFailure`
  (`radark/runner.py:write_session_settings`).
- A denied tool call shows up only in the final result's `permission_denials`; `classify` makes such a session
  `waiting_for_owner`; `after_session` turns it into `finished` + `denial_not_escalated` when the phase signal
  appeared (escalate-denial D1/D2), otherwise escalates with the reason `permission denied: <tool>` — no command,
  no why, no suggestion.
- `BLOCKED: owner — …` is parsed only in apply and act; `BLOCKED_NOTE` and `consult_prompt` say nothing about the
  team's own decision policy.

## Goals / Non-Goals

Goals: a routine denial comes with an allowed way (or the narrow form is allowed); a session that still stops on
a denial asks the owner one clear question; deciding teams are told to decide what their policy allows and to
inform the owner without blocking.

Non-goals: setting any pipeline's actual policy (the owner's task); changing escalation keywords or their routing;
changing the "phase complete" signals of escalate-denial D2; any `ho` change.

## Decisions

### D1. A `PreToolUse` guard hook, not a `PermissionDenied` hook

The only point where the engine can attach its own text to a denial, and can allow a narrow form, is before the
permission mode decides: a `PreToolUse` hook returning `permissionDecision: "deny"` with a
`permissionDecisionReason` (shown to the model) or `"allow"`. New script `radark/hooks/guard.py`, registered in
`session-settings.json` for the matchers `Bash`, `PowerShell`, `Write`, `Edit` (exec form, like the others).
When it recognises nothing it prints nothing and exits 0: the permission mode decides exactly as before.

**Assumption:** a hook `allow` skips the auto-mode classifier on the tested Claude Code version (2.1.302), as the
hook documentation says for permission prompts. Task 1.1 verifies it with a real session in the sandbox before the
allow paths are relied on. If it does not hold, the allow paths become deny-with-reason paths naming the same
narrow form ("run exactly `git restore -- <file>`" would then also be denied, so the reason names re-writing the
file and the task tool instead); record the outcome in this design.

**Outcome of task 1.1 (2026-11-14, Claude Code 2.1.325, Windows 11, a throw-away git repository and hook, removed
afterwards):** (a) holds: a `deny` with `permissionDecisionReason` reached the model verbatim (shown as
`PreToolUse:Bash hook error: <reason>`) and the call was recorded in the result's `permission_denials`. (b) An `allow`
let `git checkout -- a.txt` run with no denial recorded. Whether an `allow` overrides an auto-mode classifier
*denial* could not be reproduced: in the throw-away repository the classifier allowed every candidate without a hook
(`git checkout -- a.txt`, `git reset --hard`, `git clean -fdx`), since it judges by context. Decision: keep the allow
paths. An allow never widens anything the classifier would allow anyway, and if a classifier denial still wins on
some version, the session gets the denial plus the denial rule (D6), which names re-writing the file and the task
tool as the other ways; so the fallback's wording is already in place.

### D2. Parsing commands conservatively

The hook decides only on a **single simple command**: after trimming, the command must not contain `;`, `&&`,
`||`, `|`, a newline, backticks, `$(`, or redirections, otherwise only the deny rules (D3–D5) may apply, never an
allow. Arguments are split with `shlex.split(posix=False)`-style handling plus quote stripping. This keeps every
allow decision to exactly the narrow form ("Restore combined with another command" scenario).

### D3. Discarding working-tree edits (allowed, narrow)

Allowed: `git restore [--worktree] [--staged|-S] [-W] [--] <path>…` and `git checkout -- <path>…`, where every path,
resolved against the session's working directory, is an existing **file** (not a directory) inside the repository
root (`HARNESS_REPO`, see D7), with no `*?[`, no leading `:` (pathspec magic) and not `.`. `--source`/`-s`, `-p`,
`--ours/--theirs`, `--merge` or any other option → not allowed.

Denied with reason (the same command family in a broad form: `.`, a directory, a wildcard, pathspec magic, a path
outside the repository, `--source`):

> Discarding edits is allowed only for named files of this repository: run `git restore -- <file> [<file>…]`
> (one command, nothing else on the line), or re-write each file with the edit tool. Whole-tree or out-of-repository
> discards stay denied.

Why it is safe: it changes only the uncommitted content of named files of the team's own repository, the same thing
the `Write` tool may already do to those files; the dispatcher runs one session at a time, so the uncommitted
edits are the session's own (**Assumption:** the owner does not keep uncommitted manual work in a team repository
while a pipeline runs; README says so). Commits, other repositories, the hub and the remote are untouched.
`git reset --hard`, `git clean`, `git stash drop` are not named: the permission mode decides them as before.

### D4. Stopping the session's own processes (allowed, narrow)

Recognised: PowerShell `Stop-Process` (`-Id`/`-ID`/positional IDs, `-Name`, `-InputObject`/piped), `taskkill`
(`/PID n`…, `/IM name`, `/T`, `/F`), POSIX `kill [-9|-TERM…] <pid>…`, `pkill`, `killall`.

Allowed: stop by ID when every ID is a descendant of the session's Claude Code process. The session root is the
hook's parent process (`os.getppid()`; hooks run in exec form, spawned by Claude Code). The process table comes from
one PowerShell call `Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId | ConvertTo-Json` on Windows,
`ps -A -o pid=,ppid=` elsewhere (stdlib `subprocess`, 15 s limit; on any failure → not allowed, D5 reason). The
root itself and the hook's own chain upward are never allowed targets.

Denied with reason (by name or image, or an ID outside the tree):

> Stop only processes this session started, by their ID: `Stop-Process -Id <pid>` (or `taskkill /PID <pid> /T /F`)
> is allowed for processes started in this session. Better: start servers as background tasks and stop them with
> the task tool. Processes by name or not started by this session stay denied.

Why it is safe: a process descended from the session's own Claude Code process was started by that session (or by
a tool it ran); stopping it affects nothing outside the session.

### D5. Temporary files

The dispatcher gives every session `<run_dir>/tmp/<team>/` (created if missing) through `--add-dir`, and sets
`TEMP`, `TMP`, `TMPDIR` to it; the original values are passed to hooks as `HARNESS_SYSTEM_TEMP`
(`os.pathsep`-joined). `$env:TEMP` / `%TEMP%` / `$TMPDIR` in a command thus already point to the allowed place.

Denied with reason: `Write`/`Edit` whose `file_path` is under a system temp directory (`HARNESS_SYSTEM_TEMP` entries
or `/tmp`), and a `Bash`/`PowerShell` command that contains such a path (case-insensitive, either slash):

> Temporary files go to `<run_dir>/tmp/<team>/` (it is also `$TEMP`/`$TMP` in this session); write them there.

**Assumption:** the directory is never cleaned by the dispatcher (no deletes by the engine; it is small and under the
run directory the owner manages); README says so. One directory per team, not per session, so a resumed session finds
its files.

### D6. Denial rule in the system prompt

`--append-system-prompt` becomes `STANDING_RULE + "\n\n" + long_wait_rule(...) + "\n\n" + denial_rule(temp_dir)`:

> Denied commands: if the permission mode denies a command, do not stop. Do the same another allowed way:
> temporary files go to `<temp dir>`; to drop an edit, run `git restore -- <file>` naming the files, or re-write
> them; stop only processes you started, by their ID (`Stop-Process -Id <pid>`), or run servers as background tasks
> and stop them with the task tool. A hook message on a denial names the allowed way. If the phase cannot be
> completed without the denied command, end your final message with one line
> `BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <what you propose>`.

The exact system-prompt assertion in `test_runner.py` is extended by this rule (the only existing test whose
expected text changes; the change is the new rule itself).

### D7. Hook environment

`session_env` adds `HARNESS_REPO` (team repository root), `HARNESS_TEMP` (the session temp dir) and
`HARNESS_SYSTEM_TEMP`. Hooks keep importing only `hookcommon`.

### D8. One clear question for a denial

In `after_session`, for a work session that ends `waiting_for_owner` with denials and is escalated (the D1 path of
escalate-denial did not turn it into `finished`):

- `BLOCKED: owner — …` is parsed for the denial case in **every** work phase (propose, apply, act, review,
  archive); the general BLOCKED rule stays apply/act only.
- reason: unchanged prefix `permission denied: <tool>` per denial (the existing "Denial with an incomplete phase"
  scenario still holds);
- question: the BLOCKED text if given, otherwise
  `The permission mode denied <tool> `<input>` [, …] and the session ended without completing the <phase> phase. How should the team go on?`;
- body: a new `## Denied` section listing `- <tool>: `<input, 200 chars>`` per denial (from `denial_entry`).

There is still exactly one `escalate()` call per session end and at most one open escalation handover per item (the
existing rule), so several denials never make several escalations.

### D9. Teams decide what their policy allows

`BLOCKED_NOTE` (apply, act) gets, before the BLOCKED sentence:

> If a decision is needed that your team's instructions (your `CLAUDE.md`, the owner's goal) allow your team to
> take, take it: record it in the change (or the handover result) and inform the owner with a non-blocking handover
> (`ho new --to <owner team> --expects ack --auto-close`), then continue. Use the BLOCKED line only for what those
> instructions reserve for the owner or, where they say nothing, for a decision, money, credentials, a production step.

The owner team's ID comes from the hub guide (AGENTS.md), so the constant stays a constant.

`consult_prompt` gets, after the verdict list:

> Your team's instructions (its `CLAUDE.md`, the owner's goal) may say which decisions your team takes and which are
> reserved for the owner. Decide everything they allow you to decide (`technical` or `product`), and answer `owner`
> only for what they reserve for the owner or, where they say nothing, for what a human must decide. When you decide
> something the owner should know about, put a short note in `note_for_owner`; the dispatcher sends it to the owner
> as a handover that needs only an acknowledgement. Otherwise leave it empty.

`VERDICT_SCHEMA` gets an optional string property `note_for_owner` (not in `required`), so old verdicts stay valid.

With no policy in the team's instructions the texts fall back to the existing rules ("where they say nothing"), so
behaviour stays as now.

### D10. The team-decision notice

After a valid `technical`/`product` verdict with a non-empty `note_for_owner`, the dispatcher runs
`HO_TEAM=<triage team> ho new --to <owner_team> --expects ack --auto-close --tag team-decision --title
"<triage team>: decided for <team> on <handover>" --body - --json`, then `ho sync`. No `--ref`: a referencing open
handover could hold the product team's own item ("Waiting for a handover's result"), and this notice must never
hold anything. Run log: `team_decision_sent` (team, handover, notice ID) or `team_decision_send_failed` (error,
plus a `!` console line). The resume of the asking session happens in either case.

**Assumption:** the notice is sent only from triage verdicts. A work session that decides under D9 sends its own
`ho new` (it is told how), so the engine does not parse anything for that path.

## Implementation notes (apply phase, unattended assumptions)

- **Session root behind a launcher.** A virtual environment's `python.exe` on Windows starts the real interpreter as
  its child, so the hook's parent may be that launcher, not Claude Code. The root is the hook's parent, walked up
  while the process name is a Python interpreter (`python*`, `py.exe`); the process table carries the names.
- **Reused IDs.** On Windows the table also carries creation times; a "child" created before its parent is a reused
  parent ID and not counted as a descendant.
- **Discard edge cases.** `git checkout .` (no `--`) is denied like `git checkout -- .`; `git restore` with another
  option (`-p`, `--ours`, …), a path that does not exist (e.g. a deleted file) and `git checkout <branch>` are left to
  the permission mode (no decision), never allowed.
- **Stop edge cases.** `kill %1` (a shell job) and `kill -l` get no decision; a negative ID (a process group), a
  variable ID (`$pid`), piped input and a failed process-table read are denied with the stop reason. PowerShell's
  `kill` alias with named parameters is read as `Stop-Process`.
- **Compound commands.** Split on `;`, `&&`, `||`, `|`, `&`, newlines; any broad discard or a stop by name / of a
  non-literal ID in a part is denied; nothing in a compound command is allowed.
- **Temp in shell commands.** The session temp dir and the repository (also in Git Bash form `/c/...`) are removed
  from the command text before the system temp paths are searched, so a repository or run directory under the
  system temp directory is never denied.
- **Markers.** Each guard decision writes a `guard` marker (decision, rule, tool, input ≤ 200 chars) for the run's
  record; it does not change the session outcome. A guard exception prints nothing (the permission mode decides).
- **Escalation question.** A text question (denial) is shown in the escalation body as a quote, a structured one as
  JSON as before. With an escalation keyword question in the same session, that question stays the escalation's
  question and the `## Denied` section is still listed.
- **Test placement.** The settings-file check of task 3.2 is in `test_hooks.py`; the environment check of task 2.1
  needed the fake `claude` to record `TEMP`, `TMP`, `TMPDIR`, `HARNESS_TEMP`, `HARNESS_SYSTEM_TEMP`, `HARNESS_REPO`.

## Risks / Trade-offs

- **Hook allow may not bypass auto mode** → task 1.1 checks it first; fallback in D1.
- **Heuristic command parsing** → allow only for a single simple command (D2); everything unrecognised is left to
  the permission mode, so a parser miss means "as before", never "more allowed".
- **Process-table call cost** (PowerShell start, ~1 s) → only for recognised stop commands.
- **Owner's uncommitted manual edits in a team repository** could be discarded by an allowed `git restore` → the
  same is already possible with `Write`; documented.
- **Temp deny is stricter than before** for a write the classifier would have allowed into the system temp dir →
  the reason names the allowed place, so the session continues; accepted.

## Split

Not split: both parts are small and share the prompt/escalation code. Nothing is left for a follow-up item.
