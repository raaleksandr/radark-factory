"""The cockpit's History of finished work (change cockpit-history): pure functions on invented run log records, and
`GET /api/history` through the part-1 server harness with fake `ho`. Invented IDs and neutral names only."""
import datetime as dt
import json
import os
import re
from pathlib import Path

import pytest

from radark import cockpit
from radark import cockpit_history as ch
from radark.tests.test_cockpit import WRITES, calls_of, named, page_source, second_pipeline, start  # noqa: F401

A, B, C, D, E, F = (f"HO-20990101-{x * 4}" for x in "abcdef")
NOW = dt.datetime(2099, 1, 10, 12, 0, tzinfo=dt.timezone.utc)


def t(hours_ago: float = 0, minutes: float = 0) -> str:
    return ch.iso(NOW - dt.timedelta(hours=hours_ago) + dt.timedelta(minutes=minutes))


def at(day: int, hh: int, mm: int = 0) -> str:
    return f"2099-01-{day:02d}T{hh:02d}:{mm:02d}:00.000Z"


def start_rec(time, hid, phase="apply", team="app"):
    return {"time": time, "event": "session_start", "team": team, "repo": "x", "handover": hid, "phase": phase,
            "prompt": "secret prompt", "resume": None}


def end_rec(time, hid, phase="apply", team="app", duration=None, outcome="finished", **extra):
    rec = {"time": time, "event": "session_end", "team": team, "handover": hid, "phase": phase, "session": "s-1",
           "exit_code": 0, "outcome": outcome, "denials": 0, "escalations": 0, "timed_out": False,
           "result": "secret result text", "stream": "/somewhere/stream.jsonl"}
    if duration is not None:
        rec["duration_s"] = duration
    rec.update(extra)
    return rec


def session(hid, start, end, phase="apply", team="app", **extra):
    s, e = ch.parse_time(start), ch.parse_time(end)
    return [start_rec(start, hid, phase, team), end_rec(end, hid, phase, team, (e - s).total_seconds(), **extra)]


def past(hh: int, mm: int = 0) -> str:
    """A time before the real now, for the server tests (they use the real clock)."""
    return f"2020-01-10T{hh:02d}:{mm:02d}:00.000Z"


def boot(time):
    return {"time": time, "event": "dispatcher_start", "once": False, "pid": 1, "goal": None}


def log_of(records, skipped=0):
    return ch.Log("ok", list(records), skipped)


def run(records, items=None, period="all", pipeline=None, name="alpha"):
    return ch.history([ch.PipelineInput(name, log_of(records), items if items is not None else {})], period,
                      pipeline, NOW)


def by_id(data):
    return {(r["pipeline"], r["id"]): r for r in data["rows"]}


# ---- 1.1 reading the run log

def test_bad_lines_skipped_and_counted():
    good = json.dumps(boot(t(1)))
    lines = [good, "not json", "[1, 2]", json.dumps({"event": "session_start"}), "", good,
             '{"time": "2099-01-10T11:00:00.000Z", "event": "sess']
    records, skipped = ch.parse_log("\n".join(lines).encode("utf-8"))
    assert len(records) == 2 and skipped == 4


def test_missing_file_gives_no_records(tmp_path):
    log = ch.LogCache().read(tmp_path / "runs.jsonl")
    assert log.state == "missing" and log.records == []


def test_cache_reuses_until_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "runs.jsonl"
    path.write_text(json.dumps(boot(t(2))) + "\n", encoding="utf-8")
    calls = []
    real = ch.parse_log
    monkeypatch.setattr(ch, "parse_log", lambda data: calls.append(1) or real(data))
    cache = ch.LogCache()
    assert len(cache.read(path).records) == 1
    assert len(cache.read(path).records) == 1 and len(calls) == 1
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(start_rec(t(1), A)) + "\n")
    assert len(cache.read(path).records) == 2 and len(calls) == 2


# ---- 1.2 sessions

def test_fifo_pairing_by_team_handover_phase():
    recs = [start_rec(at(10, 9), A), start_rec(at(10, 9, 5), B), end_rec(at(10, 9, 30), B, duration=1500),
            end_rec(at(10, 9, 40), A, duration=2400)]
    built = ch.build_sessions(recs)
    got = {s.handover: (s.start, s.duration_s, s.running) for s in built.sessions}
    assert got[A] == (ch.parse_time(at(10, 9)), 2400, False)
    assert got[B] == (ch.parse_time(at(10, 9, 5)), 1500, False)


