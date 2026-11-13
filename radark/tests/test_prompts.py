from radark import prompts
from radark.select import Candidate


def cand(phase, **kw):
    base = dict(kind="work", team="app", handover="HO-20261016-ab12", title="Export", phase=phase,
                recency="", team_index=0)
    base.update(kw)
    return Candidate(**base)


def test_propose_prompt():
    text = prompts.phase_prompt(cand("propose"))
    assert "ho show HO-20261016-ab12 --json" in text and "ho ack HO-20261016-ab12" in text
    assert "cites HO-20261016-ab12" in text and "CHANGE: <change-name>" in text
    assert prompts.STANDING_RULE in text


def test_returned_apply_prompt_keeps_change():
    text = prompts.phase_prompt(cand("apply", change="add-export", return_comment="Add a CSV header.\nThen push."))
    assert "`add-export`" in text and "> Add a CSV header." in text and "> Then push." in text
    assert "Do not create a new change and do not archive" in text


def test_apply_without_change_asks_to_find_it():
    text = prompts.phase_prompt(cand("apply"))
    assert "that cites HO-20261016-ab12 (find it first)" in text and "ho done HO-20261016-ab12" in text


def test_review_archive_act_prompts():
    assert "ho close HO-20261016-ab12" in prompts.phase_prompt(cand("review", kind="review"))
    archive = prompts.phase_prompt(cand("archive", kind="archive", change="add-export"))
    assert "/opsx:archive" in archive and "`add-export`" in archive
    act = prompts.phase_prompt(cand("act", team="product", expects="response"))
    assert "(response)" in act and "no OpenSpec change" in act
    for p in ("review", "archive", "act"):
        assert prompts.STANDING_RULE in prompts.phase_prompt(cand(p))


def test_parse_change():
    assert prompts.parse_change("Done.\nCHANGE: add-export\n") == "add-export"
    assert prompts.parse_change("CHANGE: `fix-x`") == "fix-x"
    assert prompts.parse_change("no change line") is None


def test_resume_messages():
    q = {"question": "A or B?"}
    msg = prompts.resume_message({"verdict": "product", "answer": "A", "reason": "drives activation"}, q, "DEFAULT")
    assert "Product decision: A" in msg and "drives activation" in msg and "A or B?" in msg
    assert prompts.resume_message({"verdict": "technical", "answer": "", "reason": "r"}, q, "DEFAULT").endswith("DEFAULT")


def test_owner_resume_messages():
    link = {"reason": "asked: push?", "question": {"question": "Push to the remote?"}}
    yes = prompts.owner_resume_message(link, "respond", "yes, push to the feature branch\nnot main")
    assert "Push to the remote?" in yes and "> yes, push to the feature branch" in yes and "> not main" in yes
    assert "owner's decision" in yes
    no = prompts.owner_resume_message(link, "decline", "not before the release")
    assert "The owner declined" in no and "> not before the release" in no and "without it" in no
    fresh = prompts.owner_fresh_note(link, "decline", "no")
    assert "The owner declined" in fresh and "do not do that part" in fresh


def test_escalation_body_and_title():
    body = prompts.escalation_body(team="app", handover="HO-1", reason="asked: push?", phase="apply",
                                   change="add-x", question={"question": "Push?"}, result_tail="Need a decision.",
                                   session="sess-1", repo="D:\repo")
    for part in ("asked: push?", "phase apply", "`add-x`", "`sess-1`", '"Push?"', "> Need a decision.",
                 "ho respond", "ho decline", "claude --resume sess-1", "python -m radark clear HO-1"):
        assert part in body
    assert prompts.escalation_title("backend", "x " * 100).endswith("...")
    assert "waiting_for_owner" in prompts.IDLE_PROMPT and prompts.IDLE_SCHEMA["required"] == ["verdict", "reason", "waiting_for_owner"]


def test_timeout_resume_message():
    info = {"session": "s", "phase": "apply", "reason": "idle_timeout", "duration_s": 1500}
    text = prompts.timeout_resume_message(cand("apply", change="add-export"), info)
    assert "`idle_timeout`" in text and "after 25 min" in text and "git status" in text and "index.lock" in text
    assert "partial edit" in text and "shorter steps" in text and "ho done HO-20261016-ab12" in text
    assert "(one exists now)" not in text
    text = prompts.timeout_resume_message(cand("apply", change="add-export"), dict(info, phase="propose", reason="max_time"), True)
    assert "(one exists now)" in text and "propose phase" in text and "shorter steps" not in text
    assert "Then do the next phase" in text and "Implement the OpenSpec change `add-export`" in text


# ---- limit check (check-session-at-time-limit, task 3.1)

