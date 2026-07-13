"""The playground: a rig that exists only on screen.

WHY THIS IS A SEPARATE OBJECT AND NOT A FLAG

The live panel works, and it drives real lights in someone's home. So the
playground is built so that it *cannot* disturb it, rather than merely being
careful not to:

  * It owns its own Show, its own Clock and its own lights. Nothing it does can
    reach `panel.show` or `panel.engine`.
  * It has NO DRIVER. It never constructs a StreamDriver, so it cannot open the
    DTLS socket, cannot claim the entertainment area, and cannot move a bulb --
    even if the code below is wrong.
  * Its messages live in their own `pg.*` namespace, handled by a function that
    is never given the live show. A playground edit cannot be mistaken for a
    live one by a typo.

What it DOES share is `render_show`. That is deliberate and is the whole value:
the preview is produced by the exact code that drives the lights, so what you
see on screen is what the room will actually do. A second renderer written in
JavaScript would look right and then drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mirrorball.bridge import Light
from mirrorball.core.clock import Clock
from mirrorball.core.engine import render_show
from mirrorball.core.presets import build
from mirrorball.core.show import Show

# A virtual rig can be bigger than any real one -- that is half the point. But
# it still has to be drawable on a phone.
MIN_VIRTUAL = 1
MAX_VIRTUAL = 24
DEFAULT_VIRTUAL = 8

PREVIEW_HZ = 25.0     # smooth enough to read a strobe; a tenth of the light rate


def virtual_rig(count: int) -> list[Light]:
    """Invented lights. Ids are deliberately unlike bridge ids (`v0`, not a uuid)
    so a virtual show can never be mistaken for one that drives a real room."""
    count = max(MIN_VIRTUAL, min(MAX_VIRTUAL, count))
    return [Light(id=f"v{i}", name=f"Lamp {i + 1}", room="Virtual rig")
            for i in range(count)]


@dataclass
class Playground:
    """A show, a clock, and a set of lights that do not exist."""

    rig: str = "real"                       # "real" mirrors your bridge; "virtual" invents
    count: int = DEFAULT_VIRTUAL            # how many lights, when virtual
    running: bool = False
    show: Show = field(default_factory=lambda: Show(name="playground"))
    clock: Clock = field(default_factory=Clock)
    _virtual: list[Light] = field(default_factory=list)

    def lights(self, real: list[Light]) -> list[Light]:
        """The rig we are playing on.

        "real" hands back your actual lights -- same ids -- so a show you build
        here is one you can genuinely play later. "virtual" invents a rig, which
        lets you design for a room you do not have.
        """
        if self.rig == "real":
            return list(real)
        if len(self._virtual) != self.count:
            self._virtual = virtual_rig(self.count)
        return self._virtual

    def set_rig(self, rig: str, count: int, real: list[Light]) -> None:
        """Switch rigs, and re-deal the show onto the lights that now exist.

        Without the re-deal the tracks would still name the old rig's lights and
        the stage would sit dark -- which is exactly the "my groups don't play"
        confusion we have already been bitten by once.
        """
        self.rig = "virtual" if rig == "virtual" else "real"
        self.count = max(MIN_VIRTUAL, min(MAX_VIRTUAL, int(count)))
        self._virtual = []
        self.adopt(build("party", self.lights(real)))

    def adopt(self, show: Show) -> None:
        self.show = show
        self.clock.set_bpm(show.bpm)

    def preview(self) -> dict:
        """One frame of the stage. Rendered by the engine's own code."""
        frames = render_show(self.show, self.clock.beat())
        return {
            "type": "preview",
            "beat": round(self.clock.beat(), 3),
            "frames": {
                lid: {
                    "hue": round(f.hue, 1),
                    "sat": round(f.saturation, 3),
                    "bri": round(f.brightness, 1),
                }
                for lid, f in frames.items()
            },
        }

    def state(self, real: list[Light]) -> dict:
        return {
            "rig": self.rig,
            "count": self.count,
            "running": self.running,
            "show": self.show.model_dump(),
            "bpm": round(self.clock.bpm, 1),
            "max": MAX_VIRTUAL,
            # A virtual show names lights that do not exist, so it must not be
            # saved into the same drawer as shows meant for the real room.
            "savable": self.rig == "real",
            "lights": [
                {"id": light.id, "name": light.name, "room": light.room}
                for light in self.lights(real)
            ],
        }
