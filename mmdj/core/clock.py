"""The beat clock. Everything in mmdj is a function of this.

Rates are expressed in beats, never seconds, so changing the tempo moves the
whole show together instead of leaving half of it behind.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

MIN_BPM = 40.0
MAX_BPM = 220.0

# Taps further apart than this start a new measurement rather than extending the
# old one -- otherwise a forgotten tap from a minute ago drags the average.
TAP_TIMEOUT = 2.0
TAP_HISTORY = 8


@dataclass
class Clock:
    """Maps wall time to musical time.

    Changing the tempo keeps the *current beat* continuous: the show does not
    jump when you tap a new tempo mid-bar, it just starts running faster.
    """

    bpm: float = 120.0
    started: float = field(default_factory=time.monotonic)
    beat_at_start: float = 0.0
    _taps: list[float] = field(default_factory=list)

    def beat(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return self.beat_at_start + (now - self.started) * (self.bpm / 60.0)

    def set_bpm(self, bpm: float, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        # Re-anchor first, so the beat we are on does not jump
        self.beat_at_start = self.beat(now)
        self.started = now
        self.bpm = max(MIN_BPM, min(MAX_BPM, bpm))

    def tap(self, now: float | None = None) -> float | None:
        """Tap tempo. Returns the new bpm once there are enough taps."""
        now = time.monotonic() if now is None else now

        if self._taps and now - self._taps[-1] > TAP_TIMEOUT:
            self._taps.clear()
        self._taps.append(now)
        self._taps[:] = self._taps[-TAP_HISTORY:]

        if len(self._taps) < 2:
            return None

        gaps = [b - a for a, b in zip(self._taps, self._taps[1:], strict=False)]
        mean = sum(gaps) / len(gaps)
        if mean <= 0:
            return None

        self.set_bpm(60.0 / mean, now)
        return self.bpm

    def resync(self, now: float | None = None) -> None:
        """Drop the current beat back onto a downbeat (the '1')."""
        now = time.monotonic() if now is None else now
        self.beat_at_start = 0.0
        self.started = now
