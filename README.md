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

- **Teams** — Git repositories, each with its own `CLAUDE.md` and OpenSpec setup.
- **Hub** — a directory (normally a Git repository) of Markdown handovers, edited only through the `ho` CLI
  from [radark-handover](https://github.com/raaleksandr/radark-handover) (installed with radark-factory).
- **Dispatcher** (`radark`) — reads `ho inbox --json` for every team, picks the next step, launches Claude Code
  with hooks injected through `--settings`, logs everything to its run directory.

The dispatcher has no model and no credential of its own; agents run on your own Claude Code login.

## Quick start

```
uv tool install git+https://github.com/<owner>/radark-factory     # or: pip install .
copy harness.toml.example D:\work\my-factory\harness.toml           # edit hub, teams, paths
radark --config D:\work\my-factory\harness.toml dry-run
radark --config D:\work\my-factory\harness.toml run
```

`radark` and `python -m radark` are the same command. `python -m harness` is a deprecated alias of `python -m radark`
(same output and exit code, plus one note on standard error), kept for at least one release.

Keep the configuration and run directory of each pipeline in its own folder, outside this repository.
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
