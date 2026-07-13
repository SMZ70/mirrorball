"""The playground, and the one thing it must never do: touch the room.

The live panel drives real lights in someone's home and it works. These tests
exist to pin the isolation, not the features -- a playground that is merely
"careful" not to reach the lights is one refactor away from reaching them.
"""

from __future__ import annotations

import asyncio

import pytest

from mirrorball.api.playground import Playground, virtual_rig
from mirrorball.api.server import Panel, handle
from mirrorball.bridge import Light
from mirrorball.core.presets import build
from mirrorball.core.show import Show, Track

REAL = [
    Light(id="real-a", name="TV Light", room="Living room"),
    Light(id="real-b", name="Dining light", room="Dining"),
]


def a_panel() -> Panel:
    panel = Panel()
    panel.lights = list(REAL)
    panel.show = build("party", REAL)
    panel.show.name = "the real one"
    # No bridge in a test, so pin the lights the panel thinks it can stream to.
    panel.streamable_lights = lambda: list(REAL)   # type: ignore[method-assign]
    return panel


def send(panel: Panel, msg: dict) -> None:
    asyncio.run(handle(panel, msg))


# ── Isolation ───────────────────────────────────────────────────────────────

def test_a_playground_edit_never_reaches_the_live_show():
    panel = a_panel()
    before = panel.show.model_dump()

    send(panel, {"type": "pg.show", "show": Show(name="sandbox", bpm=200).model_dump()})
    send(panel, {"type": "pg.rig", "rig": "virtual", "count": 12})
    send(panel, {"type": "pg.preset", "name": "rave"})
    send(panel, {"type": "pg.blackout", "on": True})
    send(panel, {"type": "pg.play", "on": True})

    assert panel.show.model_dump() == before, "the live show must be untouched"
    assert panel.engine is None, "the playground must never start the engine"


def test_the_playground_has_no_driver_and_so_cannot_reach_the_bridge():
    """The strongest guarantee here is structural: there is nowhere for a frame
    to go. Playing the playground starts no engine and opens no socket."""
    panel = a_panel()
    send(panel, {"type": "pg.play", "on": True})

    assert panel.playground.running is True
    assert panel.engine is None
    assert not hasattr(panel.playground, "driver")
    # It renders frames, and hands them to whoever asked -- the screen.
    send(panel, {"type": "pg.preset", "name": "party"})
    preview = panel.playground.preview()
    assert preview["type"] == "preview"
    assert set(preview["frames"]) == {"real-a", "real-b"}


def test_a_live_edit_never_reaches_the_playground():
    panel = a_panel()
    send(panel, {"type": "pg.rig", "rig": "virtual", "count": 5})
    sandbox = panel.playground.show.model_dump()

    send(panel, {"type": "show", "show": Show(name="live", bpm=99).model_dump()})

    assert panel.playground.show.model_dump() == sandbox
    assert panel.show.name == "live"


# ── The rig ─────────────────────────────────────────────────────────────────

def test_the_real_rig_mirrors_your_actual_lights():
    """Same ids as the room, so a show designed here is one you can really play."""
    pg = Playground()
    assert [light.id for light in pg.lights(REAL)] == ["real-a", "real-b"]


def test_a_virtual_rig_invents_lights_that_cannot_be_confused_with_real_ones():
    pg = Playground()
    pg.set_rig("virtual", 10, REAL)
    ids = [light.id for light in pg.lights(REAL)]
    assert ids == [f"v{i}" for i in range(10)]
    assert not any(i in ids for i in ("real-a", "real-b"))


def test_a_virtual_rig_is_clamped_to_something_drawable():
    assert len(virtual_rig(0)) == 1
    assert len(virtual_rig(999)) == 24


def test_switching_rigs_re_deals_the_show_onto_the_lights_that_now_exist():
    """Otherwise the tracks name lights that are gone and the stage sits dark --
    the same silent failure as a show recalled with a latched solo."""
    panel = a_panel()
    send(panel, {"type": "pg.rig", "rig": "virtual", "count": 4})

    pg = panel.playground
    targets = {t for track in pg.show.tracks for t in track.targets}
    assert targets == {"v0", "v1", "v2", "v3"}
    assert set(pg.preview()["frames"]) == targets, "every lamp on the stage is lit"

    send(panel, {"type": "pg.rig", "rig": "real"})
    targets = {t for track in pg.show.tracks for t in track.targets}
    assert targets == {"real-a", "real-b"}


# ── Saving ──────────────────────────────────────────────────────────────────

def test_a_virtual_show_is_refused_at_the_door(tmp_path, monkeypatch):
    """It names lights that do not exist. Saved, it would load fine and then
    light nothing -- so it never gets into the drawer in the first place."""
    from mirrorball.core import store

    monkeypatch.chdir(tmp_path)          # SHOWS_DIR is relative; chdir isolates it
    panel = a_panel()
    send(panel, {"type": "pg.rig", "rig": "virtual", "count": 3})
    send(panel, {"type": "pg.save", "name": "nope"})

    assert store.names() == []
    assert panel.playground.state(REAL)["savable"] is False


def test_a_show_built_on_your_real_lights_can_be_saved_and_played_for_real(tmp_path,
                                                                          monkeypatch):
    from mirrorball.core import store

    monkeypatch.chdir(tmp_path)
    panel = a_panel()
    send(panel, {"type": "pg.preset", "name": "wave"})
    send(panel, {"type": "pg.save", "name": "from the playground"})

    assert store.names() == ["from the playground"]
    saved = store.load("from the playground")
    targets = {t for track in saved.tracks for t in track.targets}
    assert targets <= {"real-a", "real-b"}, "it names real lights, so it will play"


@pytest.mark.parametrize("kind", ["show", "play", "preset", "save", "load", "blackout"])
def test_every_live_message_has_a_playground_twin(kind):
    """If a message exists live and not in the sandbox, the panel would silently
    fall back to the live namespace -- which is exactly the accident this whole
    design exists to prevent."""
    import inspect

    from mirrorball.api import server

    source = inspect.getsource(server.handle_playground)
    assert f'case "pg.{kind}"' in source


def test_the_preview_is_rendered_by_the_engines_own_code():
    """Not a second renderer written in JavaScript -- that would look right and
    then drift. Same show, same beat, same numbers."""
    from mirrorball.core.engine import render_show

    pg = Playground()
    pg.show = Show(name="x", tracks=[Track(id="t0", targets=["real-a"])])
    pg.clock.set_bpm(120)

    beat = pg.clock.beat()
    expected = render_show(pg.show, beat)
    got = pg.preview()["frames"]["real-a"]

    assert got["bri"] == pytest.approx(expected["real-a"].brightness, abs=0.6)
