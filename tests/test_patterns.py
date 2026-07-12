"""The core is pure, so these run instantly: no bridge, no lights, no sleeping."""

from __future__ import annotations

import pytest

from mirrorball.core.clock import Clock
from mirrorball.core.color import lerp_hue
from mirrorball.core.engine import render_show
from mirrorball.core.patterns import render
from mirrorball.core.show import ColorMode, Curve, Link, Palette, Shape, Show, Track


def _track(**kw) -> Track:
    base = dict(id="t1", targets=["l1"], shape=Shape.PULSE, rate=1.0)
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

    The effects this replaces broke this way: state mutated frame to frame
    until brightness piled up and the contrast washed out. A pure function
    cannot.
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
    a = _track(id="a", targets=["l1"], phase=0.0, shape=Shape.CHASE, duty=0.5)
    b = _track(id="b", targets=["l2"], phase=0.5, shape=Shape.CHASE, duty=0.5)
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
        _track(id="a", targets=["l1"]),
        _track(id="b", targets=["l2"], solo=True),
        _track(id="c", targets=["l3"], mute=True),
    ])
    assert [t.id for t in show.active_tracks()] == ["b"]


def test_blackout_kills_every_light():
    show = Show(blackout=True, tracks=[_track(id="a", targets=["l1"])])
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
    from mirrorball.core.color import hue_in_range

    assert hue_in_range(0, 360, 0.5) == pytest.approx(180.0)
    assert hue_in_range(350, 10, 0.5) == pytest.approx(0.0)     # crosses zero
    assert hue_in_range(30, 50, 0.5) == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def _lights(count: int):
    from mirrorball.bridge import Light
    return [Light(id=f"l{i}", name=f"L{i}", room="R") for i in range(count)]


def test_every_preset_builds_and_renders_legally():
    """A preset is a recipe, dealt onto whatever lights exist. It must survive a
    room with one light and a room with a dozen, drive every light exactly once,
    and never render a frame the bridge would reject."""
    from mirrorball.core import presets

    for name in presets.names():
        for count in (1, 6, 12):
            lights = _lights(count)
            show = presets.build(name, lights)

            driven = [light for t in show.tracks for light in t.targets]
            assert sorted(driven) == sorted(light.id for light in lights), name
            assert len(driven) == len(set(driven)), f"{name}: a light is driven twice"
            assert 40 <= show.bpm <= 220, name

            for beat in (0.0, 0.37, 1.5, 7.25):
                frames = render_show(show, beat)
                assert len(frames) == count, name
                for frame in frames.values():
                    assert 0.0 <= frame.brightness <= 100.0, (name, beat)
                    assert 0.0 <= frame.hue <= 360.0, (name, beat)


# ---------------------------------------------------------------------------
# Groups and links
# ---------------------------------------------------------------------------

def test_a_group_at_spread_zero_moves_as_one():
    """'all' + spread 0 is what makes the room a single lamp."""
    from mirrorball.core import presets

    show = presets.build("rave", _lights(4))
    assert len(show.tracks) == 1                       # one track, four lights
    assert show.tracks[0].spread == 0.0

    for beat in (0.0, 0.3, 1.7):
        bri = {f.brightness for f in render_show(show, beat).values()}
        assert len(bri) == 1, (beat, bri)              # every light identical


def test_spread_makes_the_same_group_travel():
    """Same layout as `rave`, one number different -- and now it is a wave. If
    spread were ignored the lights would all fire together and there would be
    no wave at all."""
    from mirrorball.core import presets

    show = presets.build("wave", _lights(4))
    assert len(show.tracks) == 1
    assert show.tracks[0].spread == 1.0

    moved = any(
        len({round(f.brightness, 3) for f in render_show(show, beat).values()}) > 1
        for beat in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    assert moved, "spread=1 rendered every light the same: the wave is not travelling"


def test_a_follower_takes_the_leaders_pattern_and_keeps_its_own_place():
    show = Show(tracks=[
        _track(id="a", targets=["l1"], shape=Shape.STROBE, rate=2.0, duty=0.25,
               palette=Palette(hue_from=40, hue_to=40, mode=ColorMode.HOLD)),
        _track(id="b", targets=["l2"], shape=Shape.BREATHE, rate=8.0, level=0.5,
               link=Link(follow="a", rate_scale=2.0, hue_shift=180)),
    ])
    follower = show.effective(show.tracks[1])

    assert follower.shape is Shape.STROBE       # the leader's pattern...
    assert follower.duty == 0.25
    assert follower.rate == 4.0                 # ...at half speed
    assert follower.palette.hue_from == 220.0   # ...in the opposite colour
    assert follower.targets == ["l2"]           # ...but its own lights
    assert follower.level == 0.5                # ...and its own level


def test_invert_makes_a_follower_bright_where_its_leader_is_dark():
    show = Show(tracks=[
        _track(id="a", targets=["l1"], shape=Shape.PULSE, curve=Curve.SINE),
        _track(id="b", targets=["l2"], link=Link(follow="a", invert=True)),
    ])
    for beat in (0.0, 0.25, 0.5, 0.9):
        frames = render_show(show, beat)
        assert frames["l1"].brightness + frames["l2"].brightness == pytest.approx(100.0)


def test_a_link_to_a_track_that_is_not_there_is_just_a_track():
    """Delete the leader and the follower must keep playing, not explode."""
    show = Show(tracks=[_track(id="b", targets=["l2"], link=Link(follow="ghost"))])
    assert show.effective(show.tracks[0]).link is None
    assert render_show(show, 1.0)["l2"].brightness >= 0


def test_linking_cannot_loop():
    """Two tracks following each other must still render. Linking is one level
    deep by construction: a follower takes its leader's OWN pattern, never the
    leader's leader -- so there is no chain to go round."""
    show = Show(tracks=[
        _track(id="a", targets=["l1"], shape=Shape.STROBE, link=Link(follow="b")),
        _track(id="b", targets=["l2"], shape=Shape.CHASE, link=Link(follow="a")),
    ])
    frames = render_show(show, 0.4)              # would hang or recurse if it looped
    assert set(frames) == {"l1", "l2"}


def test_a_v1_show_still_loads():
    """Shows saved before tracks could hold more than one light. They are the
    user's work; the schema's history is not their problem."""
    v1 = ('{"version":1,"name":"old","bpm":120,"tracks":[{"id":"t0","target":"l9",'
          '"shape":"pulse","rate":1.0}]}')
    show = Show.model_validate_json(v1)
    assert show.tracks[0].targets == ["l9"]
    assert render_show(show, 0.5)["l9"].brightness >= 0