def test_unmatched_end_gets_start_from_duration():
    built = ch.build_sessions([end_rec(at(10, 10), A, duration=600)])
    (s,) = built.sessions
    assert s.start == ch.parse_time(at(10, 9, 50)) and s.end == ch.parse_time(at(10, 10)) and not s.running


def test_unmatched_end_without_duration_has_no_start():
    (s,) = ch.build_sessions([end_rec(at(10, 10), A)]).sessions
    assert s.start is None and s.duration_s == 0 and s.end is not None


def test_interrupted_closes_the_session():
    recs = [start_rec(at(10, 9), A), {"time": at(10, 9, 20), "event": "interrupted", "team": "app",
                                      "handover": A, "phase": "apply", "session": "s-9", "cause": "sleep"}]
    (s,) = ch.build_sessions(recs).sessions
    assert s.outcome == "interrupted" and s.duration_s == 1200 and s.session == "s-9" and not s.running


def test_dispatcher_start_closes_open_sessions():
    recs = [start_rec(at(10, 9), A), boot(at(10, 10)), start_rec(at(10, 10, 5), A)]
    first, second = ch.build_sessions(recs).sessions
    assert first.outcome == "interrupted" and first.end is None and first.duration_s == 0 and not first.running
    assert second.running


def test_running_and_timed_out_sessions():
    recs = [start_rec(at(10, 9), A), start_rec(at(10, 9), B),
            end_rec(at(10, 10), B, duration=3600, outcome="error", timed_out=True, timeout_reason="wall time")]
    data = run(recs)
    rows = by_id(data)
    a, b = rows[("alpha", A)], rows[("alpha", B)]
    assert a["running"] and a["last_end"] is None and a["sessions"][0]["running"] and a["working_s"] == 0
    assert a["sessions"][0]["start"] == at(10, 9)
    assert b["sessions"][0]["outcome"] == "timed out (wall time)"


def test_same_team_on_two_handovers_at_once_and_missing_fields():
    recs = [start_rec(at(10, 9), A), start_rec(at(10, 9, 1), B),
            {"time": at(10, 9, 30), "event": "session_end", "team": "app", "handover": B, "phase": "apply"},
            end_rec(at(10, 9, 45), A, duration=2700)]
    rows = by_id(run(recs))
    assert rows[("alpha", B)]["working_s"] == 29 * 60 and rows[("alpha", B)]["sessions"][0]["outcome"] is None
    assert rows[("alpha", A)]["working_s"] == 2700


def test_two_pipelines_logs_stay_apart():
    alpha = ch.PipelineInput("alpha", log_of(session(A, at(10, 9), at(10, 9, 30)) +
                                             session(B, at(10, 10), at(10, 10, 30))), {})
    beta = ch.PipelineInput("beta", log_of(session(A, at(10, 11), at(10, 11, 10))), {})
    data = ch.history([alpha, beta], "all", None, NOW)
    assert sorted(by_id(data)) == [("alpha", A), ("alpha", B), ("beta", A)]
    assert by_id(data)[("beta", A)]["working_s"] == 600


# ---- 1.3 rows, totals and order

def test_phases_in_time_order():
    recs = (session(A, at(10, 12), at(10, 12, 10), "archive") + session(A, at(10, 9), at(10, 9, 30), "propose") +
            session(A, at(10, 10), at(10, 11), "apply"))
    (row,) = run(recs)["rows"]
    assert [s["phase"] for s in row["sessions"]] == ["propose", "apply", "archive"]
    assert [s["duration_s"] for s in row["sessions"]] == [1800, 3600, 600]


def test_working_and_wall_time():
    recs = session(A, at(10, 9), at(10, 9, 30)) + session(A, at(10, 11), at(10, 11, 35))
    (row,) = run(recs)["rows"]
    assert row["working_s"] == 3900 and row["wall_s"] == 9300
    assert row["first_start"] == at(10, 9) and row["last_end"] == at(10, 11, 35)


def test_newest_first():
    recs = session(A, at(10, 9), at(10, 10)) + session(B, at(10, 10), at(10, 11))
    assert [r["id"] for r in run(recs)["rows"]] == [B, A]


