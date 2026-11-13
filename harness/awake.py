"""Keeping the computer awake during a run (keep-computer-awake D1, D3, D4)."""
from __future__ import annotations

import ctypes
import datetime as dt
import queue
import re
import threading
from dataclasses import dataclass

from .clock import parse_until

CHECK_S = 30  # well under the shortest Windows idle timeout of 1 min (design D4)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
RANGE_FORM = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")
FORMS = "off, on, HH:MM, YYYY-MM-DD HH:MM or HH:MM-HH:MM (local time)"


@dataclass(frozen=True)
class KeepAwake:
    mode: str = "off"  # off | on | until | range
    until: dt.datetime | None = None  # naive local time (mode until)
    start: dt.time | None = None  # mode range; end < start crosses midnight
    end: dt.time | None = None
    text: str = "off"  # as given, for `goal_start`


def parse_keep_awake(text: str, now: dt.datetime) -> KeepAwake | None:
    """`off`, `on`, a moment as for `--until`, or a daily range `HH:MM-HH:MM` with different ends; None when
    unreadable (design D1)."""
    text = text.strip()
    if text.lower() in ("off", "on"):
        return KeepAwake(text.lower(), text=text.lower())
    if m := RANGE_FORM.fullmatch(text):
        h1, m1, h2, m2 = map(int, m.groups())
        try:
            start, end = dt.time(h1, m1), dt.time(h2, m2)
        except ValueError:
            return None
        return None if start == end else KeepAwake("range", start=start, end=end, text=f"{start:%H:%M}-{end:%H:%M}")
    at = parse_until(text, now)
    return None if at is None else KeepAwake("until", until=at, text=text)


def wanted(setting: KeepAwake, now: dt.datetime) -> bool:
    """Whether the computer is to be kept awake at local time `now` (design D3)."""
    if setting.mode == "on":
        return True
    if setting.mode == "until":
        return now < setting.until
    if setting.mode == "range":
        t = now.time()
        if setting.start < setting.end:
            return setting.start <= t < setting.end
        return t >= setting.start or t < setting.end
    return False


def set_thread_state(on: bool) -> None:
    """Ask Windows to block idle sleep (or stop asking) for the calling thread."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


class Keeper:
    """A daemon thread that holds the Windows request while `wanted` says so (design D4). Changes after the first
    check go to `changes` as `(unix time, on)` for the main thread to report (design D6)."""

    def __init__(self, setting: KeepAwake, set_state=set_thread_state, now=dt.datetime.now, interval: float = CHECK_S):
        self.setting, self.set_state, self.now, self.interval = setting, set_state, now, interval
        self.changes: queue.SimpleQueue = queue.SimpleQueue()
        self.on = False
        self._first = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.setting.mode == "off":
            return
        self._thread = threading.Thread(target=self._run, name="keep-awake", daemon=True)
        self._thread.start()

    def check(self) -> None:
        """One evaluation; the state is set only on a change. The first one is reported by the start line."""
        t = self.now()
        on = wanted(self.setting, t)
        if on != self.on:
            self.set_state(on)
            self.on = on
            if not self._first:
                self.changes.put((t.timestamp(), on))
        self._first = False

    def _run(self) -> None:
        while True:
            self.check()
            if self._stop.wait(self.interval):
                break
        if self.on:  # from this thread: the request belongs to it
            self.set_state(False)
            self.on = False

    def stop(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
            self._thread = None