def checked_session():
    from radark.runner import SessionResult
    r = SessionResult(run_id="run-1", session_id="s", team="app", handover="HO-20261028-xaai", phase="apply",
                      started="", stream_path="C:/run/sessions/run-1.jsonl")
    r.awake_start, r.last_event_at = 1000.0, 1000.0 + 178 * 60
    for i in range(10):
        r.recent.append((1000.0 + i * 60, "text", f"status {i}"))
    for i in range(14):
        r.recent.append((2000.0 + i * 60, "tool", f"Read: file{i}.ts"))
    r.recent.append((1000.0 + 168 * 60, "tool", "Bash: pnpm e2e"))
    r.recent.append((1000.0 + 170 * 60, "error", "Exit code 1 lint failed"))
    r.running_tool = ("Bash", 540.0, 1000.0 + 177 * 60)
    return r


def test_session_digest():
    now = 1000.0 + 180 * 60
    text = prompts.session_digest(checked_session(), now, ["commits", "tasks"])
    assert "Team `app`, handover HO-20261028-xaai, phase apply." in text
    assert "Running for 3 h 00 min" in text and "heartbeat was 2 min ago" in text
    assert "Tool running now: Bash, for 12 min." in text
    assert "Progress since the session started: new commits, newly checked tasks." in text
    texts = text.split("Recent status texts")[1].split("Recent tool calls")[0]
    assert "status 1\n" not in texts and "status 2" in texts and "status 9" in texts  # the last 8
    tools = text.split("Recent tool calls")[1]
    assert "-12 min  Bash: pnpm e2e" in tools and "-10 min  FAILED: Exit code 1 lint failed" in tools
    assert "Read: file3.ts" not in tools and "Read: file4.ts" in tools  # the last 12 of tool calls and errors
    assert "C:/run/sessions/run-1.jsonl" in text


def test_session_digest_without_events_or_progress():
    from radark.runner import SessionResult
    r = SessionResult(run_id="r", session_id="s", team="backend", handover="HO-1", phase="review", started="")
    text = prompts.session_digest(r, 200 * 60, [])
    assert "No tool is running now." in text and "none (no new commits" in text and "(none)" in text


def test_limit_check_prompt_rules():
    text = prompts.limit_check_prompt("Team `app`, handover HO-1, phase apply.", goal="Ship the export.")
    assert text.startswith("Consultation, not a work session.")
    assert "no file edits, no `ho` write commands, no contact with other teams" in text
    assert "> Team `app`, handover HO-1, phase apply." in text
    assert "`progressing`" in text and "`hung`" in text and "repeats the same action" in text
    assert "Ship the export." in text
    assert prompts.LIMIT_SCHEMA["properties"]["verdict"]["enum"] == ["progressing", "hung"]


def test_timeout_resume_message_carries_the_hung_reason():
    info = {"session": "s", "reason": "max_time", "duration_s": 14400, "phase": "apply",
            "limit_reason": "It reruns the same failing test for an hour."}
    text = prompts.timeout_resume_message(cand("apply", change="add-export"), info)
    assert "after 240 min" in text
    assert "The product team judged the session hung: It reruns the same failing test for an hour." in text
    assert "judged" not in prompts.timeout_resume_message(cand("apply"), {**info, "limit_reason": None})


# ---- harness-no-loop-while-blocked N3, N4: the `BLOCKED: owner` line

def test_parse_blocked():
    assert prompts.parse_blocked("Done part one.\nBLOCKED: owner — go-ahead for a paid benchmark (up to $0.30)") \
        == "go-ahead for a paid benchmark (up to $0.30)"
    assert prompts.parse_blocked("blocked: OWNER – credentials for the store") == "credentials for the store"
    assert prompts.parse_blocked("  BLOCKED: owner - a decision  ") == "a decision"
    assert prompts.parse_blocked("All done.") is None and prompts.parse_blocked(None) is None
    assert prompts.parse_blocked("BLOCKED: owner — first\nmore text\nBLOCKED: owner — second") == "second"
    assert prompts.parse_blocked("BLOCKED: backend — needs the deploy") is None
    assert prompts.parse_blocked("BLOCKED: owner — money\nBLOCKED: backend — x") == "money"
    assert prompts.parse_blocked("We are not BLOCKED: owner — inline") is None


def test_apply_and_act_prompts_tell_how_to_wait_and_block():
    for c in (cand("apply", change="add-export"), cand("apply", change="x", return_comment="Fix it."),
              cand("act", expects="response")):
        text = prompts.phase_prompt(c)
        assert ("If you only wait for another team's result, stop; do not commit or comment just to record that "
                "you are still waiting.") in text
        assert "end your final message with one line `BLOCKED: owner — <what is needed>`" in text
        assert "(a decision, money, credentials, a production step)" in text
    apply = prompts.phase_prompt(cand("apply", change="add-export"))
    assert apply.index("ho done HO-20261016-ab12") < apply.index("BLOCKED: owner")


