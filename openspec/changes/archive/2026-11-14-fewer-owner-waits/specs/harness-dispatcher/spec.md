## ADDED Requirements

### Requirement: Session temp directory
For every session it starts, new or resumed, the dispatcher SHALL create the directory `<run_dir>/tmp/<team>/` if missing, add it to the session's working directories, and set `TEMP`, `TMP` and `TMPDIR` in the session's environment to it. The dispatcher MUST NOT delete files in it. Team repositories are not changed.

#### Scenario: Temp directory of a session
- **WHEN** the dispatcher starts an apply session of `app`
- **THEN** `<run_dir>/tmp/app/` exists, the Claude Code command adds it as a working directory, and the session's `TEMP`, `TMP` and `TMPDIR` name it

#### Scenario: Resumed session
- **WHEN** the dispatcher resumes a session of `backend` with the owner's answer
- **THEN** the resumed session gets `<run_dir>/tmp/backend/` the same way

### Requirement: Discarding working-tree edits
The dispatcher's hooks SHALL allow, in a session's shell tool, a `git restore` (no `--source`) or `git checkout --` whose every path names an existing file inside the session's repository. A form with `.`, a directory, a wildcard, pathspec magic, a path outside the repository or `--source` SHALL be denied with a reason naming the allowed ways: name the files, or re-write each file. Any other command is not decided by this rule.

#### Scenario: Named file is restored
- **WHEN** a session in `app` runs `git restore -- src/cache.py` and `src/cache.py` is a file of the repository
- **THEN** the hook allows the command and no permission denial is recorded

#### Scenario: Whole tree is not restored
- **WHEN** a session runs `git checkout -- .`
- **THEN** the hook denies it and the reason tells the session to name the files (`git restore -- <file>`) or re-write each file

#### Scenario: Path outside the repository
- **WHEN** a session runs `git restore ../backend/src/api.py`
- **THEN** the hook denies it with the same reason

### Requirement: Stopping the session's own processes
The dispatcher's hooks SHALL allow, in a session's shell tool, stopping processes by ID (`Stop-Process -Id`, `taskkill /PID`, `kill <pid>`) when every ID is a process descended from the session's own Claude Code process. Stopping by name or image, or a process outside that tree, SHALL be denied with a reason naming the allowed ways: stop the processes the session started by ID, or run servers as background tasks and stop them with the task tool.

#### Scenario: Own test server is stopped
- **WHEN** a session started a test server as a child process with ID 4242 and runs `Stop-Process -Id 4242`
- **THEN** the hook allows the command

#### Scenario: Stop by name
- **WHEN** a session runs `Stop-Process -Name node`
- **THEN** the hook denies it and the reason tells the session to stop only the processes it started, by ID, or to stop a background task with the task tool

#### Scenario: Foreign process
- **WHEN** a session runs `taskkill /PID 1234 /F` and 1234 is not descended from the session's Claude Code process
- **THEN** the hook denies it with the same reason

### Requirement: Temporary files go to the session temp directory
The dispatcher's hooks SHALL deny a file write or edit tool call, and a shell command, that targets the system temporary directory (the session's original `TEMP` / `TMP`, or `/tmp`), with a reason naming the session temp directory as the place for temporary files. Paths in the session temp directory and in the repository are not decided by this rule.

#### Scenario: Script written to the system temp directory
- **WHEN** a session writes `check.ps1` to the system temporary directory
- **THEN** the hook denies it and the reason names `<run_dir>/tmp/<team>/` as the place for temporary files

#### Scenario: Script in the session temp directory
- **WHEN** a session writes `check.ps1` to `<run_dir>/tmp/<team>/`
- **THEN** the hook does not deny it

### Requirement: Nothing outward becomes allowed
The hooks' allow decisions SHALL cover only the narrow forms named in "Discarding working-tree edits" and "Stopping the session's own processes". A command that pushes, publishes, tags, deletes outside the session's repository and temp directory, or spends money MUST NOT be allowed by a hook; such commands, and every command the hook rules do not name, stay with the configured permission mode.

#### Scenario: Push stays with the permission mode
- **WHEN** a session runs `git push origin main`
- **THEN** the hooks make no decision and the permission mode decides as before

#### Scenario: Restore combined with another command
- **WHEN** a session runs `git restore -- src/cache.py; git push`
- **THEN** the hooks do not allow it, and the permission mode decides

