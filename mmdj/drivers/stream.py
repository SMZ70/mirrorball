"""StreamDriver — the Hue Entertainment API, over DTLS.

This is the whole reason the project exists. The REST API accepts about ten
commands a second in total; this streams ~50 frames a second to every light at
once. That is the difference between a slideshow and an instrument.

How it works:
  1. Tell the bridge (over REST) to put an entertainment area into streaming mode.
  2. Open a DTLS socket to :2100, authenticating with a pre-shared key -- the
     `clientkey` the bridge issued at registration.
  3. Fire UDP frames at it. No acknowledgements, no retries: a dropped frame is
     simply the next one arriving 20ms later, which is invisible.

The protocol is a fixed header plus 7 bytes per channel. Colours are 16-bit RGB,
so we get far finer gradations than the REST API ever exposed.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
from dataclasses import dataclass

import aiohttp
from loguru import logger
from mbedtls import tls

from mmdj.core.color import hue_to_rgb
from mmdj.core.patterns import Frame
from mmdj.drivers.base import Driver

STREAM_PORT = 2100
PROTOCOL = b"HueStream"
API_VERSION = bytes([0x02, 0x00])   # Entertainment API v2

# The bridge will accept more, but 50Hz is its documented ceiling and there is
# nothing to gain from outrunning the lights themselves.
DEFAULT_FPS = 50.0


@dataclass(slots=True)
class Channel:
    """One addressable point in an entertainment area."""
    index: int
    light_id: str


class StreamDriver(Driver):
    fps = DEFAULT_FPS

    def __init__(self, host: str, app_key: str, client_key: str,
                 area_id: str, channels: list[Channel], fps: float = DEFAULT_FPS) -> None:
        self.host = host
        self.app_key = app_key
        self.client_key = client_key
        self.area_id = area_id
        self.channels = channels
        self.fps = fps
        self._dtls: tls.DTLSClientContext | None = None
        self._sock = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def open(self) -> None:
        # Release first, then claim. An area can be left stuck in `active` by a
        # streamer that went away (the Hue app, a Sync box, a crashed run of
        # this). The bridge then reports `active` and accepts `start` with a
        # cheerful 200 -- while never opening the UDP port, because as far as it
        # is concerned somebody else already owns the stream. Stopping first is
        # what actually makes it listen.
        await self._set_streaming(False)
        await asyncio.sleep(0.4)
        await self._set_streaming(True)
        # It also needs a moment to start listening; connecting too eagerly gets
        # the handshake refused.
        await asyncio.sleep(0.7)
        await asyncio.get_running_loop().run_in_executor(None, self._connect)
        logger.info("streaming to area {} — {} channels @ {:.0f} fps",
                    self.area_id[:8], len(self.channels), self.fps)

    async def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        await self._set_streaming(False)

    def _connect(self) -> None:
        """DTLS handshake with a pre-shared key. Blocking, so run it off-loop."""
        conf = tls.DTLSConfiguration(
            pre_shared_key=(self.app_key, bytes.fromhex(self.client_key)),
            ciphers=("TLS-PSK-WITH-AES-128-GCM-SHA256",),
            validate_certificates=False,
        )
        ctx = tls.ClientContext(conf)

        sock = ctx.wrap_socket(
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM),
            server_hostname=None,
        )
        sock.connect((self.host, STREAM_PORT))

        # A DTLS handshake is a few round trips and can need re-driving
        for _ in range(30):
            try:
                sock.do_handshake()
                break
            except tls.WantReadError:
                continue
            except tls.WantWriteError:
                continue
        self._sock = sock

    # ── The frame itself ─────────────────────────────────────────────────────

    def _packet(self, frames: dict[str, Frame]) -> bytes:
        out = bytearray()
        out += PROTOCOL
        out += API_VERSION
        out += bytes([0x00])               # sequence id: ignored by the bridge
        out += bytes([0x00, 0x00])         # reserved
        out += bytes([0x00])               # 0 = RGB colour space
        out += bytes([0x00])               # reserved
        out += self.area_id.encode("ascii")

        for ch in self.channels:
            frame = frames.get(ch.light_id)
            if frame is None:
                r = g = b = 0.0
            else:
                rgb = hue_to_rgb(frame.hue, frame.saturation)
                scale = frame.brightness / 100.0
                r, g, b = rgb.r * scale, rgb.g * scale, rgb.b * scale

            out += bytes([ch.index])
            for v in (r, g, b):
                # 16-bit per channel: far finer than REST ever exposed
                out += int(max(0.0, min(1.0, v)) * 0xFFFF).to_bytes(2, "big")

        return bytes(out)

    async def send(self, frames: dict[str, Frame]) -> None:
        if self._sock is None:
            return
        packet = self._packet(frames)
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._sock.send, packet)
        except Exception as exc:                       # a dropped frame is not fatal
            logger.debug("frame dropped: {}", exc)

    async def blackout(self) -> None:
        await self.send({ch.light_id: Frame(0, 0, 0) for ch in self.channels})

    # ── Telling the bridge to listen ─────────────────────────────────────────

    async def _set_streaming(self, on: bool) -> None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        url = f"https://{self.host}/clip/v2/resource/entertainment_configuration/{self.area_id}"
        body = {"action": "start" if on else "stop"}

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ctx),
            headers={"hue-application-key": self.app_key},
        ) as session:
            async with session.put(url, json=body) as resp:
                data = await resp.json()
                if data.get("errors"):
                    logger.warning("bridge refused {}: {}",
                                   "start" if on else "stop", data["errors"])
