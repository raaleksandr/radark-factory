"""Selection on recorded hub snapshots (task 2.4)."""
from radark import select as sel
from radark.state import new_record
from radark.tests.conftest import TEAMS, item, show

T1, T2, T3 = "2026-10-16T10:00:00.000Z", "2026-10-16T11:00:00.000Z", "2026-10-16T12:00:00.000Z"


def inbox(ar=(), tr=()):
    return {"action_required": list(ar), "to_review": list(tr), "updates": []}


def rec(team, **kw):
    r = new_record(team)
    for k, v in kw.items():
        if k in ("escalated", "stalled", "keep_session"):
            r["flags"][k] = v
        else:
            r[k] = v
    return r


def run(inboxes, shows, records=None):
    return sel.ordered(sel.candidates(TEAMS, inboxes, shows, records or {}))


def test_newest_wins_nested_handover_to_site():
    a, b = "HO-20261016-aaaa", "HO-20261016-bbbb"
    inboxes = {"app": inbox([item(a, my_state="acknowledged", last=T1)]),
               "backend": inbox([item(b, sender="app", last=T2)])}
    shows = {a: show(a, [(T1, "app", "ack", "")]), b: show(b, created=T2)}
    cands = run(inboxes, shows, {a: rec("app", change="add-x", phase="propose")})
    assert [(c.team, c.handover, c.phase) for c in cands] == [("backend", b, "propose"), ("app", a, "apply")]
    assert sel.pick(cands).team == "backend"


def test_tie_goes_to_team_order():
    a, b = "HO-20261016-aaaa", "HO-20261016-bbbb"
    inboxes = {"backend": inbox([item(b)]), "app": inbox([item(a)])}
    shows = {a: show(a, created=T1), b: show(b, created=T1)}
    assert sel.pick(run(inboxes, shows)).team == "app"


def test_nothing_to_do():
    assert sel.pick(run({t: inbox() for t, _ in TEAMS}, {})) is None


def test_escalated_and_stalled_skipped():
    a, b = "HO-20261016-aaaa", "HO-20261016-bbbb"
    inboxes = {"app": inbox([item(a)]), "backend": inbox([item(b)])}
    records = {a: rec("app", escalated=True), b: rec("backend", stalled=True)}
    assert run(inboxes, {a: show(a), b: show(b)}, records) == []


def test_new_technical_handover_is_propose_and_product_is_act():
    a, b = "HO-20261016-aaaa", "HO-20261016-bbbb"
    inboxes = {"app": inbox([item(a)]), "product": inbox([item(b, sender="strategy", expects="response")])}
    cands = {c.handover: c for c in run(inboxes, {a: show(a), b: show(b)})}
    assert cands[a].phase == "propose" and cands[a].change is None
    assert cands[b].phase == "act" and cands[b].expects == "response"


def test_done_not_closed_gives_review_not_archive():
    a = "HO-20261016-aaaa"
    shows = {a: show(a, [(T1, "app", "ack", ""), (T2, "app", "done", "ok")], status="resolved")}
    inboxes = {"product": inbox(tr=[item(a, last=T2)]), "app": inbox()}
    cands = run(inboxes, shows, {a: rec("app", change="add-x", phase="done")})
    assert [(c.kind, c.team, c.phase) for c in cands] == [("review", "product", "review")]


def test_closed_gives_archive_with_change():
    a = "HO-20261016-aaaa"
    shows = {a: show(a, [(T1, "app", "done", "ok"), (T2, "product", "close", "")], status="closed")}
    cands = run({}, shows, {a: rec("app", change="add-x", phase="done")})
    assert [(c.kind, c.team, c.phase, c.change, c.recency) for c in cands] == [("archive", "app", "archive", "add-x", T2)]
    assert sel.handovers_to_show({}, {a: rec("app", phase="done")}) == {a}


def test_returned_gives_apply_on_same_change_with_comment():
    a = "HO-20261016-aaaa"
    events = [(T1, "app", "done", "ok"), (T2, "product", "return", "Also push to dev.", "app")]
    inboxes = {"app": inbox([item(a, my_state="returned", last=T2)])}
    cands = run(inboxes, {a: show(a, events)}, {a: rec("app", change="add-export", phase="done")})
    c = sel.pick(cands)
    assert (c.phase, c.change, c.return_comment) == ("apply", "add-export", "Also push to dev.")