### Requirement: Denial rule in the system prompt
Every session the dispatcher starts, new or resumed, SHALL carry in its system prompt, after the long-wait rule, the denial rule: when a command is denied, do the same another allowed way (temp files in the session temp directory; discard edits by naming the files or re-writing them; stop only its own processes by ID); if the phase cannot be completed without it, end with one line `BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <proposal>`.

#### Scenario: Rule names the temp directory
- **WHEN** the dispatcher starts a session of `app`
- **THEN** its system prompt carries the denial rule naming `<run_dir>/tmp/app/` and the `BLOCKED: owner — denied: …` line format

### Requirement: One clear question for a denial
A work session that ends with a permission denial and is escalated (it did not complete its phase, see "Permission denial in a completed phase") SHALL produce exactly one escalation handover for the item, in every work phase. Its reason SHALL keep `permission denied: <tool>`; its body SHALL list each denied tool with its shortened command or input; its question SHALL be the session's last `BLOCKED: owner — …` text when the session gave one, otherwise a question naming the denied commands.

#### Scenario: Denied command with the team's suggestion
- **WHEN** an apply session of `backend` has `Remove-Item C:\cache -Recurse` denied, does not mark its part `done`, and ends with `BLOCKED: owner — denied: Remove-Item C:\cache -Recurse; needed for: a clean benchmark; suggestion: allow it once or run the benchmark without a clean cache`
- **THEN** the owner receives one escalation handover whose body names the denied PowerShell command and whose question is that text

#### Scenario: Denial without a blocked line
- **WHEN** a propose session has one Bash denial, no change is created, and its final message has no `BLOCKED:` line
- **THEN** the owner receives one escalation handover whose question names the denied Bash command and asks how the team should go on

#### Scenario: Several denials in one session
- **WHEN** an apply session has three denials and ends without completing its phase
- **THEN** exactly one escalation handover is sent, listing all three

### Requirement: Team decision notice
When a `technical` or `product` triage verdict carries a non-empty `note_for_owner`, the dispatcher SHALL send the owner one handover from the triage team, expecting an acknowledgement, auto-closing, tagged `team-decision`, referencing no handover, naming the asking team, the item, the question, the decision and the note. It MUST NOT hold or escalate any item; the asking session is resumed as for the verdict. A failed send is logged and shown only.

#### Scenario: Failed notice
- **WHEN** sending the team-decision handover fails
- **THEN** the run log and the console show the failure, and the asking session is still resumed with the verdict

#### Scenario: Product decides and informs the owner
- **WHEN** triage answers `product` with "use the recommended cache option" and a `note_for_owner`
- **THEN** the asking session is resumed with that answer, and the owner's inbox shows a `team-decision` handover from `product` naming the question, the decision and the note, expecting only an acknowledgement

#### Scenario: No note, no notice
- **WHEN** triage answers `technical` with an empty `note_for_owner`
- **THEN** no handover is sent to the owner, as before

## MODIFIED Requirements

### Requirement: Worker blocked on the owner
The apply and act prompts SHALL tell the worker: when it waits for another team's handover, stop without committing or commenting only to record that it still waits; when a decision is needed that its team's instructions (its `CLAUDE.md`, the owner's goal) allow the team to take, take it, record it in the change, inform the owner with a non-blocking handover (expecting only an acknowledgement) and continue; when only the owner can unblock it — what those instructions reserve for the owner, or, where they say nothing, a decision, money, credentials, a production step — end its final message with one line `BLOCKED: owner — <what is needed>`. When a work session ends with such a line as the last `BLOCKED:` line of its result and did not complete its phase (apply or act: the worker's part is not marked `done`, `declined` or answered), its outcome SHALL be `waiting_for_owner`, and the item MUST be escalated to the owner at once with the text after the dash as the reason, without waiting for `no_progress_limit`. A session that completed its phase is handled as before, whatever its last line says. The console escalation line and the run log SHALL carry the reason.

#### Scenario: Paid step needs the owner
- **WHEN** an apply session of `backend` for HO-20261031-p3uj ends with `BLOCKED: owner — go-ahead for a paid benchmark (up to $0.30)` and `backend` has not answered the handover
- **THEN** its outcome is `waiting_for_owner`, the owner receives an escalation handover naming the paid benchmark, and no further session is started for HO-20261031-p3uj until the owner answers

