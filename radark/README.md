# radark — the radark-factory dispatcher

A small deterministic Python dispatcher (OpenSpec change `add-python-harness`). It reads the handover hub,
wakes the right team agent with `claude -p`, one session at a time (only a short read-only limit check runs next
to a session), keeps the agent moving through agreed stops, gates archiving on the author's approval, and logs every decision.

Runtime: Python 3.12, standard library only. Tests: `pytest`. Tested with Claude Code **2.1.302** on Windows 11.

## Setup

1. `ho` and `claude` on `PATH` (or give full commands in the config). The owner's own Claude Code login is used;
   the dispatcher removes `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` from the agents' environment and never uses `--bare`.
2. `copy harness.toml.example harness.toml` (git-ignored) and adjust paths.
3. `python -m radark dry-run` — prints the hub, teams, Claude Code and `ho` versions, the candidates and the session it would start.

## Configuration (`harness.toml`)

| Key | Meaning |
|---|---|
| `hub` | hub directory (must contain `hub.json`) |
| `run_dir` | run-time directory, default `.harness` (relative to the config file) |
| `ho`, `claude` | command name on `PATH`, or a list such as `["python", "D:\\...\\ho.py"]` |
| `owner_team` | hub team of the human owner, default `owner`; escalation handovers go there. It must be a hub team (`ho teams`) and must not be in `[[teams]]`; `run` / `dry-run` refuse to start otherwise |
| `[[teams]]` `id`, `repo`, `kind` | in priority order; `kind = "technical"` (propose / apply / archive) or `"product"` (act on handovers) |
| `[launch]` `permission_mode`, `extra_args` | default `auto`; `bypassPermissions` and `--bare` are refused |
| `[answers]` `default`, `escalation_keywords` | the "choose the best variant" text; words that send a question to the owner (matched at a word start, case-insensitive, `ё` = `е`; the defaults include Russian stems such as `удал`, `пуш`, `депло`, `оплат`) |
| `[triage]` `team`, `teams`, `max_per_handover` | product team that answers questions; `teams` limits whose questions are triaged (default: **every** team, the product team included); escalate after N triages per handover |
| `[loop]` | `poll_seconds` 120, `session_idle_minutes` 20 (no stream event for that long ends the session), `session_max_minutes` 180 (maximum duration; the old `session_timeout_minutes` is accepted as this; both count awake time only; for a work session a checkpoint, see **Limit check**), `limit_check_minutes` 60 (positive: extension when the limit check finds the session progressing), `limit_checks` 3 (integer ≥ 0: limit checks per session, so a healthy work session runs up to 180 + 3 × 60 = 360 min; 0 turns them off), `wrap_up_minutes` 15 (≥ 0: grace period of the wrap-up at a work session's last time limit, see **Wrap-up**; 0 turns the wrap-up off and such a session is cut at its deadline), `wake_grace_minutes` 3 (positive: after the computer wakes, a session with no stream line for that long is ended as `interrupted` and resumed), `no_progress_limit` 2, `usage_pause_percent` 90 (integer 1–100: no new step while a usage window not yet reset is used at least this much; 100 turns the prediction off; `run --budget-5h` / `--budget-7d` replace it per window for one run), `usage_backoff_minutes` 30 (doubling up to `usage_backoff_max_minutes` 300; only when a usage-limit hit has no known reset time), `idle_ask` false, `keep_awake` `"on"` (`"off"`, `"on"` or a daily range `"HH:MM-HH:MM"`: when a run keeps the computer from sleeping on its own; `"off"` lets the computer sleep; not a moment, which applies to one run only; `--keep-awake` replaces it for one run, see **Keep awake**) |
| `[goal]` `max_sessions`, `max_hours` | limits of a goal run: 40 sessions (every session counts: work, triage consultation, goal check), 12 hours (usage-limit waits count, sleeps of the computer do not); both positive; `--max-sessions` / `--max-hours` override them |

A broken config (missing value, missing repository path, `ho` / `claude` not found) exits with code 2 and names the problem.

### Compatibility of `ho`

`run`, `once`, `dry-run` and `plan` first run the configured `ho` with `--version --json` (environment: `HO_HUB`
set, no `HO_TEAM`; 60 s limit), before any other hub command, lock, log event or session. The answer
`{"schema_version": 1, "version": "0.2.0", "contract": 1}` gives the package version and the **JSON contract**
version (radark-handover bumps it only for removed or renamed fields, changed types or meanings, or changed exit
codes). The engine supports contract **1**: the constant `SUPPORTED_HO_CONTRACTS` in `radark/hub.py` (a tuple, so
one engine release can accept two contracts during a migration). A compatible `ho` adds the start line
`ho: 0.2.0 (contract 1)` right after `Claude Code: ...` (`plan` prints no summary). `escalations`, `clear`, `keep`
and `note` do not use the hub and skip the check.

Otherwise the dispatcher prints one line on stderr and exits with code **2**:

| Case | Message (abridged) | What to do |
|---|---|---|
| `ho` not found | `Configuration error: '<cmd>' (ho) was not found. This radark-factory needs an ho with JSON contract 1: ...` (`ho incompatible: ho not found: cannot start ...` when the file exists but cannot be started) | install radark-handover, or fix `ho` in `harness.toml` |
| too old | `ho incompatible: ho '<cmd>' has no --version (exit 1): it is older than this radark-factory supports. Found: no version; needed: JSON contract 1. ...` | install a radark-handover release that has `ho --version` |
| no answer | `ho incompatible: ho '<cmd>' did not answer '--version --json' within 60 s. ...` | check the `ho` installation |
| other contract | `ho incompatible: ho '<cmd>' is version 0.9.0 with JSON contract 2; this radark-factory needs contract 1. Install a radark-handover release with contract 1, or a radark-factory release that supports contract 2.` | install matching releases |

radark-factory and radark-handover are upgraded together: a release of one that changes the contract needs the
matching release of the other.

## Commands

```
python -m radark [--config harness.toml] run            # loop until STOP / Ctrl+C
python -m radark run --goal goal.md [--max-sessions N] [--max-hours H] [--no-wait]   # goal run: work the goal to an end, report
python -m radark note "<text>"                          # append a timestamped note to the goal run's file (no lock)
python -m radark run --once   |  once                   # one work item (session + any triage), then exit
python -m radark run [--budget-5h PCT] [--budget-7d PCT] # this run only: end once a window is used PCT % (see Usage guard)
python -m radark run --until 07:00                      # this run only: start no new step from 07:00 on (see Pause / stop)
python -m radark run --keep-awake [WHEN]               # this run only: keep the computer from sleeping on its own (see Keep awake)
python -m radark run --dry-run | dry-run                # read the hub, print the plan and owner answers; no session, no writes
python -m radark plan [--steps N] [--goal FILE] [--max-sessions N]   # the next N steps (default 5) if every step succeeds
python -m radark escalations                            # escalated and stalled items with reasons
python -m radark clear <ID>                             # make an item selectable again (after you answered it)
python -m radark keep <ID> [--team <id>] [--off]        # next phases resume the previous session
```

**Plan:** `plan` predicts the order of the next steps; `dry-run` shows the first one in detail (prompt included).
It reads the same snapshot as `dry-run` (inboxes, `ho show`, state records, holds, owner answers, carried goal
guidance), picks every step with the real selection rule, and after each step assumes its successful outcome on an
in-memory copy: propose → apply, apply / act → the team's part finished as `expects` asks (and the author's review
once every recipient is finished, or a note that the handover waits for an author the dispatcher does not run),
review → closed, archive → archived. Each assumed outcome is the newest hub activity. Like `dry-run` it takes no
lock and writes nothing: no hub, state, `goal.json`, `runs.jsonl` or `console.log`. Pass the same `--goal` and
`--max-sessions` you will `run` with: with `--goal` an empty hub ends in a goal check, without it in the idle state;
`--max-sessions` (goal runs only; default `[goal] max_sessions`) marks the step after which the run would end. It stops
early, and says why, at a goal check, at the idle state, or when the first step is a resume with the owner's answer or
a goal check for guidance the product team has not received. Every output ends with what it cannot know: returns,
escalations and triage, permission denials, failing checks, new handovers a session sends, a goal check's verdict.

