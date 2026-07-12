"""Talking to the bridge over REST — only to find out what exists.

Once the show is running, frames go over the stream and this is not used. All it
does is answer "what lights are there, what are they called, and which
entertainment area can we drive them from".
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from loguru import logger

from mirrorball.drivers.stream import Channel

CREDENTIALS = Path("bridge.json")


@dataclass(frozen=True, slots=True)
class Light:
    id: str
    name: str
    room: str


@dataclass(frozen=True, slots=True)
class Area:
    """An entertainment area: the set of lights we can actually stream to."""
    id: str
    name: str
    channels: list[Channel]
    lights: list[Light]


@dataclass(frozen=True, slots=True)
class Credentials:
    host: str
    app_key: str
    client_key: str

    @classmethod
    def load(cls, path: Path = CREDENTIALS) -> Credentials:
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found — run: uv run python scripts/register_bridge.py <bridge-ip>"
            )
        return cls(**json.loads(path.read_text()))


def _ssl_context() -> ssl.SSLContext:
    # The bridge presents a self-signed certificate for its own IP. Verifying it
    # would fail on principle and buy nothing on a LAN we already trust.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def _get(session: aiohttp.ClientSession, host: str, resource: str) -> list[dict]:
    async with session.get(f"https://{host}/clip/v2/resource/{resource}") as resp:
        return (await resp.json()).get("data", [])


async def discover(creds: Credentials) -> tuple[list[Light], list[Area]]:
    """Everything the panel needs to know about the installation."""
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=_ssl_context()),
        headers={"hue-application-key": creds.app_key},
    ) as session:
        devices = await _get(session, creds.host, "device")
        rooms = await _get(session, creds.host, "room")
        areas_raw = await _get(session, creds.host, "entertainment_configuration")

    # A device exposes several services. The bit that trips you up: an
    # entertainment *channel* points at the device's `entertainment` service,
    # not its `light` service -- different ids for the same bulb. Without this
    # mapping, tracks keyed by light id would address nothing and the show would
    # render perfectly into the void.
    name_of: dict[str, str] = {}
    device_of_light: dict[str, str] = {}
    light_of_entertainment: dict[str, str] = {}

    for dev in devices:
        light_rid = None
        ent_rid = None
        for svc in dev.get("services", []):
            if svc["rtype"] == "light":
                light_rid = svc["rid"]
            elif svc["rtype"] == "entertainment":
                ent_rid = svc["rid"]

        if light_rid:
            name_of[light_rid] = dev["metadata"]["name"]
            device_of_light[light_rid] = dev["id"]
            if ent_rid:
                light_of_entertainment[ent_rid] = light_rid

    # device id -> room name
    room_of_device: dict[str, str] = {}
    for room in rooms:
        for child in room.get("children", []):
            room_of_device[child["rid"]] = room["metadata"]["name"]

    lights = [
        Light(
            id=lid,
            name=name_of[lid],
            room=room_of_device.get(device_of_light[lid], ""),
        )
        for lid in name_of
    ]

    by_id = {light.id: light for light in lights}

    areas: list[Area] = []
    for raw in areas_raw:
        channels, members = [], []
        for ch in raw.get("channels", []):
            if not ch.get("members"):
                continue
            ent_rid = ch["members"][0]["service"]["rid"]
            light_id = light_of_entertainment.get(ent_rid)
            if light_id is None:
                logger.warning("channel {} maps to no light; skipping", ch["channel_id"])
                continue
            # Keyed by LIGHT id, so a track targeting a light lands on the right
            # channel.
            channels.append(Channel(index=ch["channel_id"], light_id=light_id))
            members.append(by_id[light_id])
        if channels:
            areas.append(Area(raw["id"], raw["metadata"]["name"], channels, members))

    logger.info("bridge: {} lights, {} entertainment areas", len(lights), len(areas))
    return lights, areas