def test_teams_in_first_seen_order():
    recs = session(A, at(10, 9), at(10, 9, 10), "triage", "product") + session(A, at(10, 10), at(10, 11))
    assert run(recs)["rows"][0]["teams"] == ["product", "app"]


def test_sessions_without_a_handover_counted_apart():
    recs = (session(None, at(10, 9), at(10, 9, 2), "goal", "product") +
            session(None, at(10, 10), at(10, 10, 2), "goal", "product") + session(A, at(10, 11), at(10, 11, 30)))
    data = run(recs)
    assert [r["id"] for r in data["rows"]] == [A]
    assert data["summary"]["other_sessions"] == 2 and data["summary"]["other_s"] == 240


# ---- 1.4 results and the escalated badge

def item(hid, status, states, expects="done", title=None):
    return {"id": hid, "title": title or f"Title {hid[-4:]}", "status": status, "expects": expects,
            "archived": status == "closed", "to": list(states), "recipients": dict(states)}


@pytest.mark.parametrize("it, teams, result", [
    (item(A, "closed", {"app": "done"}), ["app"], "accepted"),
    (item(A, "resolved", {"app": "done"}), ["app"], "in review"),
    (item(A, "resolved", {"app": "answered"}, "response"), ["app"], "in review"),
    (item(A, "open", {"app": "returned"}), ["app"], "returned"),
    (item(A, "open", {"app": "acknowledged"}), ["app"], "open"),
    (item(A, "open", {"app": "pending"}), ["app"], "open"),
    (item(A, "resolved", {"app": "acknowledged"}, "ack"), ["app"], "in review"),
    (item(A, "resolved", {"app": "declined"}), ["app"], "declined"),
    (item(A, "closed", {"app": "declined"}), ["app"], "declined"),
    (item(A, "open", {"app": "done", "backend": "pending"}), ["product"], "open"),
    (item(A, "open", {"app": "done", "backend": "pending"}), ["app"], "in review"),
    (None, ["app"], "unknown"),
])
def test_result_kinds(it, teams, result):
    assert ch.result_of(it, teams) == result


def test_results_from_hub_items_and_titles():
    recs = sum((session(h, at(9, 9 + i), at(9, 9 + i, 30)) for i, h in enumerate((A, B, C, D, E, F))), [])
    items = {h["id"]: h for h in (item(A, "closed", {"app": "done"}), item(B, "resolved", {"app": "done"}),
                                  item(C, "open", {"app": "returned"}), item(D, "open", {"app": "acknowledged"}),
                                  item(E, "resolved", {"app": "declined"}))}
    rows = by_id(run(recs, items))
    got = {hid: rows[("alpha", hid)]["result"] for hid in (A, B, C, D, E, F)}
    assert got == {A: "accepted", B: "in review", C: "returned", D: "open", E: "declined", F: "unknown"}
    assert rows[("alpha", A)]["title"] == "Title aaaa" and rows[("alpha", F)]["title"] == F
    assert run(recs, items)["summary"]["accepted"] == 1


def test_failed_hub_gives_unknown():
    p = ch.PipelineInput("alpha", log_of(session(A, at(10, 9), at(10, 9, 30))), None, "ho failed")
    data = ch.history([p], "all", None, NOW)
    assert data["rows"][0]["result"] == "unknown" and data["pipelines"][0]["hub_error"] == "ho failed"


def test_escalated_badge():
    recs = (session(A, at(10, 9), at(10, 9, 30)) + session(B, at(10, 9), at(10, 9, 30), team="product") +
            session(C, at(10, 9), at(10, 9, 30), team="backend", escalations=1) + session(D, at(10, 9), at(10, 9, 9))
            + [{"time": at(10, 9, 31), "event": "escalation", "team": "app", "handover": A, "reason": "x"},
               {"time": at(10, 9, 31), "event": "escalation_sent", "team": "product", "handover": B,
                "escalation": "HO-20990101-zzzz", "reason": "x"}])
    rows = by_id(run(recs))
    assert {h: rows[("alpha", h)]["escalated"] for h in (A, B, C, D)} == {A: True, B: True, C: True, D: False}


# ---- 1.5 periods, filters, summary

