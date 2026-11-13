"""Awake clock and sleep detection (change sleep-aware-dispatcher, task 1.1)."""
import time

from harness.clock import Sleep, SleepWatch, awake


class Clocks:
    """A fake wall clock and awake clock moved by hand."""

    def __init__(self, wall=1_800_000_000.0, awake=1000.0):
        self.now, self.up = wall, awake

    def run(self, seconds):
        self.now += seconds
        self.up += seconds

    def sleep(self, seconds):
        self.now += seconds


def watch(c):
    return SleepWatch(wall=lambda: c.now, clock=lambda: c.up)


def test_small_gaps_are_not_a_sleep():
    c = Clocks()
    w = watch(c)
    c.run(5)
    assert w.check() is None
    c.run(1)
    c.sleep(59)
    assert w.check() is None
    c.now -= 3600  # a wall clock set back
    assert w.check() is None


def test_large_gap_is_one_sleep():
    c = Clocks()
    w = watch(c)
    start = c.now
    c.run(120)
    c.sleep(2 * 3600)
    s = w.check()
    assert s == Sleep(start=start + 120, end=start + 120 + 2 * 3600, seconds=2 * 3600)
    assert w.check() is None


def test_awake_increases():
    a = awake()
    time.sleep(0.05)
    b = awake()
    assert 0.02 < b - a < 5
