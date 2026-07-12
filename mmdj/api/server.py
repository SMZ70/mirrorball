"""The API: a WebSocket, and a page to serve.

The panel never talks to lights. It edits the Show and sends it here; the engine
renders it. That is the whole protocol, and it is why the frontend is disposable
-- a native app later is a new view over the same socket, not a rewrite.

WebSocket in, from the panel:
    {"type": "show",     "show": {...}}    the whole Show (it is a few KB)
    {"type": "tap"}                        tap tempo
    {"type": "resync"}                     drop back onto the downbeat
    {"type": "blackout", "on": true}
    {"type": "play",     "on": true}
    {"type": "save",     "name": "..."}
    {"type": "load",     "name": "..."}

WebSocket out, to the panel:
    {"type": "state", "show": {...}, "playing": true, "beat": 12.5, "shows": [...]}

Sending the whole Show rather than a patch is a deliberate simplification: it is
small, it cannot desync, and there is no merge logic to get subtly wrong. If it
ever gets big enough to matter, that is the moment to add patches -- not before.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

from mmdj.bridge import Area, Credentials, Light, discover
from mmdj.core import presets, store
from mmdj.core.clock import Clock
from mmdj.core.engine import Engine
from mmdj.core.show import Show
from mmdj.drivers.stream import StreamDriver

WEB = Path(__file__).parent.parent.parent / "web"
BROADCAST_HZ = 10.0        # UI refresh; the lights render at 50


class Panel:
    """Everything the server owns: the show, the engine, the connected panels."""

    def __init__(self, password: str = "") -> None:
        self.password = password
        self.show = Show(name="untitled")
        self.clock = Clock()
        self.engine: Engine | None = None
        self.lights: list[Light] = []
        self.areas: list[Area] = []
        self.area_index = 0
        self._clients: set[WebSocket] = set()

    # ── Bridge ───────────────────────────────────────────────────────────────

    async def connect_bridge(self) -> None:
        creds = Credentials.load()
        self.lights, self.areas = await discover(creds)
        if not self.areas:
            raise RuntimeError("no entertainment areas on this bridge")
        # Default to the area with the most lights: the biggest instrument
        self.area_index = max(range(len(self.areas)),
                              key=lambda i: len(self.areas[i].channels))
        self.creds = creds

    def _driver(self) -> StreamDriver:
        area = self.areas[self.area_index]
        return StreamDriver(
            host=self.creds.host,
            app_key=self.creds.app_key,
            client_key=self.creds.client_key,
            area_id=area.id,
            channels=area.channels,
        )

    # ── Transport ────────────────────────────────────────────────────────────

    @property
    def playing(self) -> bool:
        return bool(self.engine and self.engine.running)

    async def play(self) -> None:
        if self.playing:
            return
        self.engine = Engine(self.show, self._driver(), self.clock)
        await self.engine.start()

    async def stop(self) -> None:
        if self.engine:
            await self.engine.stop()
            self.engine = None
        # Hand the lights back: while we stream, the bridge gives us exclusive
        # ownership and mmhue/the bot cannot touch them. Stopping must release
        # them, or the rest of the house silently stops working.
        logger.info("stopped; lights released back to the bridge")

    # ── Panels ───────────────────────────────────────────────────────────────

    def state(self) -> dict:
        return {
            "type": "state",
            "show": self.show.model_dump(),
            "playing": self.playing,
            "beat": round(self.clock.beat(), 3),
            "bpm": round(self.clock.bpm, 1),
            "shows": store.names(),
            "presets": presets.info(),
            "lights": [
                {"id": light.id, "name": light.name, "room": light.room}
                for light in self.streamable_lights()
            ],
            "area": self.areas[self.area_index].name if self.areas else "",
        }

    def streamable_lights(self) -> list[Light]:
        """Only the lights in the current entertainment area can be streamed to.
        Offering the others in the UI would be a lie."""
        return self.areas[self.area_index].lights if self.areas else []

    async def broadcast(self) -> None:
        if not self._clients:
            return
        state = self.state()
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(state)
            except Exception:
                dead.add(ws)
        self._clients -= dead


def create_app(panel: Panel) -> FastAPI:
    app = FastAPI(title="mmdj", docs_url=None, redoc_url=None)
    security = HTTPBasic(auto_error=bool(panel.password))

    def auth(creds: HTTPBasicCredentials | None = Depends(security)) -> None:  # noqa: B008
        if not panel.password:
            return
        if not creds or not secrets.compare_digest(creds.password, panel.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password",
                                headers={"WWW-Authenticate": "Basic"})

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.get("/app.js")
    async def script() -> FileResponse:
        return FileResponse(WEB / "app.js")

    @app.get("/manifest.json")
    async def manifest() -> FileResponse:
        return FileResponse(WEB / "manifest.json")

    pump: list[asyncio.Task] = []

    @app.on_event("startup")
    async def _startup() -> None:
        await panel.connect_bridge()
        pump.append(asyncio.create_task(_pump()))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # Cancel the pump explicitly. It loops forever, so without this the
        # server hangs on "waiting for background tasks" and never exits.
        for task in pump:
            task.cancel()
        await panel.stop()

    async def _pump() -> None:
        """Push state to the panels on a timer. The lights do not wait for this
        -- they are rendered by the engine at 50fps regardless."""
        while True:
            await panel.broadcast()
            await asyncio.sleep(1 / BROADCAST_HZ)

    @app.websocket("/ws")
    async def socket(ws: WebSocket) -> None:
        await ws.accept()
        panel._clients.add(ws)
        await ws.send_json(panel.state())
        try:
            while True:
                msg = await ws.receive_json()
                await handle(panel, msg)
                await panel.broadcast()
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("panel error: {}", exc)
        finally:
            panel._clients.discard(ws)

    return app


async def handle(panel: Panel, msg: dict) -> None:
    match msg.get("type"):
        case "show":
            panel.show = Show.model_validate(msg["show"])
            panel.clock.set_bpm(panel.show.bpm)
            if panel.engine:
                panel.engine.show = panel.show     # live: no restart, no gap
        case "tap":
            bpm = panel.clock.tap()
            if bpm:
                panel.show.bpm = round(bpm, 1)
        case "resync":
            panel.clock.resync()
        case "blackout":
            panel.show.blackout = bool(msg.get("on"))
        case "play":
            await (panel.play() if msg.get("on") else panel.stop())
        case "save":
            panel.show.name = msg.get("name") or panel.show.name
            store.save(panel.show)
        case "load":
            _adopt(panel, store.load(msg["name"]))
        case "preset":
            name = msg.get("name", "")
            if name not in presets.PRESETS:
                logger.warning("no such preset: {!r}", name)
                return
            # Built fresh against the lights we have now, not loaded from disk:
            # a preset is a recipe, and the room may have changed since.
            _adopt(panel, presets.build(name, panel.streamable_lights()))
        case _:
            logger.debug("ignoring {}", msg)


def _adopt(panel: Panel, show: Show) -> None:
    """Swap the show under a running engine, without a gap in the lights."""
    panel.show = show
    panel.clock.set_bpm(show.bpm)
    if panel.engine:
        panel.engine.show = show
    logger.info("loaded {!r} — {} tracks @ {} bpm", show.name, len(show.tracks), show.bpm)