```
Plan (if every step succeeds):
  1. backend                 apply    HO-20261026-rbkb  Deploy ST-35 to production now, with the owner's new …
  2. product  review   HO-20261026-rbkb  Deploy ST-35 to production now, with the owner's new …
  --max-sessions 2 ends the run here
  3. backend                 archive  HO-20261026-rbkb  Deploy ST-35 to production now, with the owner's new …
  4. app          archive  HO-20261025-vozr  BL-003 …
  5. product  goal check
Stops: the next steps depend on the goal check's verdict.
Assumes: reviews accept the work; no question escalates or goes to triage; no permission is denied; checks pass; …
```

**Pause / stop:** create `<run_dir>/PAUSE` (the running session finishes, no new one starts until the file is
removed) or `<run_dir>/STOP` (exit cleanly between sessions). To stop at a time on the clock, start the run with
`--until WHEN` (`run`, `run --once`, `run --goal`, `dry-run`): `HH:MM` is the next such moment (today, or tomorrow
if it has passed or is the current minute), `YYYY-MM-DD HH:MM` (or `YYYY-MM-DDTHH:MM`) a full date and time; local
wall-clock time, so time the computer sleeps counts (unlike `--max-hours`, which counts awake time). From that moment
no new step starts and the run ends (exit 0; a goal run ends with `limit`); a session running at that moment finishes
first, which can be up to `session_max_minutes` later (a work session extended by its limit checks: longer). By
default the run keeps the computer awake until it really ends, including that session (see **Keep awake**). Waits without a session (idle poll, `PAUSE`, usage wait,
back-off) end at the moment. The start line says `Run ends at 07:00 tomorrow (2026-10-30), in 8 h 50 min`
(`run_until` in `runs.jsonl`; the end logs `run_until_reached`). The end time applies to that one run and is not
stored. An unreadable value or a full date and time in the past is refused (exit 2) before any session. To check:
`python -m radark run --until 07:00 --dry-run` prints `Would end: ...`. Ctrl+C during a session: first press finishes
the session and exits, second press ends the session (process tree, outcome `interrupted`, cause owner) and
exits; the next start resumes that session in its own context. A second dispatcher on the same
run directory is refused by `<run_dir>/lock` (a stale lock from a dead PID is replaced with a warning).

**Keep awake:** by default the dispatcher keeps the computer awake for the whole run and says so at the start
(`Keep awake: whole run (default; --keep-awake off lets the computer sleep)`); `--keep-awake off` (one run) or
`[loop] keep_awake = "off"` lets Windows put it to sleep as its power plan says (a session it interrupts is resumed
after the wake). Before change keep-awake-by-default the default was `off`. `--keep-awake WHEN` (`run`, `run --once`,
`run --goal`, `dry-run`) sets for one run when the computer is kept from going to sleep on its own: `off` (never), `on`
or the bare flag (the whole run), `HH:MM` / `YYYY-MM-DD HH:MM` (from the start until that moment, the same forms as
`--until`; after it the computer may sleep while the run goes on), or a daily range `HH:MM-HH:MM` such as
`08:00-23:00` (a range whose end is earlier than its start crosses midnight: `22:00-02:00`). `[loop] keep_awake` sets
the default (`off`, `on` or a range; without it, the whole run); the option replaces it. With an end time (`--until`), a moment at or after it
means the whole run: `--until 12:00 --keep-awake 12:00` (or `13:00`) keeps the computer awake until the run really
ends, including a session that finishes after 12:00, the same as the bare flag; a moment before the end time keeps its
meaning (the computer may sleep after it while the run goes on). A range is checked every 30 s, so keeping awake starts
and stops within 30 s of an edge; the dispatcher cannot wake a sleeping computer, so a range that starts during a sleep
takes effect after the next wake. Only idle sleep is blocked: Sleep in the Start menu, the power button, the lid action
and a low battery still put the computer to sleep. To keep working with the lid closed, set "When I close the lid" to
"Do nothing" in the power options. The display still turns off as the power plan says; on the owner's laptop (Modern Standby) the computer stayed awake with the display off when plugged in (not checked on battery).

**Screen off for the night:** `npm run screen-off` (`scripts/screen-off.ps1`) covers every monitor with a black
window and hides the cursor; a key press, a click or a mouse move brings the screen back. The power plan's display
timeout then turns the panel off. While keeping awake holds (the default), the computer does not sleep: Windows logs this display-off as
Kernel-Power 506 "entering Modern Standby, Reason: Idle Timeout", but the processes go on (owner's laptop,
2026-11-08: no gap between real and awake time, no sleep line). With keeping awake turned off (`--keep-awake off`, or outside a moment or range) the
computer may enter standby as its power plan says. Do not turn the monitor off with `SC_MONITORPOWER` (the older version of the script, or
similar tools): on Modern Standby Windows handles it like the power button and the computer enters standby within
a minute, whatever keeps it awake. `SetThreadExecutionState` with `ES_SYSTEM_REQUIRED` (used), with
`ES_DISPLAY_REQUIRED` added, and a power request (`PowerSetRequest`, system and execution required) were all tested
against it and all failed (change harness-survive-sleep, D1).