def test_archive_only_after_the_author_closes():
    propose = prompts.phase_prompt(cand("propose"))
    assert "tasks must not include archiving the change or syncing its specs" in propose
    assert "after the author closes the handover" in propose
    for c in (cand("apply", change="add-export"), cand("apply"), cand("apply", change="x", return_comment="Fix it.")):
        text = prompts.phase_prompt(c)
        assert prompts.APPLY_NO_ARCHIVE in text
        assert "Do not archive the change and do not sync its specs" in text and "leave it unchecked" in text
        assert text.index(prompts.APPLY_NO_ARCHIVE) < text.index("ho done HO-20261016-ab12")
    archive = prompts.phase_prompt(cand("archive", kind="archive", change="add-export"))
    assert "Archive the OpenSpec change `add-export` (the /opsx:archive workflow)" in archive
    assert prompts.APPLY_NO_ARCHIVE not in archive and "must not include archiving" not in archive


def test_local_todo_reaches_the_product_team():
    for c in (cand("apply", change="add-export"), cand("apply"), cand("apply", change="x", return_comment="Fix it.")):
        text = prompts.phase_prompt(c)
        assert prompts.APPLY_LOCAL_TODO in text
        assert "line starting `Local TODO:` (id, title, one line why)" in text and "leave the line out" in text
        assert text.index("ho done HO-20261016-ab12") < text.index("Local TODO:")
    review = prompts.phase_prompt(cand("review", kind="review"))
    assert prompts.REVIEW_LOCAL_TODO in review
    assert "belongs in the product backlog" in review and "close or return message" in review
    assert "not a reason to return the handover: add it yourself" in review
    for c in (cand("propose"), cand("archive", kind="archive", change="add-export"),
              cand("act", team="product", expects="response")):
        text = prompts.phase_prompt(c)
        assert "Local TODO" not in text and "local TODO" not in text


def test_propose_review_archive_prompts_have_no_blocked_line():
    for phase in ("propose", "review", "archive"):
        text = prompts.phase_prompt(cand(phase, change="add-export"))
        assert "BLOCKED" not in text and "still waiting" not in text


# ---- long-wait rule (check-long-waits D2, D5)

def test_long_wait_rule_default_limit():
    text = prompts.long_wait_rule(20.0)
    assert "ended after 20 minutes without output" in text and "20.0" not in text
    assert "longer than 10 minutes" in text and "at least once every 10 minutes" in text
    assert "two checks in a row show no progress" in text and "treat it as hung" in text


def test_long_wait_rule_interval_follows_the_limit():
    for limit, interval in [(30, 15), (1, 1), (25, 12), (2.5, 1)]:
        text = prompts.long_wait_rule(limit)
        assert f"ended after {limit:g} minutes" in text, limit
        assert f"longer than {interval} minutes" in text and f"every {interval} minutes" in text, limit
    assert "ended after 2.5 minutes" in prompts.long_wait_rule(2.5)


WRAP_UP_HEAD = (
    "The dispatcher stopped this session: it reached its time limit after 360 min and 3 limit-check extensions, in "
    "the apply phase of handover HO-20261016-ab12, and no extension is left. You now have 15 min to wrap up; after "
    "that the session is cut. The step that was running was cut off: the working tree may hold a partial edit, and an "
    "interrupted git command may have left a stale `.git/index.lock`. Check `git status` and your last step first: "
    "finish the partial step only if it is quick, otherwise undo it (remove the lock only if no git process is "
    "running). Start no new work. Commit what works. Then report what is done the way this phase reports it, and name "
    "what is left so the author can hand it over as a follow-up: "
)


def test_wrap_up_message_apply_verbatim():
    text = prompts.wrap_up_message(cand("apply", change="add-export"), 360, 3, 15)
    assert text == (
        WRAP_UP_HEAD + "check off the finished tasks in the change's `tasks.md`, write the open ones under a `Left "
        "for a follow-up` note there, commit, and report with `ho done HO-20261016-ab12 -m \"<summary>\"` whose "
        "summary starts with `Wrapped up at the time limit.` and has a line `Left: <what is left>`. "
        + prompts.APPLY_NO_ARCHIVE + "\n\n" + prompts.STANDING_RULE)