def test_last_run_per_pipeline():
    alpha = [boot(t(28)), *session(A, t(27), t(26.5)), boot(t(4)), *session(B, t(3), t(2.5))]
    beta = [boot(t(28)), *session(C, t(27), t(26.5)), *session(D, t(20), t(19))]
    data = ch.history([ch.PipelineInput("alpha", log_of(alpha), {}), ch.PipelineInput("beta", log_of(beta), {})],
                      "last-run", None, NOW)
    assert sorted(by_id(data)) == [("alpha", B), ("beta", C), ("beta", D)]
    assert {p["name"]: p["since"] for p in data["pipelines"]} == {"alpha": t(4), "beta": t(28)}


def test_last_run_without_dispatcher_start_is_the_whole_log():
    data = run(session(A, t(24 * 30), t(24 * 30 - 1)), period="last-run")
    assert [r["id"] for r in data["rows"]] == [A] and data["pipelines"][0]["since"] is None


@pytest.mark.parametrize("period, ids", [("24h", {B, C, D}), ("7d", {A, B, C, D}), ("all", {A, B, C, D, E})])
def test_periods_and_overlap_at_the_window_start(period, ids):
    recs = (session(E, t(24 * 9), t(24 * 9 - 1)) + session(A, t(48), t(47)) + session(B, t(25), t(23)) +
            session(C, t(2), t(1)) + [start_rec(t(30), D)])  # D: running since 30 h ago
    assert {r["id"] for r in run(recs, period=period)["rows"]} == ids


def test_row_keeps_all_sessions_while_the_summary_counts_the_window():
    recs = session(A, t(48), t(47)) + session(A, t(2), t(1.5))
    data = run(recs, period="24h")
    (row,) = data["rows"]
    assert len(row["sessions"]) == 2 and row["working_s"] == 3600 + 1800
    assert data["summary"] == {"handovers": 1, "sessions": 1, "working_s": 1800, "accepted": 0,
                               "other_sessions": 0, "other_s": 0}


def test_pipeline_filter_and_unknown_name():
    inputs = [ch.PipelineInput("alpha", log_of(session(A, t(2), t(1))), {}),
              ch.PipelineInput("beta", log_of(session(B, t(2), t(1))), {})]
    assert [r["pipeline"] for r in ch.history(inputs, "all", "beta", NOW)["rows"]] == ["beta"]
    nothing = ch.history(inputs, "all", "gamma", NOW)
    assert nothing["rows"] == [] and nothing["pipelines"] == []


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        run([], period="1y")


# ---- 2.1 the server

def write_log(cfg_path: Path, records) -> Path:
    from radark import config as config_mod
    run_dir = config_mod.load(cfg_path).run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "runs.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def hub_item(hid, status, states, expects="done"):
    return {**item(hid, status, states, expects), "from": "product", "body": "Body.", "events": [],
            "created": at(1, 8), "last_activity": at(1, 9)}


def snapshot(*dirs):
    out = {}
    for d in dirs:
        for p in Path(d).rglob("*"):
            if p.is_file():
                out[str(p)] = (p.stat().st_size, p.stat().st_mtime_ns)
    return out


