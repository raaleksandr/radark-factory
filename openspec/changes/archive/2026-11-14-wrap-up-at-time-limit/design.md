# Design: wrap-up at the last time limit

Handover HO-20261113-5lbl (RB-015).

## Context

`Runner.run()` asks `on_deadline(r, elapsed)` (from `Dispatcher.limit_watch`) when a work session reaches its
deadline: seconds extend it, `None` ends it by `max_time`. After `limit_checks` extensions `on_deadline` returns
`None` without asking. Sessions without a product team or with `limit_checks = 0` get no `on_deadline` at all and
are cut at `session_max_minutes`. A session cut by a time limit that made progress is resumed once by the item's
next session with `timeout_resume_message`, with full limits again.

`claude -p` runs with `stdin=DEVNULL` and one prompt; there is no channel to tell a running headless session
something.

## Goals / Non-goals

- Goal: a progressing session that runs out of time ends with a commit and a report, and the product team sees that
  the task was too big.
- Non-goal: changing how limit checks judge a session, the inactivity limit, sleep handling, or the resume after a
  cut wrap-up session.

## Decisions

### W1. Mechanism: stop and resume the same session with a wrap-up prompt

At the last deadline the runner ends the process tree (as today) and the dispatcher immediately starts
`claude -p <wrap-up prompt> --resume <session>` in the same step, with `timeout_s = wrap_up_minutes * 60` and no
limit check (`on_deadline = None`). The resumed session has the whole conversation, so it knows what it did.

Alternative considered: `--input-format stream-json` to push a user message into the running session. It would keep
the running step, but it changes the launch mode of every session (stdin, prompt delivery, hooks) and a message is
only read between turns, so a long tool call would still delay it. Rejected as too big for this item; the lost step
is handled by the prompt (check `git status`, finish or undo the partial step), as the existing time-limit resume
already does.

### W2. When a wrap-up happens

A wrap-up happens for a **work session** (a session for a handover, not a consultation) when it reaches its
deadline and no extension is left:

- limit checks on, all `limit_checks` extensions used;
- `limit_checks = 0`, or no product team configured (no check is possible) — at `session_max_minutes`.

No wrap-up (cut by `max_time` as today) when:

- the limit check answered `hung` (handover: "no wrap-up for a hung session");
- the check failed or gave a malformed verdict. Assumption: the spec already treats this "as if the check had
  answered `hung`", so it stays a cut; this keeps one rule for "the check did not say progressing".
- the session is itself a wrap-up session (no second wrap-up), a consultation, a limit check, a goal check or an
  idle ask;
- `wrap_up_minutes = 0` (setting turned off).

The inactivity limit, a sleep (wake grace) and the owner's Ctrl+C keep applying to the session and to the wrap-up
session. The grace period counts awake time like every other session limit.

### W3. Runner interface

`on_deadline` may return a new sentinel `WRAP_UP` (module constant in `runner.py`) besides seconds and `None`.
On `WRAP_UP` the runner ends the process tree and sets `r.interrupt_cause = "wrap_up"` (not `timeout_reason`), so
the first part is classified `interrupted`: it is not the session's fault and is not reported as an error. The
callback stores the number of extensions used in `r.extensions_used` for the log.

`limit_watch` returns an `on_deadline` for every work session when `wrap_up_minutes > 0`, even without a product
team or with `limit_checks = 0`; it then answers `WRAP_UP` at the first deadline without a check. Its
`on_deadline` answers `WRAP_UP` instead of `None` when the extensions are used up. With `wrap_up_minutes = 0`
everything is as today.

### W4. Dispatcher flow

In `Dispatcher.session()`, after `runner.run()`, when `r.interrupt_cause == "wrap_up"`:

1. log `wrap_up_start` (team, handover, phase, session, `elapsed_s`, `extensions_used`, `grace_min`) and print
   `! <team> <handover>: time limit after <duration>, <n> extensions used; asking the session to wrap up within
   <grace> min`;
2. record the first part in `rec["sessions"]` as usual (outcome `interrupted`) and print its end line;
3. call `self.session(team, prompts.wrap_up_message(...), phase, handover, resume=r.session_id,
   since=since or r.started, title=title, step="wrap-up", wrap_up=True)`: `wrap_up=True` passes
   `timeout_s = grace`, no `limit_watch`, and returns the wrap-up result;