The setting ends with the run (end of the work, a limit, `STOP`,
Ctrl+C, a closed window: Windows drops the request with the process) and is not stored. The start line says
`Keep awake: whole run (default; --keep-awake off lets the computer sleep)` without the option and `[loop]
keep_awake` (also with `--until` alone), `Keep awake: whole run` for an explicit `on`, `Keep awake: until 23:00 today, in 9 h 00 min`, `Keep awake: daily 08:00-23:00 (now: on)`
or, for a moment covered by the end time, `Keep awake: whole run (until 12:00 given, the run ends at 12:00)` (an end
on a later day reads `12:00 tomorrow` or `12:00 on 2026-11-20`)
(`keep_awake_setting` in `runs.jsonl`, with `mode` `on` and the given moment in `until` for the last one; a goal run's `goal_start` records `keep_awake`); each change during the run
prints `23:00  Keep awake ended; the computer may sleep.` or `08:00  Keep awake started.` and logs `keep_awake`.
`python -m radark dry-run` without the option prints `Would keep awake: whole run (default; --keep-awake off lets
the computer sleep)`, with `--keep-awake off` no keep-awake line; `dry-run --keep-awake 08:00-23:00` prints `Would keep awake: daily 08:00-23:00 (now: off, from
08:00)` outside the range; `dry-run --until 12:00 --keep-awake 12:00` prints `Would keep awake: whole run (until
12:00 given, the run ends at 12:00)`. An unreadable value is refused (exit 2) before any session. On a system other than
Windows a run with keeping awake set by the option or the configuration prints `! keeping the computer awake is not
available on this system` and goes on; with the default it prints nothing about it and goes on as with `off`.

## Running in a visible console (with Claude Code watching)

When a Claude Code session starts the dispatcher for you, its console is hidden. To see the output yourself while
the session keeps watching and steering the run, start the dispatcher in a window of its own:

```
Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd D:\work\my-factory; $env:PYTHONIOENCODING = \"utf-8\"; python -m radark run --goal .harness\goal.md --max-sessions 3'
```

The window shows the console lines and, at the end, the goal report and "Press any key to exit". Claude Code does
not need the window: it follows the run through the run directory (`runs.jsonl` for events, `goal.json` for the
goal run's status, `sessions/<run-id>.jsonl` for a session's full stream) and can wait for the end with a monitor
on `goal.json` (`status` other than `running`). Everything the window shows is also appended to `<run_dir>/console.log` (UTF-8,
a `==== <local time>  PID <pid>  <arguments>` header per start; `run` and `once` only, not `dry-run`), so Claude
Code sees the same lines, the goal report and any traceback with a `tail -f` on that file. Both of you steer the run through files: `PAUSE`, `STOP` and
`python -m radark note "<text>"`; Ctrl+C in the window is yours.

`run` and `once` turn off QuickEdit of their console window at start: in a classic Windows console a click in the
window starts a selection (the title shows "Select"), and while it lasts every console write blocks — the dispatcher
stops between sessions until Esc. To copy text from the window, use its menu: Edit → Mark.

## Console

The console is for following a run; `runs.jsonl` stays the precise record (UTC times, all fields). Each step prints
a start line (local time, team, phase, then the handover ID and its title, shortened to keep the line within about
110 characters; a long head puts the title on a second line) and an end line (outcome, a time limit's reason, the
duration). Steps without a work item name their kind: `goal check`, `idle ask`, `triage consultation`, `limit check`; resumes add
`owner answer`, `triage answer`, `resume after time limit` or `resume after interruption`. An interrupted session's
end line names the cause: `→ interrupted, computer slept (2 min)`, `owner` or `dispatcher stopped`. Problems are one line each, marked `!`, printed when
they happen: a session ended with an error and why (time limit, exit code, no result, hooks not loaded, Ctrl+C), a
session without progress (count against `no_progress_limit`), a question sent to product triage and its verdict, a
permission denial (and, when the session still completed its phase, `phase completed despite the permission denial
(PowerShell); not escalated`), a failed `ho` command, a goal check or idle ask without a valid verdict, escalations, stalls,
usage waits (an escalation names its reason, e.g. `! ESCALATED HO-… (backend): blocked on the owner: go-ahead for a
paid benchmark`; a session without progress whose commits changed only the change's own files ends with `(commits
changed only the change's own files)`), a sleep of the computer (`01:17–11:14`: when it went to sleep and woke, with the date when not today) and
a session found interrupted at start. Times are local `HH:MM`, `DD.MM HH:MM` when not today. Example (from a scripted test run; times and
durations made realistic):

```
22:24  app · propose · HO-20261024-sx7z  "The agent is told a slow page is loading, not failed (BL-0…"
22:31  ! app HO-20261024-sx7z: question for product triage: "Use a Map or a plain object for the cac…"
22:31  app · propose → question (7 min)
22:31  product · triage consultation · HO-20261024-sx7z  "The agent is told a slow page is loadi…"
22:32  product · triage consultation → finished (48 s)
22:32  ! app HO-20261024-sx7z: question went to product triage, verdict technical
22:32  app · propose · triage answer · HO-20261024-sx7z  "The agent is told a slow page is loading,…"
23:08  app · propose · triage answer → finished (36 min)
23:08  app · propose · HO-20261024-k2m9  "Show the retry button on a failed upload"
23:33  app · propose → error, idle time limit (25 min)
23:33  ! app HO-20261024-k2m9: session ended with an error: idle time limit after 25 min
23:33  ! app HO-20261024-k2m9: no progress in this session (1 of 2 before the item stalls)
11:14  ! computer slept 01:17–11:14 (9 h 57 min) - not counted
11:17  product · review → interrupted, computer slept (5 min)
11:17  product · review · resume after interruption · HO-20261024-d6zr  "Show the retry button on a fa…"
```

`·`, `→`, `…` and `–` are written only to a UTF-8 console (`$env:PYTHONIOENCODING = "utf-8"`); elsewhere they
become `-`, `->`, `...` and `-`, and characters the console cannot show are replaced, never an error.

## Goal run

`run --goal <file>` works a scope you describe to an end, without polling an idle hub. The file is your own
prompt in plain text or Markdown: which backlog work, what counts as done, and any guidelines (for example
"do not change the pricing page"). A missing or empty file, or `--goal` with `--once`, is refused (exit 2) before
any session.

- Work items run exactly as in a normal run. When no candidate is left, the product team (the `[triage]` team, else
  the first `product` team) gets a **goal check** instead of the idle ask: compare the goal with the hub, the backlog
  and the results, hand over the next goal item (one item per handover) or report the goal met or blocked. Verdict
  (`--json-schema`): `{status: complete | continue | blocked, reason, done: [..], left: [..]}`; `done` names the
  evidence (closed handovers, archived changes). A missing or malformed verdict counts as `continue` without new work.
- The goal text is added to every product-team prompt (act, review, triage consultation, goal check) before the
  standing rule; technical prompts are unchanged (they get the goal through the product team's handovers).
- **Steering:** edit the goal file or run `python -m radark note "<text>"` from a second console (it appends
  `## Note <local time>` and your text to the file named in `<run_dir>/goal.json`). The file is re-read between
  sessions; after a change the next session is a goal check that shows what was added (or says the text was edited)
  and asks the product team to adjust work in flight or keep the guidance for later. An emptied or unreadable file
  keeps the last good text (`goal_unreadable` warning). Guidance the product team has not received when a run ends
  (a note between runs, or one added late in a run that hit its limit) carries over: the next run on the same goal
  file starts with that goal check, before any other work (`goal_guidance_carried`). A run on another goal file, or
  the first run on a file, takes the whole text as already seen.
- **End:** `complete` (exit 0), `blocked` (4), `stalled` (5: two goal checks in a row with `continue` and no new hub
  activity), `limit` (6: `max_sessions` or `max_hours` of awake time, checked between work items; a running session and a triage
  chain already under way finish), `stopped` (0: `STOP` file or Ctrl+C). A goal check hit by the usage limit has no
  verdict and runs again after the wait; an interrupted goal check runs again. The report (status, reason, the run's sessions
  one line each, done, left, escalated / stalled items with their session for `claude --resume`, permission denials not escalated
(item, team, phase, tool and command), handovers the
  product team sent during the run, sessions, duration in awake time and the time slept, e.g. `duration 1 h 52 min
  (limit 12 h), slept 9 h 57 min`) is printed and saved as `<run_dir>/goal-report-<YYYYMMDD-HHMMSS>.md`. A run without a goal check of its
  own (for example `--max-sessions 1`) takes done and left from the last goal check of an earlier run on the same
  goal file (`goal.json`) and says so with that check's time. A usage budget (`--budget-5h` / `--budget-7d`, see
  the usage guard in [How it decides](#how-it-decides)) also ends the run with `limit` (6), with a reason such as
  `usage budget reached: seven_day 81% (budget 80%)`; `goal_start` records the budget. An end time (`--until 07:00`,
  see Pause / stop under [Commands](#commands)) ends the run with `limit` (6) and the reason
  `end time 2026-10-30 07:00 reached`; with `--max-hours` as well, whichever comes first ends the run (`--until` counts
  sleep of the computer, `--max-hours` does not); `goal_start` records `until`. In a console the dispatcher then waits with
  "Press any key to exit" (also for a `.cmd` started by double-click); `--no-wait` or a non-console stdin exits at once.
- `run --dry-run --goal <file>` prints the goal-check prompt when no candidate is left. A goal run is not resumed
  after a restart: a new `run --goal` with the same file continues over the same hub state.

## Owner workflow (escalations)

Every escalation (a question with an escalation keyword, a triage verdict `owner`, a permission denial in a session
that did not complete its phase, a `BLOCKED: owner` line, a stalled
item, too many triages) sends the owner a hub handover **from the team whose session escalated**:
`ho new --to owner --expects response --auto-close --tag escalation --ref <item handover>`, with the reason, the
question, phase and change, the tail of the session's result, the session ID and the manual fallback. At most one
escalation handover per item is open at a time. The item's own handover is never touched.

```
$env:HO_TEAM = "owner"; ho sync; ho inbox                  # what waits for you (tag: escalation)
ho show <ID>                                               # question, session, what was done
ho respond <ID> -m "yes, push to the feature branch"       # the same agent session resumes with your answer
ho decline <ID> -m "not before the release"                # the session resumes with the refusal and continues without that part
ho sync
```

On its next loop iteration (before any new work) the dispatcher sees the answer, clears the item and resumes the
escalated session with your answer (if the session cannot be resumed, a fresh session of the same phase gets the
answer in its prompt). The handover closes itself once answered. Agents may also send `owner` direct requests
(publishing a release, spending, credentials); those are ordinary handovers you answer the same way.

**`BLOCKED: owner`.** The apply and act prompts tell the worker: if it only waits for another team's result, stop
without committing or commenting just to record that; if only the owner can unblock it (a decision, money,
credentials, a production step), end the final message with one line `BLOCKED: owner — <what is needed>` (em dash,
en dash or hyphen). A work session that ends with such a line and did not complete its phase (the worker's part is
not `done`, declined or answered) is `waiting_for_owner` and escalated at once with the reason `blocked on the owner:
<what is needed>` (run log: `blocked_on_owner`, then `escalation`), without waiting for `no_progress_limit`; the item
runs no session until you answer. A session that completed its phase is handled as before, whatever its last line
says.

With `idle_ask = true`, an idle verdict `none` that lists backlog items waiting for the owner sends one escalation
handover from the product team; the product team sees your answer the next time it is asked for work.

**A team that is not set up.** Before every new step the dispatcher looks at the open handovers its teams have
sent (`ho list --from <team> --status all`). One addressed to a hub team that is neither in `[[teams]]` nor the
owner, whose recipient's part is not finished (see *Waiting for a handover's result* below: `pending`,
`returned`, or `acknowledged` when the handover expects more than an acknowledgement), can only wait: nobody runs
that team. The dispatcher
escalates it once, right away: the sender's item that the handover references (if the dispatcher works on it and it
is not already escalated or stalled) is marked escalated and skipped, and the owner gets an escalation handover from
the sender titled `<sender>: <handover> waits for team <team>, which the dispatcher does not run`, naming the
handover, the waiting item, the configuration file and the `[[teams]]` entry to add (`id`, `repo`, `kind`). With no
such item a standalone escalation handover referencing the waiting handover is sent instead. Console:
`! ESCALATED <item> (<sender>): <handover> "<title>" from <sender> to <team> (pending) waits for team <team>, which
is not set up in the dispatcher (<config>)`. To answer: add the team to the configuration, restart the dispatcher
and `ho respond` (the item's session resumes with your answer; the handover is then work of the new team), or have
the work done another way and respond with what was done. A handover is escalated once; it is reported again only
after it stopped waiting (closed, recipient finished, team now configured) and waits again. `dry-run` lists every
such wait and whether it would be escalated. The escalation handover does not count as new hub activity for the idle ask.

**Waiting for a handover's result.** An item is held — not selected as work — while its team has an open handover
that references the item and has a recipient whose part is not finished. Finished is `ho`'s rule per `expects`:
`ack` acknowledged or declined, `done` done or declined, `response` answered or declined; `pending` and `returned`
never. This covers handovers to configured teams, to teams that are not set up and direct requests to the owner;
escalation handovers do not hold. A held item runs no session, so it does not count sessions without progress
and does not stall. It is selected again as soon as every such handover is finished or closed (the sender's review
of the result is selected as before). An item returned to its team by its own sender is selected for **one session
per return** while held, so the worker can act on the return comment; once a session of its team for it has started
after the latest return, it is held again until the result arrives or the sender returns it once more. An item whose
session was cut by a time limit or an interruption is selected while held for its resume. Console: `12:31  HO-… (app) waits for HO-…
(backend, pending); not selected until it is finished` once when the hold starts, `HO-… (app): HO-… finished;
selectable again` when it ends. `dry-run` prints `Held (waits for a handover's result): …` per item. To release
an item whose handover nobody will answer: close the waiting handover (`ho close <ID> --force -m "..."` as its
sender team, or have the recipient decline it).

Manual fallback (still works): `escalations` lists items with their session and escalation handover; answer with
`claude --resume <session-id>` in the team repository, then `clear <ID>` (an answer given later in the hub is then
ignored). If sending the handover failed (`escalation_send_failed`), only the manual path is available for that
escalation.

## How it decides

- **Selection:** `ho inbox --json` per team → `action_required` (work) and `to_review` (review), plus records in
  phase `done` whose handover `ho show` shows closed (archive). Newest hub activity first, ties by team order;
  escalated / stalled items are skipped, and so are work items held while their team waits for a handover's
  result (`ho list --from <team> --status all`, read once per loop iteration for every configured team; see
  [Owner workflow](#owner-workflow-escalations)). Phases: technical new → `propose` (asks for a final `CHANGE: <name>`
  line; fallback: the newest change citing the handover ID; a propose after which neither names a change, whatever
  its outcome, leaves the handover new, so the next session is `propose` again, counted by `no_progress_limit`),
  with a known change, or returned → `apply` (with the return comment), sender with all recipients finished → `review`, closed → `archive`, product team → `act`.
  Archive runs only after the author closes the handover: the propose prompt keeps archiving and spec sync out of the
  change's tasks, and every apply prompt (new or returned) says not to archive or sync specs, to end with `ho done`
  and to leave any archive task unchecked for the archive phase.
  Every apply prompt also asks the team to name, on a `Local TODO:` line of its `ho done` summary, each entry of its
  repository's own TODO or backlog it added or materially changed (id, title, one line why); the review prompt asks
  the product team to take those entries into its backlog itself and say what it decided when it closes or returns
  the handover (a missing product backlog entry is not a reason to return).
- **Session:** `claude -p <prompt> --session-id <uuid> --output-format stream-json --verbose --permission-mode auto
  --permission-prompts none --settings <run_dir>/session-settings.json --append-system-prompt <standing rule>`
  in the team repository. The settings file adds our hooks in exec form (`python.exe` + script path, no shell);
  team repositories are not edited and the owner's manual sessions are unaffected.
- **Hooks:** `SessionStart` → `hooks_loaded` marker (missing ⇒ loop stops). `Stop` → a plain-text question with an
  escalation keyword ⇒ escalation; any other question ⇒ referred to product triage; otherwise one "continue"
  nudge (never twice in a row). `PreToolUse:AskUserQuestion` does the same for tool questions (see results:
  the tool is not offered in `-p`, so this is a safeguard). `StopFailure` → `usage_limit` marker.
- **Outcome:** `interrupted` (see below) > `usage_limit` > `waiting_for_owner` (escalation or a permission denial) >
  `error` (exit ≠ 0, no result, time limit, no hooks) > `question` > `finished`. A work-item session whose only reason
  to wait for the owner is a permission denial is not escalated when it ended normally (exit 0, a result, hooks
  loaded, no time limit) and completed its phase during the session: propose, its change exists; apply or act, the
  worker marked `done` or `declined`; review, the handover was closed or returned to the worker; archive, the change
  directory is gone. It is handled as `finished` (its `session_end` keeps the raw `waiting_for_owner`, then
  `denial_not_escalated`). The worker's denials kept this way are named in the item's next review prompt, which asks
  the reviewer to check that nothing required was skipped because of them; they are dropped once that prompt is built. Progress since the item's first session: hub activity
  by the team on the handover or a new handover from it, new commits on any branch of the team repository, or more
  checked tasks in the change's `tasks.md` (uncommitted edits do not count). In apply and act, commits count only if
  at least one of them changes a file outside the item's own change directory (`openspec/changes/<change>/`): a
  commit that only adds a "still waiting" note to the change's `tasks.md` is not progress, more checked tasks still
  are; the `no_progress` event then has `ignored: "change_notes"` and the console line ends with `(commits changed
  only the change's own files)`. Without any of these the session counts as no progress; after 2 the item is
  stalled.
- **Time limits:** a session is ended (whole process tree) when its stream carries nothing but `tool_progress`
  heartbeats for `session_idle_minutes` (`idle_timeout`; so one tool call longer than that is ended) or after
  `session_max_minutes` (`max_time`); both count awake time only (`QueryUnbiasedInterruptTime` on Windows), so a
  night's sleep ends no session. For a work session the maximum duration is a checkpoint (see **Limit check**),
  and at its last deadline the session is asked to wrap up instead of being cut (see **Wrap-up**). The outcome of a
  cut session is `error`. If it made progress, the
  item's next session resumes it once with a "stopped by a time limit, check `git status` and continue" message
  (fresh phase session if the resume fails); without progress the next session starts fresh.
  So that a long command or background wait is not cut silently, every session (new and resumed) carries a
  **long-wait rule** in its system prompt, next to the standing rule: never wait silently longer than a check
  interval, check the progress of a long command or background task at least once per interval (latest output, a
  progress counter, whether the process is alive), and treat two checks in a row without progress as hung (stop it,
  record what was seen, continue another way or report it). The interval is half of `session_idle_minutes`, rounded
  down to whole minutes, at least 1 (10 with the default 20); the rule names both numbers. A background wait still
  does not count as activity.
- **Limit check:** a work session (propose, apply, review, archive, act) at `session_max_minutes` is not cut at once.
  While it keeps running (the inactivity limit, a sleep and Ctrl+C still apply), the product team (the triage team,
  else the first product team) gets a read-only consultation (`Read`, `Grep`, `Glob`; phase `limit_check`, a
  second `claude -p` next to the session) with a digest of the session: handover, phase, duration, time since its
  last event other than a heartbeat, the tool running now, its last 8 status texts and 12 tool calls or failed tool
  results with their age, its progress so far and the path of its stream. It answers `{verdict: progressing | hung,
  reason}`. `progressing` moves the deadline by `limit_check_minutes`; after `limit_checks` extensions the session
  is not checked again and is asked to wrap up at its deadline (see **Wrap-up**). `hung`, a malformed verdict or a
  failed check (error, its own limits of `limit_check_minutes` and `session_idle_minutes`) cut it by `max_time` as
  before, without a wrap-up; after `hung` the resume message
  carries the product team's reason. A session that ends during its check ends the check, whose verdict is ignored.
  Not checked: triage consultations, limit checks, goal checks, idle asks, and every session without a product team
  or with `limit_checks = 0`. A check counts as a session of a goal run, never as progress. Console:

  ```
  15:37  ! app HO-20261028-xaai: time limit after 3 h 00 min, asking product whether it is hung
  15:37  product · limit check · HO-20261028-xaai  "The agent leaves the task and starts blind…"
  15:39  product · limit check → progressing, +60 min (2 min)
      It runs its final full e2e suite; new results every few minutes.
  ```
- **Wrap-up:** a work session for a handover that reaches its deadline with no extension left (all `limit_checks`
  used, `limit_checks = 0`, or no product team configured) is not cut. The dispatcher ends its process tree and at
  once resumes the same session (`claude -p <wrap-up prompt> --resume <session>`) in the same step, limited to
  `wrap_up_minutes` (default 15) and without a limit check or a second wrap-up. The prompt gives the grace period,
  says the running step was cut off (check `git status`, finish the partial step only if it is quick, otherwise undo
  it), asks to start no new work, commit what works, report the way the phase reports and name what is left on a
  `Left:` line; for apply: check off finished tasks, write the open ones under a `Left for a follow-up` note in
  `tasks.md`, and `ho done` with a summary starting `Wrapped up at the time limit.` (never archive). Limit of the
  mechanism: `claude -p` has no channel into a running session, so the step running at the stop is lost (as with a
  cut). The stopped first part is `interrupted` (`asked to wrap up`, not an error); the step's outcome is the
  wrap-up session's, and progress counts from the first part's start. A wrap-up session still running after the
  grace period is cut by `max_time` (`error`; with progress, resumed by the item's next session as after any time
  limit). The inactivity limit, a sleep and Ctrl+C apply to it as to any session. No wrap-up for a session judged
  `hung` or whose check failed, for triage consultations, limit checks, goal checks and idle asks, or with
  `wrap_up_minutes = 0`. Console:

  ```
  21:37  ! app HO-20261028-xaai: time limit after 6 h 00 min, 3 extensions used; asking the session to wrap up within 15 min
  21:37  app · apply → interrupted, asked to wrap up (6 h 00 min)
  21:37  app · apply · wrap-up · HO-20261028-xaai  "The agent leaves the task and starts blind…"
  21:45  app · apply · wrap-up → finished (8 min)
  ```

  The run log has `wrap_up_start` and `wrap_up`; the item's state keeps `time_limits`, one entry per wrap-up and per
  work session cut by `max_time` or `idle_timeout`. When the product team reviews that handover, its review prompt
  gets a paragraph that lists them (e.g. `wrapped up after 6 h with 3 extensions (finished)`), says the task may be
  too big for one session, and asks it to check the result's `Left:` list and, if work is left, to return the
  handover for it or record a follow-up and say which.
- **Sleep of the computer:** a gap of a minute or more between real time and awake time is a sleep. It is printed
  once (`! computer slept 01:17–11:14 (9 h 57 min) - not counted`) and logged as `suspend`. Waits for a moment in
  real time (a usage window's reset, a back-off) keep real time, so a window that reset during the night lets the
  next step start at once. A session that was running gets `wake_grace_minutes` of awake time after the wake: a
  stream line in that time and it goes on as if nothing happened; otherwise it is ended as `interrupted` (cause
  sleep).
- **Interrupted sessions:** `interrupted` (cause sleep, owner — the second Ctrl+C — or dispatcher stopped) is neither
  an error nor no progress: the counter stays, and the item's next session resumes the session in its own context
  whether or not it made progress, with a message naming the cause and asking to check the state, `git status` and
  continue the phase (a fresh phase session if the resume fails). An interrupted triage consultation resumes the
  asking session, which asks again; an interrupted goal check or idle ask runs again.
- **Window closed, reboot, crash:** while a session runs, `state.json` holds `meta.running` (session, run_id, team,
  handover, phase, step, pid, started); it is removed once the session's end is processed. The next `run` or `once`
  (after taking the lock) that finds it ends a leftover process of that session (only if the PID's process was
  created no later than the record, so a reused PID is left alone), prints `! <team> <handover>: session <id>
  (<phase>) was interrupted at HH:MM - dispatcher stopped; it will be resumed`, logs `interrupted` and resumes the
  session as the item's next session. A goal check, idle ask, triage consultation or owner-answer resume is not
  resumed: the record is dropped and the step runs again when due. A goal run's own counters start afresh.
- **Product triage** (fallback for every question the rules do not settle): a read-only consultation in the
  product repository (`--tools Read,Grep,Glob`, `--json-schema` verdict `technical | product | owner`), then the
  asking session is resumed with the default answer or the product decision. `owner`, a failed or malformed
  consultation, or more than `max_per_handover` triages ⇒ escalation.
- **Escalation handovers** (tag `escalation`, or known from the state) are never work or review items for any team.
- **Usage guard:** every session stream carries `rate_limit_event` lines with the plan's usage per window
  (`five_hour`, `seven_day`: used share and reset time). The latest reading per window is kept in `state.json`
  (`meta.usage`). Before every new step (owner-answer resume, work item, idle ask) the loop checks it: a window whose
  reset is still ahead and that is used at `usage_pause_percent` or more (or reports status `rejected`) holds all new
  steps until its reset + 60 s (the latest reset if several hold). A running session is never stopped; a triage
  chain already under way (consultation + resume) finishes. After a `usage_limit` hit the wait ends at the exhausted
  window's reported reset (the window not `allowed`, else the most used one) + 60 s; only without a future reset
  time does the doubling back-off apply. Console (marked like other problems, see [Console](#console)):
  `14:48  ! usage: five_hour 90% - no new step after this session` (once per session and window),
  `14:50  ! Usage: five_hour 93% used, resets 15:30 (local), waiting 40 min.` or `14:38  ! Usage limit hit:
  five_hour resets 15:30 (local), waiting 52 min.` (local time, with the date when not today), an hourly
  `! still waiting ...` reminder during long waits, and `15:31  Usage window five_hour has reset; resuming.`
  `dry-run` and a held `once` print each
  window's reading and the guard's verdict. Usage from the owner's own manual sessions shows up only in the next
  dispatcher session's stream.
- **Usage budget of a run:** `run --budget-5h PCT` / `--budget-7d PCT` (integers 1–100, alone or together; also on
  `run --once`, `run --goal`, `dry-run`) spend a window only up to PCT % in **this run**; nothing is stored, the next
  run without the options uses `usage_pause_percent` again. For a budgeted window the budget replaces
  `usage_pause_percent`, lower or higher: that window never holds, and once its reading (not reset) is at PCT % or
  more, or reports `rejected`, the run ends before the next step instead of waiting for the reset — a plain run with
  exit 0 and `Usage budget reached: seven_day 81% (budget 80%); ending the run.`, a goal run with `limit`. A run whose
  budget is already reached at start ends before any session. Windows without a budget keep the hold above. The
  check is between sessions, so one long session can overshoot the budget; its crossing is announced as
  `! usage: seven_day 80% - run budget reached - the run ends after this session (budget 80%)`. The start prints
  `Usage budget for this run: seven_day up to 80% (now 77%)` (`usage_budget` in `runs.jsonl`) and, for a budget
  above `usage_pause_percent`, `! warning: seven_day budget 95% is above the global usage_pause_percent 90%; this
  run may use the window past it` (`usage_budget_warning`); the end is logged as `usage_budget_reached`. The "now"
  share is the last reading from a harness session, so the owner's own use since then is not in it until the first
  session reports. To check without running: `python -m radark run --budget-7d 80 --dry-run` prints
  `budget: below (seven_day 77% < 80%)` at a 77 % reading; with `--budget-7d 75` it prints
  `budget: seven_day 77% >= 75% - the run would end without starting a step`.
- **Idle ask:** the product session returns a `--json-schema` verdict `{verdict: handed_over | none, reason,
  waiting_for_owner: [{item, why}]}`; asked at most once per hub state.

## Run-time files (`run_dir`)

`state.json` (per handover: team, change, phase, sessions (with the progress snapshot `base`: branch heads, change,
checked tasks), no_progress, triage_count, flags, reason, `waiting_for` (while held: the handovers the item waits
for, each with handover, team, state), `resume_after_timeout` (session, team, phase, reason
`idle_timeout | max_time | sleep | owner | dispatcher_stopped`, duration_s, limit_reason after a `hung` limit check), `time_limits` (sessions wrapped up or cut by a time limit:
session, phase, kind `wrap_up | cut`, reason, extensions, elapsed_s, outcome; named in the item's review prompt),
escalation link: escalation handover, team, session, phase, reason, question, sent, answered),
`meta` (`usage` per window: utilization 0–1, resets_at Unix s, status, seen; `usage_wait` of the current wait:
until, window, utilization, cause; `backoff_until`, `backoff_minutes`; `running`: the session now running; `unconfigured`: per handover waiting for a
team that is not set up and already escalated: team, sender, item, escalation, at), `runs.jsonl` (the run log), `sessions/<run-id>.jsonl` (full stream per session), `markers/<run-id>.jsonl`
(hook markers), `session-settings.json`, `hook-config.json`, `lock`, `PAUSE`, `STOP`, `console.log` (copy of the console of every `run` / `once`), `goal.json` (the current or
last goal run, for observability and `note`: path, hash, started, status, sessions and limits, slept_s, empty_continues,
guidance_pending, given_text — the goal text the product team last received —, last_verdict, last_verdict_at, result), `goal-report-<YYYYMMDD-HHMMSS>.md`.

Run-log events (one JSON line each, with `time`): `dispatcher_start`, `session_start` (team, repo, handover,
phase, prompt, resume), `session_end` (outcome, exit_code, session, duration_s, auto_answers, denials,
escalations, timed_out, timeout_reason `idle_timeout | max_time`, interrupt_cause `sleep | owner | wrap_up`, progress_sources `hub | commits | tasks`, stream,
result tail), `resume_after_timeout` (session, reason, duration_s), `wrap_up_start` (team, handover, phase,
session, elapsed_s, extensions_used, grace_min), `wrap_up` (the same and wrap_up_session, outcome, timeout_reason,
duration_s), `suspend` (start, end in Unix s, seconds, during: team,
handover, phase of the running session or null), `interrupted` (team, handover, phase, session, cause
`dispatcher_stopped`, resumed), `stale_index_lock` (path), `auto_answer`, `question`, `nudge`, `escalation`, `denial`,
`denial_not_escalated` (team, handover, phase, session, denials: tool, input shortened to 200 characters, phase,
session, at), `triage` (verdict, consult_session), `limit_check_start` (team, check_team, handover, session, elapsed_s,
checks_used), `limit_check` (team, check_team, handover, session, check_session, outcome, verdict
`progressing | hung` or null, reason, extension_min, duration_s, ignored, stream), `propose_without_change` (team, handover, outcome, session), `no_progress`, `stalled`, `escalation_sent` (escalation handover ID),
`escalation_send_failed` (error), `owner_answer` (action `respond | decline`, answer, session), `unconfigured_team`
(handover, sender, team, state `pending | acknowledged | returned`, item or null, escalation handover ID or null),
`waiting_for_handover` (handover, team, waits: handover, team, state; when a hold starts or its set changes),
`wait_ended` (handover, team, handovers), `usage_limit`
(window, resets_at — or backoff_minutes for the fallback), `usage_threshold` (team, handover, window, utilization,
resets_at), `usage_wait` (window, utilization, resets_at, until, minutes, cause `threshold | limit_hit`; once per
wait), `usage_resume` (window, cause), `keep_awake_setting` (mode `on | until | range`, text, until, start, end), `keep_awake` (on, at), `idle_ask`, `idle_verdict`, `idle_verdict_invalid`, `goal_start` (path, goal, hash,
max_sessions, max_hours), `goal_guidance_carried` (path, recovered `stored | hash | unknown`, added_chars),
`goal_check` (team, guidance_changed), `goal_verdict` (status, reason, done, left),
`goal_verdict_invalid`, `goal_updated` (path, hash, diff_chars), `goal_unreadable` (path), `goal_result` (status
`complete | blocked | stalled | stopped | limit`, reason, done, left, escalated, unescalated_denials, handovers, sessions, duration_s in awake time, slept_s),
`pause`, `stop`, `clear`, `hooks_not_loaded`.

## Hub contract used (read from `ho.py`, task 1.1)

Start check: `ho --version --json` (see **Compatibility of `ho`**).

Read commands: `ho inbox --json`, `ho show <ID> --json`, `ho list --from <team> --status all --json`,
`ho teams --json` (owner team check), with `HO_HUB` and `HO_TEAM` in the environment.

Write commands (escalation handovers only; team handovers are never changed):
`HO_TEAM=<escalated team> ho new --to <owner_team> --expects response --auto-close --tag escalation --ref <item>
--title ... --body - --json` (UTF-8 body on stdin), `ho close <escalation ID> --force -m "declined by owner"` (only
if a declined escalation handover is still open), and `ho sync` after each write. `respond` and `decline` both
auto-close the escalation handover (checked with ho on 2026-10-19).

- `inbox`: `team`, `action_required[]`, `to_review[]`, `updates[]`, `warnings[]`; items: `id`, `title`, `from`,
  `to`, `expects` (`ack | done | response`), `status` (`open | resolved | closed`), `recipients` {team: state},
  `my_state` (`pending | acknowledged | done | answered | declined | returned`), `priority`, `due`, `tags`,
  `refs`, `auto_close`, `created`, `last_activity`, `archived`, `path`.
- `show`: the same summary plus `body`, `events[]` (`at` UTC `YYYY-MM-DDTHH:MM:SS.mmmZ`, `team`, `action`
  — `ack | done | respond | decline | return | close | comment | seen` —, optional `target` for `return`,
  `body`, `file`), `invalid_events`, `allowed_actions` (when a team is given). Closed handovers move to
  `archive/` but `show` still finds them.
- `list`: `items[]` (summaries). Errors: JSON `{"error": {"code", "message"}}` with exit codes 1 (bad input),
  2 (not found), 3 (action not allowed now), 4 (hub integrity) — mapped to `HoUsageError`, `HoNotFound`,
  `HoLifecycleError`, `HoIntegrityError`.
- Time limit: each `ho` call gets 120 s of **awake time** (a sleep of the computer during the call adds nothing).
  A call with no answer by then is killed with its process tree and fails as `HoTimeout` (a `HoError`): the
  console shows e.g. `! ho show <ID> failed: no answer within 120 s` and the run goes on. A read (`inbox`, `show`,
  `list`) that was killed or left hanging by a sleep (it ended without JSON, or timed out, and a sleep fell inside
  the call) is run once more; write commands (`new`, `close`, `sync`) are never re-run.
- `ho init <path> --teams id=Name,...` (names must not contain commas). Recency uses the newest non-`seen`
  event, the same rule as `last_activity`.

## Tests and sandbox

```
python -m pytest radark/tests -q                                   # fake ho / claude; the fake claude runs the real hooks
python radark/sandbox/make_sandbox.py <scratch-dir> [--force]      # throw-away hub + app / product repos
python -m radark --config <scratch-dir>/harness.toml once
```

## Verification results (2026-10-17, Claude Code 2.1.302, Python 3.12.10, Windows 11)

| Check | Result |
|---|---|
| Hooks fire (exec form via `--settings`) | yes — `hooks_loaded` in every session, with Git Bash installed |
| `AskUserQuestion` in `-p` | **not offered**, with and without `--permission-prompts none` (absent from the `init` tool list; `ToolSearch` finds nothing). Design D2 "removed" case: questions arrive only as plain text at `Stop`; the `PreToolUse` hook stays as a safeguard |
| `Stop` nudge | fires once, the session then ends (`stop_hook_active`); `last_assistant_message` is delivered |
| Usage limit | a real limit hit gave `StopFailure` → `usage_limit` marker, exit 1, outcome `usage_limit` |
| Usage reports in the stream | `rate_limit_event` lines (45 in 4 saved sessions), only `status: "allowed"` seen so far: `{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","resetsAt":1792281000,"rateLimitType":"five_hour","overageStatus":"rejected","isUsingOverage":false,"unifiedWindows":{"five_hour":{"utilization":0.57,"resetsAt":1792281000},"seven_day":{"utilization":0.34,"resetsAt":1792652400}}}}`; utilization grows by about 0.01 per event. Without `unifiedWindows` the top-level `rateLimitType` / `utilization` / `resetsAt` is read; malformed parts are ignored |
| End to end (`once` ×4) | propose (64 s, change name captured) → apply + `ho done` (36 s) → author review + `close` (45 s) → archive (49 s, change moved to `archive/`) → "Nothing to do" |
| Triage, technical question | verdict `technical` (consultation 12 s), session resumed, choice recorded in the change |
| Triage, product question | verdict `product` ("name the product"), recorded in the change as a product decision; the resumed session knew the question |
| Consultations change nothing | product repository HEAD and status unchanged; no hub commit or event during consultations |
| Escalation | a "push to the remote?" question → `waiting_for_owner`, listed by `escalations`, skipped by selection, `clear` restores it |
| Dry run on the real hub | two `review` items for `backend` listed, nothing started; hub and all four team repositories unchanged (HEAD + status) |

Deviations and notes:

- **Agents follow the standing rule over handover text.** Asked by a handover to "end your turn with this question",
  the agent decided itself instead. Triage and escalation were therefore exercised with a sandbox-only driver that
  swaps the standing rule for one that lets such test questions through; the dispatcher code was unchanged.
- **Untrusted workspaces:** in `-p`, `permissions.allow` from a repository's `.claude/settings.json` is ignored until
  the folder has been trusted once interactively (stderr says so). The sandbox ran on `auto` mode alone; the real team
  repositories are already trusted.
- Every session ends with one nudge turn (the `Stop` hook cannot tell a finished phase from an early stop); the cost
  was a few seconds per session.
- Additions beyond the design text: a plain-text question with an escalation keyword at `Stop` is escalated for any
  team (otherwise it would be nudged); consultations also get `--tools Read,Grep,Glob` (not only `--allowedTools`)
  and no nudge; progress is counted from the item's first session so a triage resume does not count as "no progress";
  product triage covers every team by default (owner decision, 2026-10-17).