def test_api_history_two_pipelines_one_hub(env, start):
    env.set_hub({f"show:{A}": hub_item(A, "closed", {"app": "done"}),
                 f"show:{B}": hub_item(B, "open", {"app": "returned"})})
    alpha = named(env, "alpha")
    beta = second_pipeline(env, "beta")
    now = dt.datetime.now(dt.timezone.utc)
    recent = lambda h: ch.iso(now - dt.timedelta(hours=h))  # noqa: E731
    write_log(alpha, [boot(recent(30)), *session(A, recent(29), recent(28)), *session(B, recent(3), recent(2))])
    write_log(beta, [*session(A, recent(24 * 10), recent(24 * 10 - 1)), start_rec(recent(1), C)])
    c = start([alpha, beta])
    before_calls = len(env.ho_calls())
    files = snapshot(env.root)
    status, data = c.json("GET", "/api/history?period=all")
    assert status == 200
    assert sorted((r["pipeline"], r["id"]) for r in data["rows"]) == [("alpha", A), ("alpha", B), ("beta", A),
                                                                     ("beta", C)]
    rows = by_id(data)
    assert rows[("alpha", A)]["result"] == "accepted" and rows[("alpha", B)]["result"] == "returned"
    assert rows[("beta", C)]["result"] == "unknown" and rows[("beta", C)]["running"]
    lists = [x for x in env.ho_calls()[before_calls:] if x["args"][0] == "list"]
    assert len(lists) == 1 and lists[0]["args"] == ["list", "--status", "all"] and lists[0]["team"] == "owner"
    assert not [x for x in env.ho_calls() if x["args"][0] in WRITES]
    text = json.dumps(data)
    for secret in ("secret prompt", "secret result text", "stream.jsonl", str(env.root), "runs.jsonl"):
        assert secret not in text
    status, data = c.json("GET", "/api/history?pipeline=alpha&period=7d")
    assert status == 200 and [r["id"] for r in data["rows"]] == [B, A] and data["pipeline"] == "alpha"
    assert data["summary"]["handovers"] == 2 and data["summary"]["accepted"] == 1
    status, data = c.json("GET", "/api/history")
    assert status == 200 and data["period"] == "last-run"
    assert sorted((r["pipeline"], r["id"]) for r in data["rows"]) == [("alpha", A), ("alpha", B), ("beta", A),
                                                                     ("beta", C)]
    after = snapshot(env.root)
    changed = {k for k in set(files) | set(after) if files.get(k) != after.get(k)}
    assert all(k.endswith((".calls", ".calls-lock")) for k in changed), changed  # the fake's own call record


def test_api_history_log_grows(env, start):
    env.set_hub({})
    alpha = named(env, "alpha")
    path = write_log(alpha, [start_rec(past(9), A)])
    c = start([alpha])
    (row,) = c.json("GET", "/api/history?period=all")[1]["rows"]
    assert row["running"]
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(end_rec(past(9, 30), A, duration=1800)) + "\n")
    (row,) = c.json("GET", "/api/history?period=all")[1]["rows"]
    assert not row["running"] and row["working_s"] == 1800


def test_api_history_missing_log_and_failing_hub(env, start):
    env.set_hub({"list:all": {"exit": 1, "error": {"code": "broken", "message": "hub broken"}}})
    alpha = named(env, "alpha")
    c = start([alpha])
    status, data = c.json("GET", "/api/history")
    assert status == 200 and data["rows"] == [] and data["pipelines"][0]["log"] == "missing"
    write_log(alpha, session(A, past(9), past(9, 30)))
    status, data = c.json("GET", "/api/history?period=all")
    assert status == 200 and data["rows"][0]["result"] == "unknown"
    assert "hub broken" in data["pipelines"][0]["hub_error"]


def test_api_history_bad_period_and_foreign_host(env, start):
    alpha = named(env, "alpha")
    c = start([alpha])
    status, data = c.json("GET", "/api/history?period=1y")
    assert status == 400 and data["error"] == "unknown period" and data["allowed"] == list(ch.PERIODS)
    before = len(env.ho_calls())
    status, _, _ = c.request("GET", "/api/history", headers={"Host": f"attacker.invalid:{c.port}"})
    assert status == 403 and len(env.ho_calls()) == before
    status, headers, _ = c.request("GET", "/api/history?period=all")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_items_do_not_send_the_run_directory(env, start):
    env.set_hub({})
    c = start([named(env, "alpha")])
    assert "run_dir" not in json.dumps(c.items()["pipelines"])


# ---- 2.2 the page

def test_page_history_tab():
    src = page_source()
    nav = src[src.index("<nav>"):src.index("</nav>")]
    history = re.search(r"<button[^>]*>History</button>", nav).group(0)
    assert "disabled" not in history and 'data-tab="history"' in history
    assert re.search(r"<button disabled[^>]*>Pipelines status</button>", nav)
    for text in ("Last run", "Last 24 h", "Last 7 days", "All pipelines", "/api/history", "running since",
                 "escalated", "toLocaleString"):
        assert text in src
    code = src[src.index("// ---- History of finished work"):src.index("</script>")]
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert not re.search(r"""(src|href)\s*=\s*["']?\s*(https?:)?//""", src)


def test_page_served_has_the_history_tab(env, start):
    status, _, body = start().request("GET", "/")
    html = body.decode("utf-8")
    assert status == 200 and 'id="tab-history"' in html and "coming later" in html
    assert "History of finished work - coming later" not in html
