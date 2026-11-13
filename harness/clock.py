"""Awake time and sleep detection (sleep-aware-dispatcher D1, D2)."""
from __future__ import annotations

import ctypes
import datetime as dt
import os
import re
import time
from dataclasses import dataclass

SLEEP_MIN_S = 60  # a shorter gap can be one slow loop iteration and is harmless when counted (design D2)


def awake() -> float:
    """Seconds of awake time: stops while the computer sleeps or hibernates (design D1). On Windows
    `time.monotonic()` goes on during sleep; `QueryUnbiasedInterruptTime` (100 ns units) does not."""
    if os.name == "nt":
        t = ctypes.c_ulonglong()
        ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(t))
        return t.value / 1e7
    return time.monotonic()  # stops during suspend on Linux and macOS


@dataclass
class Sleep:
    start: float  # Unix time the computer went to sleep
    end: float  # Unix time it woke (the sample that saw the gap)
    seconds: float


class SleepWatch:
    """Compares real time with awake time between two samples; a gap of a minute or more is a sleep."""

    def __init__(self, wall=time.time, clock=awake):
        self.wall, self.clock = wall, clock
        self.last = (wall(), clock())

    def check(self) -> Sleep | None:
        wall, awake_now = self.wall(), self.clock()
        last_wall, last_awake = self.last
        self.last = (wall, awake_now)
        gap = (wall - last_wall) - (awake_now - last_awake)
        if gap < SLEEP_MIN_S:  # also a wall clock set back
            return None
        return Sleep(start=last_wall + (awake_now - last_awake), end=wall, seconds=gap)


UNTIL_FORM = re.compile(r"(?:(\d{4})-(\d{2})-(\d{2})[ T])?(\d{1,2}):(\d{2})")


def parse_until(text: str, now: dt.datetime) -> dt.datetime | None:
    """`--until`: `H:MM` / `HH:MM` (the next such moment) or `YYYY-MM-DD HH:MM` (`T` accepted), naive local time;
    None when unreadable, out of range or a full date and time not later than `now` (run-until-time D1)."""
    m = UNTIL_FORM.fullmatch(text.strip())
    if not m:
        return None
    year, month, day, hour, minute = m.groups()
    try:
        if year is None:
            at = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            return at if at > now else at + dt.timedelta(days=1)
        at = dt.datetime(int(year), int(month), int(day), int(hour), int(minute))
    except ValueError:
        return None
    return at if at > now else None
