# radark-factory

A small, deterministic dispatcher for a **software factory** built from Claude Code agents: one agent per
repository ("team"), teams talking only through a handover hub, every task an OpenSpec change. The dispatcher
wakes the team that has work, runs each OpenSpec phase (propose → apply → archive) as a fresh `claude -p` session,
answers agreed stops, escalates what only a human may decide, and archives only after the task's author accepts it.

It is a "light" factory rather than a fully dark one: the owner stays in the loop for pushes, deploys, payments and
anything else on the escalation list, and decides through the same hub the agents use.

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

```
uv tool install git+https://github.com/<owner>/radark-factory     # or: pip install .
copy radark.toml.example D:\work\my-factory\radark.toml             # edit hub, teams, paths
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
sessions and full test runs (`machine.toml`, see [machine.toml.example](machine.toml.example)), and each team
repository belongs to one running pipeline; `radark status` shows them (see "Several pipelines on one computer" in
[radark/README.md](radark/README.md)).
Full documentation: [radark/README.md](radark/README.md). Design: [openspec/specs](openspec/specs),
decision record: [docs/decisions](docs/decisions), background research: [docs/research](docs/research).

## Development

```
python -m pytest radark/tests
```

Changes go through OpenSpec (`openspec/changes/`). A sandbox with a fake hub and two tiny team repositories:
`python radark/sandbox/make_sandbox.py <dir>`.

## License

MIT — see [LICENSE](LICENSE).
