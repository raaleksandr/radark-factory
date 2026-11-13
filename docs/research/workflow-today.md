# Our workflow today (manual)

As of 2026-10-16. Read from the hub guide (`<hub>/AGENTS.md`, `ho --help`), `hub.json`, and each team repository's `CLAUDE.md`, `.claude/settings.json` and `openspec/` — read only. Research briefs quote this page as the description of the workflow a harness must drive.

## Teams and repositories

Each team is one Git repository on one Windows 11 PC, worked on by a Claude Code agent (CLI, version 2.1.301 on 2026-10-16) that the owner opens by hand in a terminal in that directory. The agent's role comes from the repository's `CLAUDE.md`.

| Team (`HO_TEAM`) | Repository | Role |
|---|---|---|
| `strategy` | `D:\work\strategy` | Company strategy; no product code. Sends everything about the product to `product`. |
| `product` | `D:\work\product` | Product manager for the product: backlog (`backlog/BACKLOG.md`, items `BL-NNN`), research, proposals; no product code. Decides the next task and hands it to a technical team. |
| `app` | `D:\work\app` | Technical team: the Chrome extension (TypeScript, pnpm monorepo). Default receiver of the product tasks; asks `backend` for what it needs and owns the API contract. |
| `backend` | `D:\work\backend` | Technical team: website and backend (Next.js, Prisma). Rules include "push to `dev` only after a green `npm run test:e2e`". |

A fifth team, `games`, is registered in the hub but is not part of this workflow.

Every repository has the same setup: OpenSpec (`openspec/`, schema `spec-driven`, changes in `openspec/changes/`), the `/opsx:*` commands and OpenSpec skills (propose, apply, archive, explore, sync, update) in `.claude/`, and `.claude/settings.json` setting `HO_HUB=D:\work\hub`, `HO_TEAM=<team>` and allowing `Bash(ho:*)` without a prompt. `backend` also has a `PreToolUse` hook on `Bash` that auto-allows its server SSH commands.

## The handover hub

`D:\work\hub` is a local Git repository of Markdown "handovers" between teams, edited only through the `ho` CLI (Python). It is the only channel between teams; one repository never edits another.

- `ho sync` — first and last in every session (git pull --rebase, commit, push; the hub has no remote today, so it commits locally).
- `ho inbox --json` — three arrays: `action_required` (addressed to my team, still needs my action, including parts returned to me), `to_review` (sent by my team, every recipient finished: review, then `close` or `return`), `updates` (new comments or answers; `ho seen <ID>`). Items carry `id`, `title`, `from`, `expects`, `my_state`, `recipients`, `priority`, `due`, `path`.
- `ho show <ID> --json` — `body`, full `events` history, `allowed_actions`.
- Recipient actions by `expects`: `ack` → `ho ack`; `done` → `ho done -m`; `response` → `ho respond --body-file`; also `decline`, `comment`.
- Sender actions: `ho return <ID> --to <team> -m` (rework), `ho close <ID>` (accept and archive), `ho new --to … --expects … --title … --body-file … --json`.
- Errors in JSON with exit codes 1 (bad input), 2 (not found), 3 (action not allowed now), 4 (hub integrity).

IDs look like `HO-20261013-j7lg`. A harness can learn who has work by running `ho inbox --json` with `HO_TEAM` set to each team in turn.

## How a task moves today

1. `product` keeps the backlog and picks the next task (a routine stream with its own runbook in the product repository; no OpenSpec change there for routine work).
2. It writes a self-contained handover and sends it to one technical team (by default `app`; `backend` only for backend-only work), `--expects done`, then `ho sync`.
3. **The owner** opens a Claude Code terminal in that team's repository and tells the agent that a handover is waiting.
4. The technical agent reads it (`ho inbox`, `ho show`), creates an OpenSpec change citing the handover ID (`/opsx:propose`), `ack`s it, and implements it (`/opsx:apply`). By habit each OpenSpec phase — propose, apply, archive — runs in a fresh session; context is restored from the change's artifacts and repository files. Sometimes one session is kept longer on purpose.
5. If it needs another team (e.g. `app` needs a backend endpoint), it sends its own handover to `backend` and pauses that part. **The owner** then opens `backend`, which works the same way and answers; then **the owner** goes back to `app` to continue.
6. When finished, the technical team reports `ho done <ID> -m "…"`. **The owner** opens `product`, which sees the item in `to_review` and either closes it (accepted) or returns it (rework, or a finishing step such as pushing to Git).
7. Only after the author closes the handover does the technical team archive the change (`/opsx:archive`) — again **the owner** opens that session. Several changes may be active in one repository at once if a task waits on another.

Teams are run one at a time, never two repositories at once (shared machine resources, and conflicts).

## Where a human is in the loop

- **Waking the right team:** nothing starts an agent; the owner opens the terminal and pings it at every step above.
- **Stops:** agents stop to ask the owner a question (often "which of these approaches?", via the `AskUserQuestion` tool or as plain text at the end of a turn), to ask permission for a tool not on the allowlist, or end their turn early. The owner answers. For the tasks chosen for automation, routine questions are to be answered "choose the best variant and continue, record the assumption"; anything else (push to a remote, spend money, unclear scope) still needs the owner.
- **Phase changes:** the owner closes one session and starts the next phase in a new one.

The harness must replace the owner in these three places — and only there.
