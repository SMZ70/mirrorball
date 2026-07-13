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

The playground has its own namespace, and its own handler:
    {"type": "pg.show" | "pg.play" | "pg.rig" | "pg.preset" | "pg.save" | ...}

That is not decoration. The playground must never be able to touch the live show
or the lights, and a separate namespace makes that a property of the wiring
rather than of everyone remembering to be careful.

WebSocket out, to the panel:
    {"type": "state",   "show": {...}, "playing": true, "beat": 12.5, "pg": {...}}
    {"type": "preview", "beat": 3.2, "frames": {"<light id>": {hue, sat, bri}}}

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

from mirrorball.api.playground import PREVIEW_HZ, Playground
from mirrorball.bridge import Area, Credentials, Light, discover
from mirrorball.core import presets, store
from mirrorball.core.clock import Clock
from mirrorball.core.engine import Engine
from mirrorball.core.show import Show
from mirrorball.drivers.stream import StreamDriver

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
        # A sandbox with no driver. It cannot reach the engine or the bridge.
        self.playground = Playground()

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
        # ownership and nothing else -- the Hue app, your automations -- can
        # touch them. Stopping must release them, or the rest of your lighting
        # silently stops working.
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
            "pg": self.playground.state(self.streamable_lights()),
        }

    def streamable_lights(self) -> list[Light]:
        """Only the lights in the current entertainment area can be streamed to.
        Offering the others in the UI would be a lie."""
        return self.areas[self.area_index].lights if self.areas else []

    async def broadcast(self) -> None:
        await self.send_all(self.state())

    async def send_all(self, payload: dict) -> None:
        if not self._clients:
            return
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead


def create_app(panel: Panel) -> FastAPI:
    app = FastAPI(title="mirrorball", docs_url=None, redoc_url=None)
    security = HTTPBasic(auto_error=bool(panel.password))

    def auth(creds: HTTPBasicCredentials | None = Depends(security)) -> None:  # noqa: B008
        if not panel.password:
            return
        if not creds or not secrets.compare_digest(creds.password, panel.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password",
                                headers={"WWW-Authenticate": "Basic"})

    # The page and the script must always be the ones on disk.
    #
    # This bit us: a deploy shipped a new index.html and the browser refetched it
    # (it is a navigation), but reused a CACHED app.js -- so the new page called
    # into old code. The Playground button rendered, and did nothing at all when
    # tapped, because the function behind it did not exist yet. Nothing in the
    # logs, nothing on screen. There is no build step here to hash filenames with,
    # so the honest fix is to tell the browser not to keep them.
    FRESH = {"Cache-Control": "no-store, must-revalidate"}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html", headers=FRESH)

    @app.get("/app.js")
    async def script() -> FileResponse:
        return FileResponse(WEB / "app.js", headers=FRESH)

    @app.get("/manifest.json")
    async def manifest() -> FileResponse:
        return FileResponse(WEB / "manifest.json")

    pump: list[asyncio.Task] = []

    @app.on_event("startup")
    async def _startup() -> None:
        await panel.connect_bridge()
        pump.append(asyncio.create_task(_pump()))
        pump.append(asyncio.create_task(_preview_pump()))

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

    async def _preview_pump() -> None:
        """Frames for the playground stage, and nothing else.

        Its own loop, faster than the state pump: the whole Show is a few kB and
        does not need to go out 25 times a second, but a strobe does. It sends
        nothing at all unless someone is actually looking at the playground.
        """
        while True:
            pg = panel.playground
            if pg.running and panel._clients:
                await panel.send_all(pg.preview())
            await asyncio.sleep(1 / PREVIEW_HZ)

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


async def handle_playground(pg: Playground, lights: list[Light], msg: dict) -> None:
    """Playground messages. Note what this function is NOT given: the live show,
    the engine, or a driver. It could not disturb the room if it tried."""
    match msg.get("type"):
        case "pg.show":
            pg.show = Show.model_validate(msg["show"])
            pg.clock.set_bpm(pg.show.bpm)
        case "pg.play":
            pg.running = bool(msg.get("on"))
        case "pg.tap":
            bpm = pg.clock.tap()
            if bpm:
                pg.show.bpm = round(bpm, 1)
        case "pg.resync":
            pg.clock.resync()
        case "pg.blackout":
            pg.show.blackout = bool(msg.get("on"))
        case "pg.rig":
            pg.set_rig(msg.get("rig", "real"), msg.get("count", pg.count), lights)
        case "pg.preset":
            name = msg.get("name", "")
            if name in presets.PRESETS:
                pg.adopt(presets.build(name, pg.lights(lights)))
        case "pg.load":
            pg.adopt(store.load(msg["name"]))
        case "pg.save":
            # A virtual show names lights that do not exist. Saving it into the
            # same drawer as real shows would hand you a show that loads fine and
            # then lights nothing -- so it is refused at the door.
            if pg.rig != "real":
                logger.warning("refusing to save a virtual-rig show")
                return
            pg.show.name = msg.get("name") or pg.show.name
            store.save(pg.show)
        case _:
            logger.debug("ignoring playground {}", msg)


async def handle(panel: Panel, msg: dict) -> None:
    kind = msg.get("type", "")
    if isinstance(kind, str) and kind.startswith("pg."):
        await handle_playground(panel.playground, panel.streamable_lights(), msg)
        return

    match kind:
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
