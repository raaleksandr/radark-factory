# Setup from zero

This guide takes you from nothing to a first `radark dry-run` and a first real run: a handover hub, two team
repositories (a product team that sends tasks and a technical team that does them), a configuration, and the checks
that tell you it is healthy. It gives the minimal steps and links to the reference for the details:
[radark/README.md](../radark/README.md) (the engine) and the
[radark-handover README](https://github.com/raaleksandr/radark-handover) (the hub and the `ho` CLI).

The examples use the folder `~/work/my-factory` (POSIX shells) or `D:\work\my-factory` (Windows), the team ids
`product`, `app` and `owner`, and made-up handover IDs. Commands are shown once; where Windows and POSIX differ,
both forms are given.

Want to see the whole loop first without setting anything up? Jump to [The sandbox](#7-the-sandbox), then come
back.

## 1. Prerequisites

- **Python 3.11 or newer** (`python --version`).
- **Git** (`git --version`). Every team repository is a Git repository; the dispatcher measures progress by its
  commits.
- **Claude Code**, logged in with your own account. The engine is tested with Claude Code 2.1.302 (see
  [README.md](../README.md) "Status"); newer versions normally work. Check: `claude --version` and
  `claude auth status` (exit code 0 and your account when logged in; otherwise run `claude` once interactively and
  log in). The dispatcher has no model and no credential of its own: agents run on this login, and it never passes
  `ANTHROPIC_API_KEY`.
- **Node.js and the OpenSpec CLI**, only for teams on the `openspec` workflow profile (the default):
  `npm install -g @fission-ai/openspec`, check with `openspec --version`. Teams on the `plain` profile need neither
  (see [Workflow profile](../README.md#workflow-profile)).

Windows vs POSIX — only these differences matter:

| | Windows (PowerShell) | POSIX shells |
|---|---|---|
| Paths in `radark.toml` | single-quoted TOML literal strings: `hub = 'D:\work\my-factory\hub'` (in `"..."` every `\` must be doubled) | `hub = "/home/me/work/my-factory/hub"` |
| Copy a file | `copy a b` | `cp a b` |
| Set a variable for this shell | `$env:HO_TEAM = "owner"` | `export HO_TEAM=owner` |
| Run directory | `.radark\` | `.radark/` |

## 2. Install

```
uv tool install git+https://github.com/<owner>/radark-factory     # or, from a clone: pip install .
```

This installs `radark` and, as its dependency, radark-handover with the `ho` CLI. Do not install another `ho`
separately: the two are released together (see "Compatibility of `ho`" in
[radark/README.md](../radark/README.md#compatibility-of-ho)). Check:

```
pip show radark-factory          # or: uv tool list — the installed version
radark --help                    # the commands: run, once, dry-run, plan, status, ...
ho --version                     # e.g. ho 0.2.0 (contract 1)
ho --version --json              # {"schema_version": 1, "version": "0.2.0", "contract": 1, ...}
claude --version
```

`radark` has no `--version` flag; `radark dry-run` (section 6) prints the Claude Code and `ho` versions in its start
summary. The number after `contract` is the `ho` JSON contract; this release of the engine needs contract 1. If
`ho` is missing or has another contract, every `run` / `dry-run` stops with exit code 2 and one line such as
`Configuration error: 'ho' (ho) was not found on PATH. This radark-factory needs an ho with JSON contract 1: ...`
or `ho incompatible: ho 'ho' is version ... with JSON contract 2; this radark-factory needs contract 1. ...`; the
full list of these messages and what to do is in "Compatibility of `ho`".

## 3. Hub

The hub is a directory of Markdown handovers, edited only through `ho`. Every team, and you as the owner, is a team
of the hub. For a hub **shared through git** (teams on several computers), follow "Set up a hub shared through git"
in the [radark-handover README](https://github.com/raaleksandr/radark-handover#set-up-a-hub-shared-through-git). For one computer, a local hub is
enough:

```
mkdir -p ~/work/my-factory                       # Windows: mkdir D:\work\my-factory
cd ~/work/my-factory
ho init hub --teams "product=Product,app=App,owner=Owner"
```

`ho init <path> --teams id=Name,...` creates `hub/hub.json`, `hub/AGENTS.md` (the guide every agent reads) and the
handover folders. Team names must not contain commas. Include the `owner` team: escalations go there, and the
dispatcher refuses to start without it.

The hub may stay a plain folder, or become a local Git repository without a remote (recommended: it keeps a history):

```
cd hub
git init -b main
git add -A
git commit -m "Hub created"
cd ..
```

Without a remote, `ho sync` prints that there is no upstream to pull from and commits locally; that is fine.

`ho` finds the hub and the acting team through two environment variables:

- `HO_HUB` — the hub directory (here `~/work/my-factory/hub`);
- `HO_TEAM` — the team you act as (`product`, `app`, or `owner` for you).

Agents get both from their repository's `.claude/settings.json` (next section). For your own commands as the owner:

```
export HO_HUB=~/work/my-factory/hub HO_TEAM=owner                  # POSIX
$env:HO_HUB = "D:\work\my-factory\hub"; $env:HO_TEAM = "owner"     # PowerShell
ho teams                                                           # product, app, owner
```

## 4. Team repositories

Each team is one Git repository with its own `CLAUDE.md` (what the team is and how it works) and
`.claude/settings.json` (where its hub is). Create a technical team `app` and a product team `product`:

```
mkdir -p repos/app repos/product
cd repos/app
git init -b main
openspec init --tools claude        # only for the openspec profile (the default)
cd ../..
cd repos/product
git init -b main
cd ../..
```

### `CLAUDE.md` template

Copy this into `CLAUDE.md` at the root of each team repository and replace the `<...>` placeholders (the role, the
owner-only actions and the decisions the team takes are your pipeline's own policy; see
[Owner-only actions / decisions the team takes](../README.md#owner-only-actions--decisions-the-team-takes)):

```markdown
# CLAUDE.md — <team id>

<One or two sentences: what this repository is.>

## Role
- You are the <technical | product> team `<team id>`. Other teams reach you only through the handover hub, with
  the `ho` CLI; `HO_HUB` and `HO_TEAM` are set in `.claude/settings.json`.
- <Technical team: you do the tasks other teams send you.>
  <Product team: you keep the backlog in `<backlog file>`, send tasks to the technical teams with
  `ho new --to <team id> ...`, and review their results: `ho close <ID>` to accept, `ho return <ID>` to ask for
  more.>

## Working through the hub
- Before the first handover in a session, read `$HO_HUB/AGENTS.md`.
- Run `ho sync` first and last.
- Unclear question: `ho comment <ID> -m "..."` instead of guessing.

## Work process
- <openspec profile: Every task gets an OpenSpec change (propose, apply, archive) that cites the handover ID;
  report it with `ho done <ID> -m "<summary>"`; archive only after the author closes the handover.>
- <plain profile: No OpenSpec change. For a handover: read and acknowledge it, do the task, run the tests that
  cover it, commit locally, and report with `ho done <ID> -m "<summary>"`.>

## Tests
- <The test command, e.g. `python -m pytest -q`; all must pass before `ho done`.>

## Owner-only actions
- Publishing a release, pushing to the remote, tagging.
- Spending money; credentials and accounts; legal questions.

## Decisions the team takes
- A choice between technical options the team already recommended.
- The test strategy, and the order of the team's own work.
- Inform the owner of such a decision with a non-blocking handover (`--expects ack --auto-close`).
```

Keep only the lines that fit the team (one role, one work process). A product team needs no OpenSpec change for
routine work (reviewing, closing, returning); say so in its work process.

### `.claude/settings.json`

In each team repository, `.claude/settings.json` points the team's sessions at the hub. Use the absolute hub path
and the repository's own team id:

```json
{
  "env": { "HO_HUB": "/home/me/work/my-factory/hub", "HO_TEAM": "app" },
  "permissions": {
    "allow": ["Bash(ho:*)", "Bash(openspec:*)", "Bash(python -m pytest:*)",
              "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)"]
  }
}
```

On Windows a JSON path doubles each backslash: `"HO_HUB": "D:\\work\\my-factory\\hub"`. The `allow` list only saves
permission prompts for common read and hub commands; adjust it to the team's tools.

Commit both files in each repository (`git add -A`, `git commit -m "Team setup"`): the dispatcher works on
committed history.

## 5. Configuration

Start from [radark.toml.example](../radark.toml.example) (in the repository; it is not installed with the package):
copy it into the pipeline folder as `radark.toml` and edit it. Keep the configuration and the run directory in their
own folder, outside the team repositories. The minimum to edit:

- `hub` — the hub directory (it must contain `hub.json`);
- `owner_team` — your hub team, default `owner`; it must be a hub team and not in `[[teams]]`;
- `[[teams]]` — one entry per team, in priority order: `id` (the hub team id), `repo` (the repository path, which
  must exist), `kind` (`"technical"` or `"product"`), optionally `profile = "plain"`; delete the example teams you
  do not have;
- `[triage] team` — the product team that answers the technical teams' questions (it must be a `kind = "product"`
  team in `[[teams]]`); delete the `[triage]` table if you have no product team.

For this guide the result is (Windows paths in single quotes, see section 1):

```toml
hub = "/home/me/work/my-factory/hub"     # Windows: hub = 'D:\work\my-factory\hub'
owner_team = "owner"

[[teams]]
id = "product"
repo = "/home/me/work/my-factory/repos/product"
kind = "product"

[[teams]]
id = "app"
repo = "/home/me/work/my-factory/repos/app"
kind = "technical"

[triage]
team = "product"
```

Every other key has a default; their meanings are in "Configuration (`radark.toml`)" in
[radark/README.md](../radark/README.md#configuration-radarktoml), the work process per team in
"Workflow profiles". Relative paths are resolved from the configuration file's folder. The run directory
(`state.json`, `runs.jsonl`, `console.log`, `PAUSE`, `STOP`, ...) is `.radark` next to `radark.toml` unless you set
`run_dir`; see "Run-time files (`run_dir`)".

`machine.toml` is needed only when several pipelines run on one computer; see
[machine.toml.example](../machine.toml.example) and "Several pipelines on one computer".

## 6. First dry run

From the pipeline folder:

```
cd ~/work/my-factory
radark dry-run          # reads ./radark.toml; or: radark --config <file> dry-run
```

`dry-run` reads the hub and prints what it would do; it starts no session and changes nothing in the hub or the
repositories (it only adds the pipeline to the cockpit's list on this computer). A healthy start on an empty hub
looks like this (releases with the start banner print an ASCII "RA DARK FACTORY" picture first; version numbers and
usage lines vary):

```
Hub: /home/me/work/my-factory/hub
Teams (in priority order):
  product                product   openspec  /home/me/work/my-factory/repos/product
  app                    technical openspec  /home/me/work/my-factory/repos/app
Triage: questions of product, app -> product
Owner (escalations): owner
Claude Code: 2.1.302 (Claude Code)
ho: 0.2.0 (contract 1)
Run directory: /home/me/work/my-factory/.radark
Machine: /home/me/.local/state/radark/machine - limits 2 sessions, 1 test run
Machine slot: free
Usage: no reading yet
guard: next step would start (threshold 90%)
Would keep awake: whole run (default; --keep-awake off lets the computer sleep)
An item that escalates or stalls would send an escalation handover to `owner` (...), then ho sync.
Nothing to do: no selectable candidate.
```

Exit code 0 means the start checks passed (a summary can still be followed by an error line, e.g. for `owner_team`). To give it
work, send the product team a first task as the owner (with `HO_HUB` and `HO_TEAM=owner` set as in section 3):

```
ho new --to product --expects done --title "Plan the first feature" -m "Pick the first backlog item and hand it to app."
ho sync
radark dry-run
```

Now the output lists the candidate and the session it would start, with its prompt:

```
Candidates (newest first):
  2026-01-01T09:00:00.000Z  product              work    act      HO-20260101-ab12  Plan the first feature

Would start: product in /home/me/work/my-factory/repos/product, phase act, handover HO-20260101-ab12
Prompt:
Handover HO-20260101-ab12 ("Plan the first feature"). Phase: act.
...
```

Common errors (`dry-run` stops with exit code 2 and one line; the start of the line tells you which):

| Message starts with | Cause and fix |
|---|---|
| `Configuration error: configuration file not found: ...` | no `radark.toml` in the current folder: `cd` to the pipeline folder or pass `--config <file>` |
| `Configuration error: hub path has no hub.json: ...` | `hub` points to the wrong folder: use the folder `ho init` created |
| `Configuration error: team 'app': repository path does not exist: ...` | fix that team's `repo` |
| `Configuration error: owner_team 'owner' is not a team of the hub ...` | add the owner team to the hub (`hub.json`, then `ho validate` and `ho sync`), or set `owner_team` to your hub team |
| `Configuration error: 'ho' (ho) was not found on PATH ...` / `ho incompatible: ...` | install radark-factory again so that its `ho` is on `PATH`, or fix `ho` in `radark.toml`; see "Compatibility of `ho`" |
| `Configuration error: 'claude' (claude) was not found on PATH` | install Claude Code, or give its full path as `claude` in `radark.toml` |
| `Configuration error: triage: team 'product' ...` | `[triage] team` must be a product team listed in `[[teams]]` |

`dry-run` does **not** check the Claude Code login: a missing login shows only when the first real session starts.
Check it beforehand with `claude auth status`, or run `claude` once interactively and log in.

`radark plan` prints the next few steps the run would take, if every step succeeds.

## 7. The sandbox

To try the whole loop on throw-away data first, the engine ships a script that makes a scratch hub, three team
repositories (`app` on `openspec`, `backend` on `plain`, `product` with a tiny backlog) and a `radark.toml`. It never
touches your real hub or repositories. Pick a new, empty folder:

```
python -m radark.sandbox.make_sandbox ~/work/radark-sandbox        # from a clone: python radark/sandbox/make_sandbox.py <dir>
```

It needs `ho`, `git` and `openspec` on `PATH`, prints what it made, and writes `machine-env.ps1` / `machine-env.sh`,
which set `RADARK_MACHINE_DIR` to a machine directory inside the sandbox, so that the sandbox neither shares limits
with your real pipelines nor appears in your cockpit. Load it in the same shell you run the dispatcher from:

```
. ~/work/radark-sandbox/machine-env.sh                              # PowerShell: . <dir>\machine-env.ps1
radark --config ~/work/radark-sandbox/radark.toml dry-run
```

The output has the shape shown in section 6, with the teams `product`, `app` and `backend` (`plain`) and
`Machine: <dir>/machine`.

With an empty sandbox hub the dry run finds no work. Send `product` a task as the owner (as in section 6, with
`HO_HUB` set to the sandbox hub) and run `radark --config <dir>/radark.toml once` to watch one real session work it.
Run the script again with `--force` to start over (it deletes only a folder it made itself).

## 8. First real run

```
cd ~/work/my-factory
radark run                    # loop until STOP or Ctrl+C
radark run --until 07:00      # the same, but start no new step from 07:00 on
radark once                   # one work item, then exit
```

Where to watch:

- **The console**: one start and one end line per step, problems marked `!`; see "Console" in
  [radark/README.md](../radark/README.md#console). The same lines go to `.radark/console.log`.
- **The cockpit**: `radark cockpit` opens a local page with everything addressed to you, the history of the work
  and what runs now; see [Cockpit](../README.md#cockpit).
- `radark status` (pipelines and limits on this computer), `radark escalations` (escalated and stalled items).

To pause, create `.radark/PAUSE` (the running session finishes, no new one starts until you delete the file); to
stop, create `.radark/STOP` (the run exits between sessions). See "Pause / stop" under "Commands".

**Answering an escalation.** When a session needs you (an escalation keyword such as push or payment, a
`BLOCKED: owner` line, a stalled item), the team sends a handover to the `owner` team, tagged `escalation`:

```
ho sync; ho inbox                                   # as HO_TEAM=owner
ho show HO-20260101-cd34
ho respond HO-20260101-cd34 -m "yes, go ahead"      # or: ho decline HO-20260101-cd34 -m "not now"
ho sync
```

The dispatcher then resumes the waiting session with your answer. The cockpit offers the same answers on its page.
Details: "Owner workflow (escalations)" in [radark/README.md](../radark/README.md#owner-workflow-escalations).

**What the engine never does on its own:** push, publish, deploy, pay, or touch credentials. Those questions are
escalated to you, and your teams' `CLAUDE.md` lists them as owner-only actions; you do them yourself.

From here, the reference is [radark/README.md](../radark/README.md): goal runs (`run --goal`), parallel sessions,
several pipelines on one computer, and how the dispatcher decides.
