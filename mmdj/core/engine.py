"""The engine: turn a Show plus a Clock into frames, and hand them to a driver.

Still pure at the edges -- `render_show` takes a beat and returns frames. The
only thing with a heartbeat is `Engine.run`, and even that just calls the pure
part on a timer. That split is what lets the whole show be tested without a
bridge, without lights, and without sleeping.
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

from mmdj.core.clock import Clock
from mmdj.core.patterns import Frame, render
from mmdj.core.show import Show
from mmdj.drivers.base import Driver


def render_show(show: Show, beat: float) -> dict[str, Frame]:
    """Every light's frame at this beat. Pure: no I/O, no clock, no surprises."""
    if show.blackout:
        return {light: Frame(0.0, 0.0, 0.0) for t in show.tracks for light in t.targets}

    energy = show.master.energy
    master = show.master.brightness

    frames: dict[str, Frame] = {}
    for track in show.active_tracks():
        # A track drives a set of lights, and `spread` deals its pattern across
        # them -- so one track can be a group (unison) or a wave (staggered).
        pattern = show.effective(track)          # resolves a link, if it has one
        count = len(track.targets)
        for i, light in enumerate(track.targets):
            frame = render(pattern, beat, energy, index=i, count=count)
            frames[light] = Frame(
                hue=frame.hue,
                saturation=frame.saturation,
                brightness=frame.brightness * master,
            )
    return frames


class Engine:
    """Runs the show. Swap the driver to change how fast it can talk."""

    def __init__(self, show: Show, driver: Driver, clock: Clock | None = None) -> None:
        self.show = show
        self.driver = driver
        self.clock = clock or Clock(bpm=show.bpm)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        await self.driver.open()
        self._task = asyncio.create_task(self._loop())
        logger.info("engine started at {:.0f} fps ({} driver)",
                    self.driver.fps, type(self.driver).__name__)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
        await self.driver.close()
        logger.info("engine stopped")

    async def _loop(self) -> None:
        interval = 1.0 / self.driver.fps
        try:
            while not self._stop.is_set():
                started = time.monotonic()

                self.clock.bpm = self.show.bpm
                frames = render_show(self.show, self.clock.beat())
                await self.driver.send(frames)

                # Sleep the remainder. If a frame overruns we drop the excess
                # rather than piling up late frames -- a late frame is worse
                # than a missing one.
                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.0, interval - elapsed))
        except asyncio.CancelledError:
            pass
        finally:
            await self.driver.blackout()