def test_wrap_up_message_other_phase_extension_count_lock_and_goal():
    text = prompts.wrap_up_message(cand("propose"), 180, 0, 15, index_lock=True, goal="Ship it.")
    assert text.startswith("The dispatcher stopped this session: it reached its time limit after 180 min, in the "
                           "propose phase of handover HO-20261016-ab12, and no extension is left.")
    assert "a stale `.git/index.lock` (one exists now). Check" in text
    assert ("as a follow-up: say what is left on a line starting `Left:` in your final message. "
            "End your final message with one line `CHANGE: <change-name>`") in text
    assert prompts.goal_block("Ship it.") in text and text.endswith(prompts.STANDING_RULE)
    one = prompts.wrap_up_message(cand("review"), 240, 1, 7.5)
    assert "after 240 min and 1 limit-check extension, in the review" in one and "You now have 7.5 min" in one
    assert "ho close HO-20261016-ab12" in one and "(one exists now)" not in one


def test_review_prompt_time_limit_paragraph_verbatim():
    history = [{"kind": "wrap_up", "reason": None, "extensions": 3, "elapsed_s": 6 * 3600, "outcome": "finished"},
               {"kind": "cut", "reason": "max_time", "extensions": 0, "elapsed_s": 3 * 3600 + 300,
                "outcome": "error"},
               {"kind": "wrap_up", "reason": "max_time", "extensions": 1, "elapsed_s": 5400, "outcome": "error"}]
    text = prompts.phase_prompt(cand("review"), time_limits=history)
    assert (
        "\n\nThe worker's sessions on this handover ran into the time limit: wrapped up after 6 h with 3 extensions "
        "(finished); cut by max_time after 3 h 05 min with 0 extensions; wrapped up after 90 min with 1 extension "
        "(error, max_time). The task may be too big for one session: check the result's `Left:` list, and if work is "
        "left, return the handover for it or record it as a follow-up (a new backlog item or handover) and say which "
        "in your close or return message."
    ) in text
    assert "ran into the time limit" not in prompts.phase_prompt(cand("review"))
    assert "ran into the time limit" not in prompts.phase_prompt(cand("review"), time_limits=[])


# ---- fewer-owner-waits D6, D9

def test_denial_rule_names_the_temp_dir_and_the_ways():
    text = prompts.denial_rule("/run/tmp/app")
    assert "temporary files go to `/run/tmp/app`" in text
    assert "`git restore -- <file>`" in text and "`Stop-Process -Id <pid>`" in text and "task tool" in text
    assert "`BLOCKED: owner — denied: <command>; needed for: <why>; suggestion: <what you propose>`" in text
    assert prompts.parse_blocked("BLOCKED: owner — denied: x; needed for: y; suggestion: z") == (
        "denied: x; needed for: y; suggestion: z")


def test_apply_and_act_prompts_tell_the_team_to_decide_what_its_policy_allows():
    for c in (cand("apply", change="add-export"), cand("act", team="product", expects="done")):
        text = prompts.phase_prompt(c)
        assert "your team's instructions (your `CLAUDE.md`, the owner's goal) allow your team to take, take it" in text
        assert "`ho new --to <owner team> --expects ack --auto-close`" in text
        assert "Use the BLOCKED line only for what those instructions reserve for the owner" in text
        assert text.index(prompts.TEAM_DECIDES) < text.index("`BLOCKED: owner — <what is needed>`")


def test_consult_prompt_names_the_team_policy_and_the_note():
    text = prompts.consult_prompt({"question": "Map or object?"}, "app", "HO-20261016-ab12", "add-export")
    assert "Decide everything they allow you to decide" in text
    assert "answer `owner` only for what they reserve for the owner" in text
    assert "`note_for_owner`" in text and "needs only an acknowledgement" in text


def test_verdict_schema_note_is_optional():
    schema = prompts.VERDICT_SCHEMA
    assert schema["properties"]["note_for_owner"] == {"type": "string"}
    assert "note_for_owner" not in schema["required"]


def test_verdict_without_or_with_note_parses():
    from radark.__main__ import parse_verdict
    from radark.runner import SessionResult
    r = SessionResult(run_id="r", session_id="s", team="product", handover="H", phase="consult", started="")
    r.structured = {"verdict": "technical", "answer": "", "reason": "internal"}
    assert parse_verdict(r) == {"verdict": "technical", "answer": "", "reason": "internal"}
    r.structured = {**r.structured, "note_for_owner": " FYI "}
    assert parse_verdict(r)["note_for_owner"] == "FYI"


def test_escalation_body_lists_denials_and_a_text_question():
    body = prompts.escalation_body(team="app", handover="H", reason="permission denied: Bash", phase="apply",
                                   change=None, question="How should the team go on?", result_tail="",
                                   session="s", repo="r",
                                   denied=[{"tool": "Bash", "input": "curl x"}, {"tool": "Write", "input": "{}"}])
    assert "## Question\n\n> How should the team go on?" in body
    assert "## Denied\n\n- Bash: `curl x`\n- Write: `{}`" in body
