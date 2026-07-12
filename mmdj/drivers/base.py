"""The driver boundary.

Everything above this line is pure and knows nothing about Hue. Everything below
it is I/O. The engine asks a driver for its `fps` and sends it frames; it does
not care whether those go out over REST at 10 a second or over a DTLS stream at
50. That is the whole point: the instrument can be built and tuned today on the
slow path, and get fast later without a redesign.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from mmdj.core.patterns import Frame


class Driver(ABC):
    """Where frames go."""

    #: How many frames a second this driver can actually deliver. The engine
    #: paces itself to this, so a driver must be honest about its ceiling --
    #: overrunning it means the bridge silently drops commands, which looks
    #: like a bug in the show and is impossible to debug from the outside.
    fps: float = 10.0

    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def send(self, frames: dict[str, Frame]) -> None:
        """Push one frame. Called `fps` times a second."""

    @abstractmethod
    async def blackout(self) -> None:
        """Leave the lights in a sane state. Called when the engine stops --
        including when it is cancelled, so the room is never stranded."""
