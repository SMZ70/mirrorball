"""The core is pure, so these run instantly: no bridge, no lights, no sleeping."""

from __future__ import annotations

import pytest

from mmdj.core.clock import Clock
from mmdj.core.color import lerp_hue
from mmdj.core.engine import render_show
from mmdj.core.patterns import render
from mmdj.core.show import ColorMode, Curve, Palette, Shape, Show, Track


def _track(**kw) -> Track:
    base = dict(id="t1", target="l1", shape=Shape.PULSE, rate=1.0)
    return Track(**{**base, **kw})


# ---------------------------------------------------------------------------
# Determinism -- the property everything else rests on
# ---------------------------------------------------------------------------

def test_same_beat_always_renders_the_same_frame():
    """A show must look the same tonight as it did last week."""
    t = _track(shape=Shape.SPARKLE, seed=7)
    for beat in (0.0, 1.25, 9.75, 133.5):
        assert render(t, beat) == render(t, beat)


def test_nothing_accumulates_over_time():
    """Replaying a beat after thousands of others gives the same frame.

    Every dance in mmhue broke this way: state mutated frame to frame until
    brightness piled up and the contrast washed out. A pure function cannot.
    """
    t = _track(shape=Shape.PULSE)
    first = render(t, 0.25)
    for beat in range(10_000):
        render(t, float(beat))
    assert render(t, 0.25) == first


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------

def test_rate_is_in_beats_so_tempo_changes_move_everything_together():
    """A track at rate=1 is at the same point of its cycle on every beat,
    whatever the bpm. That is why rates are in beats and not seconds."""
    t = _track(rate=1.0, shape=Shape.PULSE, curve=Curve.SINE)
    assert render(t, 3.0).brightness == pytest.approx(render(t, 7.0).brightness)


def test_phase_staggers_tracks_against_each_other():
    """Phase is what makes a wave run around the room."""
    a = _track(id="a", target="l1", phase=0.0, shape=Shape.CHASE, duty=0.5)
    b = _track(id="b", target="l2", phase=0.5, shape=Shape.CHASE, duty=0.5)
    # At beat 0 the first light is on and the second is not
    assert render(a, 0.0).brightness > 0
    assert render(b, 0.0).brightness == 0


def test_half_rate_fires_twice_per_beat():
    t = _track(rate=0.5, shape=Shape.STROBE, duty=0.5)
    on = [render(t, i / 8).brightness > 0 for i in range(8)]   # one beat, 8 steps
    assert on.count(True) == 4                                  # two full cycles


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

def test_hue_interpolates_the_short_way_round():
    """350 -> 10 should cross zero, not travel backwards through the spectrum."""
    assert lerp_hue(350.0, 10.0, 0.5) == pytest.approx(0.0)


def test_palette_confines_a_track_to_its_colour_range():
    """'l1 does golds, l2 does teals.'"""
    t = _track(palette=Palette(hue_from=30, hue_to=50, mode=ColorMode.CYCLE))
    hues = [render(t, i / 20).hue for i in range(20)]
    assert all(29.9 <= h <= 50.1 for h in hues), hues


def test_random_mode_is_random_looking_but_repeatable():
    t = _track(palette=Palette(hue_from=0, hue_to=360, mode=ColorMode.RANDOM), seed=3)
    hues = [render(t, float(c)).hue for c in range(6)]
    assert len(set(hues)) > 1                         # it does vary per cycle
    assert hues == [render(t, float(c)).hue for c in range(6)]   # ...and repeats


# ---------------------------------------------------------------------------
# Show composition
# ---------------------------------------------------------------------------

def test_brightness_never_leaves_the_legal_range():
    for shape in Shape:
        t = _track(shape=shape, bri_min=0, bri_max=100)
        for i in range(64):
            assert 0.0 <= render(t, i / 8).brightness <= 100.0


def test_solo_beats_mute_like_every_mixer_ever_built():
    show = Show(tracks=[
        _track(id="a", target="l1"),
        _track(id="b", target="l2", solo=True),
        _track(id="c", target="l3", mute=True),
    ])
    assert [t.id for t in show.active_tracks()] == ["b"]


def test_blackout_kills_every_light():
    show = Show(blackout=True, tracks=[_track(id="a", target="l1")])
    frames = render_show(show, 1.0)
    assert all(f.brightness == 0 for f in frames.values())


def test_master_brightness_scales_the_whole_show():
    show = Show(tracks=[_track(shape=Shape.SOLID, bri_min=100, bri_max=100)])
    full = render_show(show, 0.0)["l1"].brightness
    show.master.brightness = 0.5
    assert render_show(show, 0.0)["l1"].brightness == pytest.approx(full * 0.5)


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------

def test_tap_tempo_finds_the_bpm():
    clock = Clock()
    for i in range(4):
        clock.tap(now=i * 0.5)          # 120 bpm
    assert clock.bpm == pytest.approx(120.0, abs=0.5)


def test_changing_tempo_does_not_make_the_beat_jump():
    """Tap a new tempo mid-bar and the show speeds up -- it does not lurch."""
    clock = Clock(bpm=120.0, started=0.0)
    before = clock.beat(now=10.0)
    clock.set_bpm(140.0, now=10.0)
    assert clock.beat(now=10.0) == pytest.approx(before)


def test_a_stale_tap_starts_a_new_measurement():
    clock = Clock()
    clock.tap(now=0.0)
    clock.tap(now=60.0)                 # a minute later: not part of the same tempo
    assert len(clock._taps) == 1


def test_a_full_wheel_palette_actually_travels_the_full_wheel():
    """0 -> 360 is the same point on the wheel; shortest-path interpolation
    would sit still. A palette range must travel forwards instead."""
    from mmdj.core.color import hue_in_range

    assert hue_in_range(0, 360, 0.5) == pytest.approx(180.0)
    assert hue_in_range(350, 10, 0.5) == pytest.approx(0.0)     # crosses zero
    assert hue_in_range(30, 50, 0.5) == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def test_every_preset_builds_and_renders_legally():
    """A preset is a recipe, dealt onto whatever lights exist. It must survive
    a room with one light and a room with a dozen, and never render a frame the
    bridge would reject."""
    from mmdj.bridge import Light
    from mmdj.core import presets

    for name in presets.names():
        for count in (1, 6, 12):
            lights = [Light(id=f"l{i}", name=f"L{i}", room="R") for i in range(count)]
            show = presets.build(name, lights)
            assert len(show.tracks) == count, name
            assert 40 <= show.bpm <= 220, name
            for beat in (0.0, 0.37, 1.5, 7.25):
                for frame in render_show(show, beat).values():
                    assert 0.0 <= frame.brightness <= 100.0, (name, beat)
                    assert 0.0 <= frame.hue <= 360.0, (name, beat)


def test_a_preset_spreads_its_lights_around_the_cycle():
    """The 'wave' preset is one voice repeated. If every light got the same
    phase they would all fire at once and there would be no wave."""
    from mmdj.bridge import Light
    from mmdj.core import presets

    lights = [Light(id=f"l{i}", name=f"L{i}", room="R") for i in range(4)]
    phases = [t.phase for t in presets.build("wave", lights).tracks]
    assert len(set(phases)) == 4, phases