4. log `wrap_up` with the same fields plus `wrap_up_session`, `outcome`, `timeout_reason`, `duration_s`;
5. return the wrap-up session's result as the step's result.

The item's handling in `run_candidate` then works on the wrap-up result unchanged: finished within the grace → the
normal outcome (`finished`, or `question` / `waiting_for_owner` as usual); cut after the grace → `max_time`,
`error`, and with progress the existing resume-after-timeout. Progress is measured from the first part's start
(`since`). The first part's `interrupted` outcome must not reach the item's interrupted-resume logic (only the
returned wrap-up result does).

`recover()` needs no change: the wrap-up session is a normal running session in `meta["running"]`.

### W5. Wrap-up prompt (exact text)

`prompts.wrap_up_message(c, minutes, extensions, grace, index_lock, goal)`:

```
The dispatcher stopped this session: it reached its time limit after {minutes} min{ext}, in the {phase} phase of
handover {handover}, and no extension is left. You now have {grace} min to wrap up; after that the session is cut.
The step that was running was cut off: the working tree may hold a partial edit, and an interrupted git command may
have left a stale `.git/index.lock`{lock}. Check `git status` and your last step first: finish the partial step
only if it is quick, otherwise undo it (remove the lock only if no git process is running). Start no new work.
Commit what works. Then report what is done the way this phase reports it, and name what is left so the author can
hand it over as a follow-up: {phase_part}
```

(One paragraph in the code; the line breaks above are only for reading.)

- `{ext}`: ` and {n} limit-check extension(s)` when `n > 0` (`extension` for 1), else empty.
- `{lock}`: ` (one exists now)` when the lock file exists.
- `{phase_part}` for apply: ``check off the finished tasks in the change's `tasks.md`, write the open ones under a
  `Left for a follow-up` note there, commit, and report with `ho done {handover} -m "<summary>"` whose summary
  starts with `Wrapped up at the time limit.` and has a line `Left: <what is left>`.`` followed by
  `APPLY_NO_ARCHIVE`. For the other phases: ``say what is left on a line starting `Left:` in your final message.``
  followed by `_closing(c)`.
- Then the goal block and the standing rule, as `_with_rule` adds them.

The text is tested verbatim and quoted in the `ho done` of this handover.

### W6. Signal of a too-big task (smallest visible mechanism)

1. **Run log and console** (W4): `wrap_up_start` / `wrap_up` events and the `!` line; the existing `limit_check`
   events already show each extension.
2. **State history:** the item's state record gets `time_limits: [{"session", "phase", "kind": "wrap_up" | "cut",
   "reason", "extensions", "elapsed_s", "outcome"}]`, appended for every wrap-up and every work session cut by
   `max_time` or `idle_timeout` (so repeated resumed sessions on the same handover are counted too). It lives as
   long as the item's state record.
3. **Review prompt:** when the product team's review of that handover is built and `time_limits` is not empty,
   `phase_prompt` (review) gets one paragraph (exact text):

```
The worker's sessions on this handover ran into the time limit: {summary}. The task may be too big for one
session: check the result's `Left:` list, and if work is left, return the handover for it or record it as a
follow-up (a new backlog item or handover) and say which in your close or return message.
```

   `{summary}`: one item per entry, e.g. `wrapped up after 6 h with 3 extensions (finished)`,
   `cut by max_time after 3 h with 0 extensions`, joined by `; `.

Assumption: the review candidate finds the worker's record by handover ID in the state (`self.state.get(handover)`),
as the review already does for `unescalated_denials`. No `ho` change is needed; the worker's own `ho done` with
`Left:` also reaches the product team through the hub.

### W7. Setting

`[loop] wrap_up_minutes`, float, default **15**, must be `>= 0`; `0` turns the wrap-up off. Documented in
`radark/README.md` (and the sandbox's `harness.toml` if it lists `[loop]` keys). 15 min is enough for a commit, a
task list update and `ho done`, and below the default inactivity limit (20 min).

## Risks

- The step running at the stop is lost (as with the cut today); the prompt makes the session check it first.
- A wrap-up session that ignores the prompt costs at most `wrap_up_minutes` more before the cut.
- `ho done` on partial work is intended: the product team decides in review (W6 paragraph) whether to return the
  handover or record a follow-up.

## Split

Everything fits one change; nothing is left for a second item.