def test_apply_needs_a_known_change():
    a = "HO-20261016-aaaa"
    inboxes = {"app": inbox([item(a, my_state="acknowledged")])}

    def phase(r, state="acknowledged"):
        return sel.pick(run({"app": inbox([item(a, my_state=state)])}, {a: show(a)}, {a: r})).phase
    assert phase(rec("app", phase="propose")) == "propose"  # a record from an older dispatcher
    assert phase(rec("app", change="add-x", phase="propose")) == "apply"
    assert phase(rec("app", phase="apply")) == "apply"  # a return seen in the hub
    assert phase(rec("app", phase="propose"), state="returned") == "apply"
    assert sel.pick(run(inboxes, {a: show(a)})).phase == "propose"


def test_seen_events_do_not_count_for_recency():
    a = "HO-20261016-aaaa"
    s = show(a, [(T1, "app", "ack", ""), (T3, "app", "seen", "")])
    assert sel.latest_activity(s) == T1


def test_kept_session_is_resumed_by_same_team():
    a = "HO-20261016-aaaa"
    r = rec("app", change="add-x", phase="propose", keep_session=True)
    r["sessions"] = [{"id": "sess-1", "team": "app", "phase": "propose"}]
    c = sel.pick(run({"app": inbox([item(a, my_state="acknowledged")])}, {a: show(a)}, {a: r}))
    assert (c.phase, c.resume_session) == ("apply", "sess-1")


def test_escalation_handover_is_not_a_review_item():
    """The owner responded to an escalation handover sent from app (design E5)."""
    a, e1, e2 = "HO-20261016-aaaa", "HO-20261016-esc1", "HO-20261016-esc2"
    tagged = dict(item(e1, sender="app", last=T3), tags=["escalation"])
    untagged_link = item(e2, sender="app", last=T3)  # known only through the state link
    inboxes = {"app": inbox(ar=[dict(tagged, id="HO-20261016-esc3")], tr=[tagged, untagged_link])}
    records = {a: rec("app", escalated=True, escalation={"handover": e2, "answered": False})}
    assert run(inboxes, {}, records) == []
    assert sel.handovers_to_show(inboxes, records) == set()


def test_timeout_resume_overrides_kept_session_for_same_team_only():
    a = "HO-20261016-aaaa"
    timed = {"session": "sess-cut", "team": "app", "phase": "apply", "reason": "max_time", "duration_s": 60}
    r = rec("app", change="add-x", phase="apply", keep_session=True, resume_after_timeout=timed)
    r["sessions"] = [{"id": "sess-1", "team": "app", "phase": "propose"}]
    c = sel.pick(run({"app": inbox([item(a, my_state="acknowledged")])}, {a: show(a)}, {a: r}))
    assert (c.resume_session, c.timeout_resume) == ("sess-cut", timed)
    r["resume_after_timeout"] = dict(timed, team="backend")
    c = sel.pick(run({"app": inbox([item(a, my_state="acknowledged")])}, {a: show(a)}, {a: r}))
    assert (c.resume_session, c.timeout_resume) == ("sess-1", None)


# ---- waiting for a handover's result (wait-for-handover-result)

V, G = "HO-20261025-pq34", "HO-20261025-mn12"


def test_part_finished_mirrors_ho_satisfied():
    states = ["pending", "acknowledged", "done", "answered", "declined", "returned"]
    finished = {"ack": {"acknowledged", "declined"}, "done": {"done", "declined"}, "response": {"answered", "declined"}}
    for expects, ok in finished.items():
        for state in states:
            assert sel.part_finished(expects, state) == (state in ok), (expects, state)
        assert not sel.part_finished(expects, None)  # missing state counts as pending
    assert [s for s in states if sel.part_finished("other", s)] == ["declined"]
    assert [s for s in states if sel.part_finished(None, s)] == ["declined"]


