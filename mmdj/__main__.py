"""Run the panel:  uv run python -m mmdj"""

from __future__ import annotations

import os

import uvicorn
from loguru import logger

from mmdj.api.server import Panel, create_app
from mmdj.core.show import ColorMode, Curve, Palette, Shape, Show, Track

# A house-warming show, so the panel opens with something that plays rather than
# an empty list. Each light gets a different pattern -- which is the whole point.
STARTERS = [
    dict(shape=Shape.PULSE,   curve=Curve.SINE, rate=1.0,  hue=(30, 55)),
    dict(shape=Shape.CHASE,   curve=Curve.FALL, rate=1.0,  hue=(320, 350)),
    dict(shape=Shape.STROBE,  curve=Curve.SQUARE, rate=0.5, hue=(180, 200)),
    dict(shape=Shape.BREATHE, curve=Curve.SINE, rate=4.0,  hue=(265, 290)),
    dict(shape=Shape.SPARKLE, curve=Curve.FALL, rate=0.5,  hue=(45, 60)),
    dict(shape=Shape.SWEEP,   curve=Curve.SINE, rate=8.0,  hue=(0, 360)),
]


def starter_show(panel: Panel) -> Show:
    tracks = []
    lights = panel.streamable_lights()
    for i, light in enumerate(lights):
        spec = STARTERS[i % len(STARTERS)]
        lo, hi = spec["hue"]
        tracks.append(Track(
            id=f"t{i}",
            target=light.id,
            name=light.name,
            shape=spec["shape"],
            curve=spec["curve"],
            rate=spec["rate"],
            # Stagger the phase so a chase actually travels rather than firing
            # every light at once.
            phase=(i / max(len(lights), 1)) % 1.0,
            palette=Palette(hue_from=lo, hue_to=hi, mode=ColorMode.CYCLE),
            bri_min=8, bri_max=100,
            seed=i,
        ))
    return Show(name="starter", bpm=120, tracks=tracks)


def main() -> None:
    panel = Panel(password=os.getenv("MMDJ_PASSWORD", "").strip())
    app = create_app(panel)

    @app.on_event("startup")
    async def _seed() -> None:
        if not panel.show.tracks:
            panel.show = starter_show(panel)
            logger.info("seeded a starter show with {} tracks", len(panel.show.tracks))

    host = os.getenv("MMDJ_HOST", "0.0.0.0")
    if not panel.password and host != "127.0.0.1":
        logger.warning("MMDJ_PASSWORD is not set — binding to localhost only")
        host = "127.0.0.1"

    uvicorn.run(app, host=host, port=int(os.getenv("MMDJ_PORT", "8090")),
                log_level="info", access_log=False)


if __name__ == "__main__":
    main()
