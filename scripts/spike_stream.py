"""SPIKE: does Entertainment streaming actually deliver on this bridge?

Everything in PLAN.md rests on this. If the stream is not genuinely smooth, the
whole design changes, so it gets answered before a single button is drawn.

    uv run python scripts/spike_stream.py

Watch the lights. You should see:
  1. a slow, SMOOTH fade through the spectrum   (impossible over REST)
  2. a hard strobe at 8Hz                       (impossible over REST)
  3. a wave running light to light              (the chase)
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from pathlib import Path

import aiohttp

from mmdj.core.color import hue_to_rgb  # noqa: F401  (proves the import graph)
from mmdj.core.patterns import Frame
from mmdj.drivers.stream import Channel, StreamDriver

CREDS = Path(__file__).parent.parent / "bridge.json"


async def entertainment_area(host: str, app_key: str) -> tuple[str, list[Channel]]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"https://{host}/clip/v2/resource/entertainment_configuration"
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ctx),
        headers={"hue-application-key": app_key},
    ) as session:
        async with session.get(url) as resp:
            areas = (await resp.json())["data"]

    # Take the area with the most channels: the most lights to play with
    area = max(areas, key=lambda a: len(a["channels"]))
    channels = [
        Channel(index=c["channel_id"], light_id=c["members"][0]["service"]["rid"])
        for c in area["channels"]
    ]
    print(f"area: {area['metadata']['name']!r}  channels: {len(channels)}")
    return area["id"], channels


async def main() -> None:
    creds = json.loads(CREDS.read_text())
    area_id, channels = await entertainment_area(creds["host"], creds["app_key"])

    driver = StreamDriver(
        host=creds["host"],
        app_key=creds["app_key"],
        client_key=creds["client_key"],
        area_id=area_id,
        channels=channels,
    )

    await driver.open()
    sent = 0
    t0 = time.monotonic()

    try:
        # 1 — a smooth spectrum fade. Over REST this stutters; it should not here.
        print("\n1/3  smooth fade through the spectrum (8s)")
        while (t := time.monotonic() - t0) < 8:
            hue = (t / 8) * 360
            await driver.send({c.light_id: Frame(hue, 1.0, 80) for c in channels})
            sent += 1
            await asyncio.sleep(1 / driver.fps)

        # 2 — a hard strobe. The REST API physically cannot do this.
        print("2/3  hard strobe at 8Hz (4s)")
        t1 = time.monotonic()
        while (t := time.monotonic() - t1) < 4:
            on = int(t * 16) % 2 == 0
            await driver.send({c.light_id: Frame(300, 1.0, 100 if on else 0)
                               for c in channels})
            sent += 1
            await asyncio.sleep(1 / driver.fps)

        # 3 — a wave running around the room
        print("3/3  chase (6s)")
        t2 = time.monotonic()
        while (t := time.monotonic() - t2) < 6:
            head = (t * 2) % len(channels)
            frames = {}
            for i, c in enumerate(channels):
                d = min(abs(i - head), len(channels) - abs(i - head))
                frames[c.light_id] = Frame(45, 1.0, max(0.0, 100 * (1 - d)))
            await driver.send(frames)
            sent += 1
            await asyncio.sleep(1 / driver.fps)

    finally:
        elapsed = time.monotonic() - t0
        await driver.blackout()
        await driver.close()

    print(f"\nsent {sent} frames in {elapsed:.1f}s = {sent / elapsed:.1f} fps")
    print("REST tops out around 10 COMMANDS/sec, shared across all lights.")


if __name__ == "__main__":
    asyncio.run(main())
