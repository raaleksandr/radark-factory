# radark-factory

A small, deterministic dispatcher for a **software factory** built from Claude Code agents: one agent per
repository ("team"), teams talking only through a handover hub, every task an OpenSpec change. The dispatcher
wakes the team that has work, runs each OpenSpec phase (propose → apply → archive) as a fresh `claude -p` session,
answers agreed stops, escalates what only a human may decide, and archives only after the task's author accepts it.

It is a "light" factory rather than a fully dark one: the owner stays in the loop for pushes, deploys, payments and
anything else on the escalation list, and decides through the same hub the agents use.

New here? Start with [Setup from zero](docs/setup.md): from nothing to a first `radark dry-run` and a first run.

## Status

Early and opinionated. Used daily on one Windows 11 PC with four teams. Python 3.11+, standard library only (plus `ho` from radark-handover).
Tested with Claude Code 2.1.302.

## How it fits together

- **Teams** — Git repositories, each with its own `CLAUDE.md` and OpenSpec setup (see
  [Owner-only actions / decisions the team takes](#owner-only-actions--decisions-the-team-takes)), or, with the
  `plain` workflow profile, no spec tool at all (see [Workflow profile](#workflow-profile)).
- **Hub** — a directory (normally a Git repository) of Markdown handovers, edited only through the `ho` CLI
  from [radark-handover](https://github.com/raaleksandr/radark-handover) (installed with radark-factory).
- **Dispatcher** (`radark`) — reads `ho inbox --json` for every team, picks the next step, launches Claude Code
  with hooks injected through `--settings`, logs everything to its run directory. With `[loop] parallel_sessions`
  above 1 it runs sessions of different repositories for unrelated work at the same time (one per repository).

The dispatcher has no model and no credential of its own; agents run on your own Claude Code login.

### Owner-only actions / decisions the team takes

Which decisions a team takes itself and which only the owner takes is each pipeline's own policy, not the engine's.
Write it into the team's `CLAUDE.md` (or the goal file of a goal run), for example:

```markdown
## Owner-only actions
- Publishing a release, pushing to the remote, tagging.
- Spending money above the agreed limit; credentials and accounts; legal questions.

## Decisions the team takes
- A choice between technical options the team already recommended.
- The test strategy, and the order of the team's own work.
- Inform the owner of such a decision with a non-blocking handover (`--expects ack --auto-close`).
```

The engine's prompts tell every team to follow it: the apply and act prompts and the product team's triage
consultation say to decide what the team's instructions allow, record the decision, inform the owner without
blocking, and stop for the owner (`BLOCKED: owner — …`, a triage verdict `owner`) only for what those instructions
reserve for the owner — or, where they say nothing, for a decision, money, credentials or a production step. Setting
a pipeline's policy is the owner's task; without one, behaviour is as before.

### Workflow profile

How a team works is a setting (`[workflow] profile`, or `profile` in a `[[teams]]` entry): `openspec` (default:
propose → apply → archive with OpenSpec changes) or `plain` (one session per handover: do the task, test it, commit
locally, report with `ho done`; no propose or archive session). Prompts can be overridden per file and new profiles
defined next to the configuration; see "Workflow profiles" in [radark/README.md](radark/README.md). Say the
profile in the team's `CLAUDE.md`, so a session started by hand works the same way, for example:

```markdown
## Work process
- This team runs on the `plain` workflow profile: no OpenSpec change. For a handover: read and acknowledge it,
  do the task, run the tests that cover it, commit locally, and report with `ho done <ID> -m "<summary>"`.
```

## Quick start

These lines assume a hub, team repositories and a Claude Code login already exist; to set them up, follow
[Setup from zero](docs/setup.md).

```
uv tool install git+https://github.com/<owner>/radark-factory     # or: pip install .
radark --version                                                     # the installed version and the ho it needs
radark example-config -o D:\work\my-factory\radark.toml          # the example; edit hub, teams, paths
cd D:\work\my-factory
radark dry-run                                                       # reads radark.toml here; run files in .radark\
radark run
```

Pipelines set up before this name change keep working unchanged: without `radark.toml` the dispatcher reads the
legacy `harness.toml` and, without `run_dir`, uses an existing `.harness\` (see "Migrating from harness.toml /
.harness/" in [radark/README.md](radark/README.md)).

`radark` and `python -m radark` are the same command. `python -m harness` is a deprecated alias of `python -m radark`
(same output and exit code, plus one note on standard error), kept for at least one release.

Keep the configuration and run directory of each pipeline in its own folder, outside this repository.
Several pipelines may run on one computer at once: they share one machine-wide usage record, a cap on concurrent
sessions and full test runs (`machine.toml`, see [machine.toml.example](radark/examples/machine.toml.example)), and each team
repository belongs to one running pipeline; `radark status` shows them (see "Several pipelines on one computer" in
[radark/README.md](radark/README.md)).
Full documentation: [radark/README.md](radark/README.md). Design: [openspec/specs](openspec/specs),
decision record: [docs/decisions](docs/decisions), background research: [docs/research](docs/research).

## Cockpit

One local page for the owner: everything addressed to the owner team (escalations the dispatcher created and direct
requests from teams) in the hubs of all pipelines on this computer, split into **Pending** and **Done**, newest first
(by last activity). The **Owner** tab reads like an inbox: one compact line per item with its title, the time it
arrived (created, in local time) and its pipeline name(s); an escalation's line carries the red mark and the
`escalation` badge. A click on a line, or Enter / Space when it has the focus, opens the details below it — sender,
times, tags, `expects`, the text, its history and the answer controls — and closes them again; one item is open at a
time. The open item and an answer being typed survive the periodic refresh.
A short answer is given right on the page: only the actions `ho show` allows for the owner (`respond`, `done` with an
optional note, `ack`, `decline` with a reason), run through `ho` as the owner team, followed by `ho sync`. Files to
place or code to change are handled outside the cockpit, as each item's note says. The page refreshes every 30 s and
on "Refresh".

The **History** tab lists the work the pipelines did: one row per handover per pipeline (two pipelines on one hub
keep their own rows), newest first, with the pipeline, ID, title, team(s), first session start, last session end,
two totals (working time, the sum of the session durations, and wall time, from the first start to the last end,
as `1 h 05 min`), the result (accepted, in review, returned, open, declined, or unknown when the hub does not know
the handover or cannot be read) and an `escalated` badge. A row expands to its sessions in time order (phase, start,
end, duration, outcome, denials and escalations; "running since ..." for a session still running). Filters: a
pipeline (or all) and a period (**Last run**, for each pipeline since its latest dispatcher start; **Last 24 h**;
**Last 7 days**; **All**); a handover is listed when one of its sessions overlaps the period. A summary line counts
the handovers, sessions, working time and accepted ones, and the sessions without a handover (goal checks, idle
asks). The History reads each pipeline's run log (`runs.jsonl` in its run directory) and each hub once per refresh
with `ho list --status all`; it changes nothing. Times are shown in the browser's time zone.

The **Now** tab shows what the pipelines are doing right now: one card per pipeline, running or not, with its name.
A card is `running` (a live dispatcher instance on this computer belongs to the pipeline; its start and PID are
shown), `not running`, or `unknown` (its configuration or run log cannot be read); it says **Goal run** with the goal
file's name and start, or **Regular run**; it lists the sessions running now (team, handover ID, title, phase, since,
for how long; sessions left open by a dispatcher that is gone are listed as interrupted) and the newest run-log event;
a card that is not running also shows the last session's end and outcome, the last start and the stop, when
recorded. A line on top shows the session slots in use against the machine limit, the running pipelines and the
instances that belong to no shown pipeline. Now reads the machine directory's instance records (`instances/*.json`,
liveness by a read-only lock probe), each run directory's `runs.jsonl` and `goal.json`, and each hub's handover list
with `ho list --status all` (reused for 30 s); it changes none of them, not even stale instance records, which are
left to the dispatcher. The tab refreshes every 10 s while it is open.

```
npm run cockpit                       # in this repository: the same as python -m radark cockpit
radark cockpit                        # or: python -m radark cockpit; opens http://127.0.0.1:7391/ in the browser
radark cockpit --port 7400            # another port; or set [cockpit] port in machine.toml (--port wins)
radark cockpit --config D:\work\app-pipeline\radark.toml   # also show this pipeline (repeatable) and register it
radark cockpit --no-browser           # start the server only
radark cockpit --forget D:\work\old-pipeline\radark.toml   # drop a pipeline from the list (the registry only)
```

The pipelines shown are those that ran `run`, `once` or `dry-run` on this computer (a registry `pipelines.json` in the
machine directory) plus each `--config`; the pipeline name is the optional top-level `name` of its `radark.toml`, else
the name of its folder. A configuration that is gone is listed as missing with a "Forget" button. If the port is busy
with a running cockpit, the command opens that one and exits 0; if another program has it, the command exits 2 and
names `--port N` and `[cockpit] port`; it never switches ports on its own.

A pipeline repository gets `npm run cockpit` with one line in its own `package.json`:

```json
"scripts": { "cockpit": "python -m radark cockpit" }
```

**Security:** the server listens on 127.0.0.1 only, has no login and sends nothing anywhere. It refuses requests
for another host name (DNS rebinding) and writes from another origin, takes writes only as `POST` with a JSON body,
sends no CORS headers, and escapes all hub text in the page. It never edits hub files: every change goes through `ho`.

## Development

```
python -m pytest radark/tests
```

Changes go through OpenSpec (`openspec/changes/`). A sandbox with a fake hub and two tiny team repositories:
`python radark/sandbox/make_sandbox.py <dir>`.

### Releasing (owner's steps)

1. When the required `ho` JSON contract changes, update three things together: the `radark-handover` pin in
   `pyproject.toml`, the tag table `HO_RELEASE_CONTRACTS` in `radark/hub.py` (add the new tag with the contract that
   tag's `ho --version --json` reports) and `SUPPORTED_HO_CONTRACTS` next to it. A new pin with the same contract
   is added to the table too.
2. Run the full test suite; all must pass. `radark/tests/test_ho_pin.py` fails when the pinned tag is not in the
   table or its contract is not supported.
3. Then tag and release.

## License

MIT — see [LICENSE](LICENSE).
