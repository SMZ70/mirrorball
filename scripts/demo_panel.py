"""Run the panel with no bridge at all: fake lights, a driver that goes nowhere.

    uv run python scripts/demo_panel.py

Everything above the driver boundary is real -- the same server, the same show,
the same engine, the same page. Only the lights are imaginary. Useful for working
on the panel on a train, and it is what the README's screenshots are taken
against, so no real light names or room names end up in the repo.
"""

from __future__ import annotations

import os

import uvicorn

from mirrorball.api.server import Panel, create_app
from mirrorball.bridge import Area, Light
from mirrorball.core import presets
from mirrorball.core.patterns import Frame
from mirrorball.drivers.base import Driver
from mirrorball.drivers.stream import Channel

# Deliberately generic: a demo should not describe somebody's actual home.
LIGHTS = [
    Light(id=f"light-{i}", name=name, room=room)
    for i, (name, room) in enumerate([
        ("Ceiling", "Lounge"),
        ("Sofa", "Lounge"),
        ("Shelf", "Lounge"),
        ("Counter", "Kitchen"),
        ("Table", "Kitchen"),
        ("Desk", "Study"),
    ])
]


class NullDriver(Driver):
    """Accepts frames and drops them. The clock still runs, so the panel behaves
    exactly as it does with lights attached -- it just has nothing to light."""

    fps = 50.0

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def send(self, frames: dict[str, Frame]) -> None: ...
    async def blackout(self) -> None: ...


class DemoPanel(Panel):
    async def connect_bridge(self) -> None:
        channels = [Channel(index=i, light_id=lit.id) for i, lit in enumerate(LIGHTS)]
        self.areas = [Area(id="demo", name="Demo room", channels=channels, lights=LIGHTS)]
        self.lights = LIGHTS
        self.area_index = 0

    def _driver(self) -> Driver:  # type: ignore[override]
        return NullDriver()


def main() -> None:
    panel = DemoPanel()
    app = create_app(panel)

    @app.on_event("startup")
    async def _seed() -> None:
        panel.show = presets.build(os.getenv("MIRRORBALL_OPENING", "party"),
                                   panel.streamable_lights())
        panel.clock.set_bpm(panel.show.bpm)

    uvicorn.run(app, host=os.getenv("MIRRORBALL_HOST", "127.0.0.1"),
                port=int(os.getenv("MIRRORBALL_PORT", "8091")),
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
