import pytest

from harness.hub import Hub, HoLifecycleError, HoNotFound, HoUsageError, HoIntegrityError
from harness.tests.conftest import item, show


def test_inbox_and_show_pass_team_and_hub(env):
    cfg = env.cfg()
    env.set_hub({"inbox:app": {"action_required": [item("HO-20261016-aaaa")], "to_review": []},
                 "show:HO-20261016-aaaa": show("HO-20261016-aaaa")})
    hub = Hub(cfg.ho, cfg.hub)
    assert hub.inbox("app")["action_required"][0]["id"] == "HO-20261016-aaaa"
    assert hub.show("HO-20261016-aaaa")["status"] == "open"
    calls = env.ho_calls()
    assert calls[0] == {"args": ["inbox"], "team": "app", "hub": str(cfg.hub)}
    assert calls[1]["args"] == ["show", "HO-20261016-aaaa"] and calls[1]["team"] is None


@pytest.mark.parametrize("code,exc", [(1, HoUsageError), (2, HoNotFound), (3, HoLifecycleError), (4, HoIntegrityError)])
def test_exit_codes_map_to_exceptions(env, code, exc):
    cfg = env.cfg()
    env.set_hub({"show:HO-x": {"exit": code, "error": {"code": "c", "message": f"boom {code}"}}})
    with pytest.raises(exc, match=f"boom {code}"):
        Hub(cfg.ho, cfg.hub).show("HO-x")


def test_sent_by_reads_list_items(env):
    cfg = env.cfg()
    env.set_hub({"list:backend": {"items": [{"id": "HO-1", "created": "2026-10-16T10:00:00.000Z"}]}})
    assert Hub(cfg.ho, cfg.hub).sent_by("backend")[0]["id"] == "HO-1"
    assert env.ho_calls()[0]["args"] == ["list", "--from", "backend", "--status", "all"]


def test_new_sends_body_on_stdin_and_returns_id(env):
    cfg = env.cfg()
    hub = Hub(cfg.ho, cfg.hub)
    h = hub.new("app", "owner", "app: push?", "Line 1\nПривет", tags=["escalation"], refs=["HO-1"])
    assert h["id"] == "HO-FAKE-0001" and h["from"] == "app" and h["auto_close"]
    call = env.ho_calls()[0]
    assert call["team"] == "app" and call["stdin"] == "Line 1\nПривет"
    assert call["args"] == ["new", "--to", "owner", "--expects", "response", "--title", "app: push?",
                            "--body", "-", "--tag", "escalation", "--ref", "HO-1", "--auto-close"]
    assert hub.inbox("owner")["action_required"][0]["id"] == h["id"]


def test_answer_auto_closes_and_sync_teams(env):
    import subprocess, os, sys
    cfg = env.cfg()
    hub = Hub(cfg.ho, cfg.hub)
    hid = hub.new("app", "owner", "t", "b")["id"]
    subprocess.run(cfg.ho + ["respond", hid, "-m", "yes"], env=dict(os.environ, HO_TEAM="owner"), check=True,
                   capture_output=True)
    shown = hub.show(hid)
    assert shown["status"] == "closed" and [e["action"] for e in shown["events"]] == ["respond", "close"]
    assert hub.inbox("owner")["action_required"] == []
    assert hub.sync()["committed"] and "owner" in hub.teams()
    hub.close(hid, "app", "declined by owner", force=True)
    assert env.ho_calls()[-1]["args"] == ["close", hid, "-m", "declined by owner", "--force"]


# ---- a hub command across a sleep and on a hang (harness-survive-sleep)

import time

from harness.hub import HoError, HoTimeout

H = "HO-20261107-w6xg"


class Jump:
    """Real time that jumps `by` seconds from the `at`-th sample on, as a sleep in the middle of the first call."""

    def __init__(self, by=600, at=2):
        self.by, self.at, self.n = by, at, 0

    def __call__(self):
        self.n += 1
        return time.time() + (self.by if self.n >= self.at else 0)


def hub_for(env, data, **kw):
    cfg = env.cfg()
    env.set_hub(data)
    return Hub(cfg.ho, cfg.hub, slice_s=0.05, **kw)


def test_sleep_during_a_call_is_not_a_timeout(env):
    hub = hub_for(env, {f"show:{H}": show(H), "_delay": {"show": 0.3}}, wall=Jump())
    assert hub.show(H)["id"] == H
    assert len(env.ho_calls()) == 1  # waited for, not run again


def test_awake_time_budget_ignores_real_time():
    """The limit is counted on the awake clock: 600 s of real time pass, 1 s of awake time."""
    import sys
    awake = iter([0.0] + [1.0] * 1000)
    hub = Hub([sys.executable, "-c", "import time; time.sleep(0.3); print('{\"ok\": 1}')"], ".",
              awake=lambda: next(awake), wall=Jump(), timeout=120, slice_s=0.05)
    assert hub._run(["teams"]) == {"ok": 1}


def test_no_answer_is_a_timeout_and_the_process_is_killed(env):
    hub = hub_for(env, {f"show:{H}": show(H), "_hang_once": ["show"]}, timeout=0.5)
    t0 = time.monotonic()
    with pytest.raises(HoTimeout, match=r"^no answer within 0\.5 s$"):
        hub.show(H)
    assert time.monotonic() - t0 < 10 and len(env.ho_calls()) == 1
    assert isinstance(HoTimeout("x"), HoError)


def test_default_limit_text():
    assert Hub(["ho"], ".").timeout == 120
    assert f"no answer within {Hub(['ho'], '.').timeout:g} s" == "no answer within 120 s"


def test_read_that_died_at_the_wake_is_run_once_more(env):
    hub = hub_for(env, {f"show:{H}": show(H), "_die_once": ["show"]}, wall=Jump())
    assert hub.show(H)["id"] == H
    assert [c["args"][0] for c in env.ho_calls()] == ["show", "show"]


def test_read_left_hanging_by_a_sleep_is_run_once_more(env):
    hub = hub_for(env, {f"show:{H}": show(H), "_hang_once": ["show"]}, wall=Jump(), timeout=0.5)
    assert hub.show(H)["id"] == H
    assert len(env.ho_calls()) == 2


def test_read_that_died_without_a_sleep_is_not_run_again(env):
    hub = hub_for(env, {f"show:{H}": show(H), "_die_once": ["show"]})
    with pytest.raises(HoError, match="ho show .* failed"):
        hub.show(H)
    assert len(env.ho_calls()) == 1


def test_read_with_a_hub_error_after_a_sleep_is_not_run_again(env):
    hub = hub_for(env, {f"show:{H}": {"exit": 2, "error": {"code": "c", "message": "gone"}}}, wall=Jump())
    with pytest.raises(HoNotFound, match="gone"):
        hub.show(H)
    assert len(env.ho_calls()) == 1


@pytest.mark.parametrize("key", ["_die_once", "_hang_once"])
def test_write_is_never_run_again(env, key):
    hub = hub_for(env, {key: ["new"]}, wall=Jump(), timeout=0.5)
    with pytest.raises(HoError):
        hub.new("app", "owner", "t", "b")
    assert len(env.ho_calls()) == 1
