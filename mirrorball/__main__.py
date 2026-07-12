"""Run the panel:  uv run python -m mirrorball"""

from __future__ import annotations

import os

import uvicorn
from loguru import logger

from mirrorball.api.server import Panel, create_app
from mirrorball.core import presets

# What the panel opens with, so it starts on something that plays rather than an
# empty list. It is a preset like any other -- there is no special "starter".
OPENING = os.getenv("MIRRORBALL_OPENING", "party")


def main() -> None:
    panel = Panel(password=os.getenv("MIRRORBALL_PASSWORD", "").strip())
    app = create_app(panel)

    @app.on_event("startup")
    async def _seed() -> None:
        if not panel.show.tracks:
            panel.show = presets.build(OPENING, panel.streamable_lights())
            panel.clock.set_bpm(panel.show.bpm)
            logger.info("opened on the {!r} preset — {} tracks",
                        OPENING, len(panel.show.tracks))

    host = os.getenv("MIRRORBALL_HOST", "0.0.0.0")
    if not panel.password:
        # No password, by request. It only reaches the LAN, and the worst a
        # stranger on your wifi can do is turn the lights funny colours.
        logger.warning("no password set — anyone on the LAN can drive the lights")

    uvicorn.run(app, host=host, port=int(os.getenv("MIRRORBALL_PORT", "8090")),
                log_level="info", access_log=False)


if __name__ == "__main__":
    main()
