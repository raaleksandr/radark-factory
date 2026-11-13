# Harness research

Questions about choosing the orchestration harness — the tool that wakes our Claude Code team agents and answers their routine stops — whose answers depend on **external, current facts**: third-party tools, Claude Code features, Anthropic's plan terms. The answers feed the scoring matrix and the decision record in [docs/decisions/](../decisions/). The requirements every candidate is scored against are the `orchestration-harness` spec (`openspec/specs/orchestration-harness/`; change archived as `openspec/changes/archive/2026-10-29-harness-selection/`).

The workflow the harness must drive is described in [workflow-today.md](workflow-today.md); briefs quote it.

## What is researched here, and what is not

- **Researched here:** what the candidate platforms are and can do, how people run Claude Code unattended, and what Anthropic's terms allow.
- **Checked by hand instead:** a must-have a report leaves `unknown` or `partly` for a finalist is checked in a short spike on this machine (`spikes/`, git-ignored), recorded in [spikes.md](spikes.md).
- **Not researched:** our own workflow and repositories — read from them directly.

## The loop

1. **Brief** — a self-contained request in [briefs/](briefs/README.md). The owner pastes everything below its marker line into the research tool.
2. **Run** — the owner runs it in claude.ai Research (about 30 minutes) and saves the Markdown result.
3. **Report** — stored unedited in [reports/](reports/README.md).
4. **Findings** — summarised in English in [findings/](findings/README.md) in the same session as the intake.
5. **Decision** — findings fill the candidate list and the scoring matrix in the decision record; a gap a decision waits on becomes a narrower follow-up question here or a spike.

**IDs:** `HR-NNN` ("harness research"), next free number, never reused. (Not `PQ-` or `RQ-`, used by the product and strategy registers.)

**Status:** planned → brief ready → sent → returned → summarised → closed (or dropped, with a note). This register is the source of truth for status.

**Privacy and secrets:** briefs, reports and findings hold no credentials, API keys, repository content beyond what the briefs describe, or anyone's e-mail address or private contact details.

## Register

| ID | Question | Informs | Status | Brief | Report | Findings |
|---|---|---|---|---|---|---|
| HR-001 | What "Hermes" is (exact project), its architecture, whether it can drive external Claude Code sessions, Windows support, licence, maturity, cost | Candidate group 1; verdict on Hermes | closed | [brief](briefs/HR-001-hermes.md) (2026-10-16) | [report](reports/HR-001-hermes.md) (2026-10-16) | [findings](findings/HR-001-hermes.md) (2026-10-29) |
| HR-002 | The 2025–2026 landscape of tools and patterns for running several Claude Code sessions unattended, Anthropic's first-party options included | Candidate groups 2–3; scoring matrix | closed | [brief](briefs/HR-002-orchestrating-claude-code.md) (2026-10-16) | [report](reports/HR-002-orchestrating-claude-code.md) (2026-10-16) | [findings](findings/HR-002-orchestrating-claude-code.md) (2026-10-29) |
| HR-003 | What Claude Code's headless mode, hooks, Agent SDK, `/loop` and inter-session messaging allow today (and on Windows), and what the Pro/Max terms allow for script-driven sessions, a dispatcher session and a harness's own model | Must-haves of first-party candidates; account model (design D5) | closed | [brief](briefs/HR-003-claude-code-headless-limits.md) (2026-10-16) | [report](reports/HR-003-claude-code-headless-limits.md) (2026-10-17) | [findings](findings/HR-003-claude-code-headless-limits.md) (2026-10-29) |

## Notes

- 2026-10-29: late intake. The reports were acted on before they were summarised: `add-python-harness` built the
  dispatcher they recommend, and its sandbox run served as the finalist spike. HR-003 was not dropped — HR-002 did not
  answer the terms questions with primary sources.
- 2026-10-29: all three closed by [decision 0001](../decisions/0001-orchestration-harness.md), approved by the owner.
