"""Two clocks: simulated telemetry time and real control time (PHASE5 7.2)."""

from __future__ import annotations

import time

_PROCESS_START = time.monotonic()


class DataClock:
    """Simulated epoch seconds; only tool calls advance it."""

    def __init__(self, start: float) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class ControlClock:
    """Real monotonic time, used for approval deadlines and trace timestamps."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        # time.sleep can return slightly early relative to time.monotonic (coarse Windows
        # timers), so keep sleeping until the monotonic clock has really advanced that far.
        target = time.monotonic() + seconds
        remaining = seconds
        while remaining > 0:
            time.sleep(remaining)
            remaining = target - time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - _PROCESS_START
