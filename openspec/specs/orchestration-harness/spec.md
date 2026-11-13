# orchestration-harness Specification

## Purpose

Defines what the controlling tool ("orchestration harness") must do to run our multi-repo AI-team workflow without a human in the loop: wake the right Claude Code agent when the handover hub has work for it, keep it moving through pre-agreed stops, and hand control on. Every candidate platform is scored against these requirements, and the setup change implements them.

## Requirements

### Requirement: Drives Claude Code sessions in each team repository
The harness SHALL start a Claude Code session in a given team repository (working directory = that repository, so its CLAUDE.md, skills, OpenSpec setup and permissions apply), give it a prompt, and observe the session until it ends, on Windows 11. The agents MUST be Claude Code in its current configuration — the installation, account and plan the owner already uses for manual work — and the way the harness launches them MUST stay within that plan's terms.

#### Scenario: Session started in the right repository
- **WHEN** the harness decides the `app` team must act
- **THEN** a Claude Code session runs with `D:\work\app` as its working directory and receives the harness's prompt

#### Scenario: Session end detected
- **WHEN** the agent finishes its turn or the session exits
- **THEN** the harness records that the session ended and whether it ended normally, with an error, or waiting for input

### Requirement: Harness model access is separate from the agents'
If the harness uses a language model for its own decisions, it SHALL use its own credential with a spend limit, and a third-party harness MUST NOT use the owner's Claude Code Pro/Max subscription for that. The harness MAY work without a model. The only exception is a harness that is itself a Claude Code session on the owner's plan using only Claude Code's own features, with primary sources allowing it.

#### Scenario: Harness decides with its own key
- **WHEN** the harness needs a model to classify an agent's question
- **THEN** the call is made with the harness's API key and counted against its spend limit, not against the owner's Claude Code plan

#### Scenario: Only the stop text leaves the machine
- **WHEN** the harness sends an agent's stop to its model
- **THEN** the request holds only the stop text, the team and the handover ID — no repository files or user data — and goes to a provider whose policy excludes training on prompts

#### Scenario: Spend limit reached
- **WHEN** the harness's API key reaches its spend limit
- **THEN** the harness stops making model calls, starts no new agent session, and notifies the owner

#### Scenario: Claude Code session as the dispatcher
- **WHEN** the chosen harness is a Claude Code session on the owner's plan
- **THEN** the decision record cites the primary sources allowing it, and the session uses no third-party agent loop and no other credential

#### Scenario: Agents unaffected by the harness key
- **WHEN** an agent session runs
- **THEN** it uses the owner's existing Claude Code login, and the harness's API key is not passed to it

### Requirement: Wakes the team a handover is waiting for
The harness SHALL find, through the handover hub's `ho` CLI (`ho sync`, `ho inbox --json`), which team has work — `action_required` or `to_review` items — and SHALL ping that team's agent with a prompt naming the handover and the expected next step (for a new task: create an OpenSpec change and implement it; for a finished task: review and close or return it). Teams MUST exchange data only through the hub; the harness MUST NOT carry task content between repositories itself.

#### Scenario: New task handed to a technical team
- **WHEN** `product` creates a handover to `app` and syncs it
- **THEN** the harness pings the `app` agent with the handover ID and the instruction to read it, create an OpenSpec change and implement it

#### Scenario: Nested handover to another team
- **WHEN** the `app` agent, while implementing, sends a handover to `backend`
- **THEN** after the `app` session ends the harness pings `backend`, and after `backend` finishes it pings `app` again to continue

#### Scenario: Nothing to do
- **WHEN** no team has `action_required` or `to_review` items
- **THEN** the harness starts no session and stays idle until the next check

### Requirement: Answers pre-agreed stops without a human
The harness SHALL detect when an agent stops to ask a question or to request a permission, and for stops of a kind agreed in advance it SHALL answer automatically — by default with "choose the best variant and continue, record the assumption". Stops not covered by the agreed list MUST be escalated to the owner (left waiting, with a notice) rather than answered.

#### Scenario: Routine question auto-answered
- **WHEN** an agent asks which of two approaches to take and the question is of an agreed kind
- **THEN** the harness replies "choose the best variant" and the session continues

#### Scenario: Unlisted stop escalated
- **WHEN** an agent asks for something outside the agreed list (for example, to push to a remote or spend money)
- **THEN** the harness does not answer, marks the run as waiting for the owner and notifies the owner

### Requirement: One agent at a time
The harness SHALL run at most one team agent session at any moment across all repositories; further work MUST wait in order until the running session ends. A dispatcher session that only reads the hub and wakes teams, and does no work in a team repository, is not a team agent session. Team sessions left open between phases but idle do not count either; only a session currently working counts.

#### Scenario: Two teams have work
- **WHEN** both `app` and `backend` have `action_required` items
- **THEN** the harness runs one of them, and starts the other only after the first session has ended

### Requirement: Fresh session per OpenSpec phase
By default the harness SHALL start a new session for each OpenSpec phase (propose, apply, archive) of each task in each repository, so that context is restored from OpenSpec artifacts and repository files. It SHALL allow a task to be marked as continuing in one session instead.

#### Scenario: Phases in separate sessions
- **WHEN** a team has finished `propose` for a change
- **THEN** the `apply` phase runs in a new session that starts with no previous conversation

#### Scenario: Kept session for a special case
- **WHEN** a task is marked to continue in one session
- **THEN** the harness resumes that same session for the next phase

### Requirement: Archive only after the task author approves
The harness SHALL let a technical team archive an OpenSpec change only after the handover's author has accepted the result (closed the handover). If the author returns it for rework or for a finishing step (for example, pushing to git), the harness SHALL send the team back to the same change.

#### Scenario: Approved
- **WHEN** the team reports `done` and the author closes the handover
- **THEN** the harness pings the team to archive the change

#### Scenario: Returned for rework
- **WHEN** the author returns the handover with a request
- **THEN** the harness pings the team to continue the same active change, not to archive it

### Requirement: Observable and stoppable
The harness SHALL keep a log of every session it started (team, repository, prompt, start and end time, outcome, auto-answers given) that the owner can read afterwards, and SHALL let the owner pause or stop the loop at any time without leaving a session half-controlled.

#### Scenario: Owner reviews a night run
- **WHEN** the owner opens the log after an unattended run
- **THEN** they see each session in order with its outcome and every automatic answer the harness gave

#### Scenario: Owner stops the loop
- **WHEN** the owner stops the harness while a session runs
- **THEN** no new session starts, and the running session is either let finish or ended cleanly, as the owner chose

### Requirement: Platform choice is recorded with evidence
The platform choice SHALL be recorded in a decision record, approved by the owner, that scores every candidate against each requirement of this spec and names the chosen platform and the runner-up. A requirement left `unknown` for the chosen platform MUST be named as a risk with a plan to check it.

#### Scenario: Account model and cost stated
- **WHEN** the decision record is read
- **THEN** it states which credential powers the harness and which powers the agents, with the sources showing both are within the terms, an estimated monthly cost, the risks and the open questions for the setup change

#### Scenario: Decision approved
- **WHEN** the decision record is complete
- **THEN** the owner has approved it, and every candidate has a score and a source for each requirement

#### Scenario: Hermes assessed
- **WHEN** the decision record is read
- **THEN** it states whether Hermes (as identified in research) is suitable, and why