#### Scenario: Blocked line after the phase was completed
- **WHEN** an apply session marks its part `done` and its final message also ends with a `BLOCKED: owner — …` line
- **THEN** it is handled as a completed phase and nothing is escalated

#### Scenario: No line, no change
- **WHEN** an apply session ends normally without completing its phase and without a `BLOCKED:` line
- **THEN** the outcome and progress rules are the same as before this requirement

#### Scenario: Waiting for another team
- **WHEN** an apply session sends its own handover to `backend` with `ho new` and stops that part
- **THEN** it is not escalated; the item is held as described in "Waiting for a handover's result"

#### Scenario: Prompt tells the team to decide what its policy allows
- **WHEN** the dispatcher builds an apply or act prompt
- **THEN** the prompt tells the worker to take the decisions its team's instructions allow, record them, inform the owner with a handover that expects only an acknowledgement, and use `BLOCKED: owner` only for what those instructions reserve for the owner or, where they say nothing, for a decision, money, credentials or a production step

### Requirement: Product triage of questions
When a session ends with outcome `question`, the dispatcher SHALL refer the question directly — without creating a hub handover — to the configured product team (by default `product`) in a consultation session in that team's repository. Product triage is the fallback for every question the rules do not settle: by default the questions of every configured team are triaged, including the product team's own questions from its work sessions (answered in a separate consultation session); the configuration MAY limit triage to a list of teams. A question raised inside a consultation session is never triaged again; it gets the default answer. The consultation receives the question, its options, the asking team, the handover ID and the change name, and MUST NOT modify files, run `ho` write commands or contact other teams. The consultation prompt SHALL tell the product team to decide everything its instructions (its `CLAUDE.md`, the owner's goal) allow it to decide, to answer `owner` only for what those instructions reserve for the owner or, where they say nothing, for what a human must decide, and to put what the owner should know about a decision it takes into `note_for_owner`. It SHALL return one structured verdict:
- `technical` — the question cannot affect product success, user count or other key product figures; the team chooses the best variant;
- `product` — it can affect them; the verdict carries the chosen answer and the reason;
- `owner` — a human must decide; the verdict carries the reason.
The verdict MAY carry `note_for_owner` (see "Team decision notice"). The dispatcher SHALL then resume the asking team's session: with the default answer for `technical`, or with the product agent's answer and reason for `product`, instructing the agent to record it in the change as a product decision. For `owner`, a missing or malformed verdict, or a failed consultation, the item MUST be escalated. More than the configured number of triages for one handover (default 3) MUST also be escalated. Every verdict SHALL be written to the run log. The consultation runs only after the asking session has ended and before it is resumed, so the *one session at a time* rule holds; it is not a work phase and does not count as progress.

#### Scenario: Technical question
- **WHEN** `app` asked "Use a Map or a plain object for the cache?" and the product agent answers `technical`
- **THEN** the `app` session is resumed with "choose the best variant, record the assumption, continue", and the log shows the verdict

#### Scenario: Product-relevant question decided by product
- **WHEN** `app` asked "Show the onboarding tour on first install or only on request?" and the product agent answers `product` with "on first install, it drives activation"
- **THEN** the `app` session is resumed with that answer and reason, to be recorded in the change as a product decision

#### Scenario: Product asks for the owner
- **WHEN** the product agent answers `owner` because the question changes pricing
- **THEN** the item is escalated to the owner with the product agent's reason, and the asking session is not resumed

#### Scenario: Consultation fails
- **WHEN** the consultation session ends with an error or a verdict that does not fit the expected structure
- **THEN** the item is escalated and the asking session is not resumed

#### Scenario: Consultation changes nothing
- **WHEN** a consultation session has ended
- **THEN** the product repository and the hub have no changes made by it

#### Scenario: Consultation prompt names the team's policy
- **WHEN** the dispatcher builds a consultation prompt
- **THEN** it tells the product team to decide what its instructions allow, to answer `owner` only for what they reserve for the owner (or, where they say nothing, what a human must decide), and to put what the owner should know into `note_for_owner`

#### Scenario: Verdict without the note
- **WHEN** a consultation returns a verdict without `note_for_owner`
- **THEN** the verdict is valid and handled as before