def sent_h(hid=G, to=("backend",), recipients=None, expects="done", status="open", refs=(V,), tags=()):
    h = {"id": hid, "title": "Backend part", "to": list(to), "expects": expects, "status": status,
         "refs": list(refs), "tags": list(tags)}
    if recipients is not False:
        h["recipients"] = recipients if recipients is not None else {t: "pending" for t in to}
    return h


def held(handovers, records=None, links=()):
    records = {V: rec("app")} if records is None else records
    return sel.held_items({"app": handovers}, records, set(links))


def test_open_handover_with_pending_part_holds_the_senders_item():
    assert held([sent_h()]) == {V: [{"handover": G, "team": "backend", "state": "pending", "title": "Backend part"}]}
    assert held([sent_h(recipients=False)])[V][0]["state"] == "pending"


def test_finished_or_closed_handovers_do_not_hold():
    for h in (sent_h(recipients={"backend": "done"}), sent_h(recipients={"backend": "declined"}),
              sent_h(expects="response", recipients={"backend": "answered"}),
              sent_h(expects="ack", recipients={"backend": "acknowledged"}), sent_h(status="closed")):
        assert held([h]) == {}, h


def test_returned_and_acknowledged_done_hold():
    assert held([sent_h(recipients={"backend": "returned"})])[V][0]["state"] == "returned"
    assert held([sent_h(recipients={"backend": "acknowledged"})])[V][0]["state"] == "acknowledged"


def test_escalation_handover_does_not_hold():
    assert held([sent_h(to=("owner",), tags=("escalation",))]) == {}
    assert held([sent_h("HO-esc", to=("owner",))], links={"HO-esc"}) == {}


def test_direct_request_to_owner_holds():
    assert held([sent_h(to=("owner",), expects="response")])[V][0]["team"] == "owner"


def test_ref_without_a_record_of_the_sender_is_not_held():
    assert held([sent_h()], records={}) == {}
    assert held([sent_h()], records={V: rec("backend")}) == {}


def test_held_work_item_is_not_selected():
    inboxes = {"app": inbox([item(V, my_state="acknowledged", last=T3)]),
               "backend": inbox([item(G, sender="app", last=T2)])}
    shows = {V: show(V, created=T3), G: show(G, created=T2)}
    records = {V: rec("app", phase="apply")}
    waits = {V: [{"handover": G, "team": "backend", "state": "pending"}]}
    assert [c.handover for c in run(inboxes, shows, records)] == [V, G]
    cands = sel.ordered(sel.candidates(TEAMS, inboxes, shows, records, held=waits))
    assert [(c.team, c.handover, c.phase) for c in cands] == [("backend", G, "propose")]


def test_held_item_selected_when_returned_or_cut_short():
    waits = {V: [{"handover": G, "team": "backend", "state": "pending"}]}
    returned = {"app": inbox([item(V, my_state="returned")])}
    records = {V: rec("app", phase="done")}
    assert [c.handover for c in sel.candidates(TEAMS, returned, {V: show(V)}, records, held=waits)] == [V]
    timed = {"session": "sess-cut", "team": "app", "phase": "apply", "reason": "max_time"}
    inboxes = {"app": inbox([item(V, my_state="acknowledged")])}
    records = {V: rec("app", phase="apply", resume_after_timeout=timed)}
    assert [c.resume_session for c in sel.candidates(TEAMS, inboxes, {V: show(V)}, records, held=waits)] == ["sess-cut"]
    records[V]["resume_after_timeout"] = dict(timed, team="backend")
    assert sel.candidates(TEAMS, inboxes, {V: show(V)}, records, held=waits) == []


def test_review_and_archive_are_not_held():
    waits = {V: [{"handover": G, "team": "backend", "state": "pending"}]}
    shows = {V: show(V, [(T2, "product", "close", "")], status="closed")}
    records = {V: rec("app", change="add-x", phase="done")}
    inboxes = {"product": inbox(tr=[item(V)])}
    kinds = [c.kind for c in sel.candidates(TEAMS, inboxes, shows, records, held=waits)]
    assert sorted(kinds) == ["archive", "review"]
