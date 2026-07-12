"""Patterns: pure functions of the beat.

    render(track, beat, energy) -> Frame

No state. No I/O. No mutation between calls. Given the same beat you get the
same frame, always.

That is not purism -- it is the fix for a specific class of bug. The dances in
mmhue mutated state frame to frame and every one of them broke the same way:
brightness accumulated until the contrast washed out; lights were left stranded
lit when a dance was cancelled; a restore captured the room mid-strobe. None of
those can happen here, because there is nothing to accumulate.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from mmdj.core.color import clamp01, hue_in_range, lerp
from mmdj.core.show import ColorMode, Curve, Shape, Track


@dataclass(frozen=True, slots=True)
class Frame:
    """What one track wants its light to be doing, right now."""
    hue: float          # degrees
    saturation: float   # 0..1
    brightness: float   # 0..100


# ---------------------------------------------------------------------------
# Curves: shape a 0..1 phase into a 0..1 amount
# ---------------------------------------------------------------------------

def _curve(curve: Curve, p: float) -> float:
    p = p % 1.0
    match curve:
        case Curve.SINE:
            return 0.5 - 0.5 * math.cos(2 * math.pi * p)
        case Curve.RAMP:
            return p
        case Curve.FALL:
            # Snap to full, then decay. This is what reads as a *hit*: the eye
            # sees the attack, not the release.
            return 1.0 - p
        case Curve.SQUARE:
            return 1.0 if p < 0.5 else 0.0
        case Curve.EASE:
            return p * p * (3.0 - 2.0 * p)      # smoothstep
    return p


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

def _hue(track: Track, cycle: int, p: float) -> float:
    pal = track.palette
    match pal.mode:
        case ColorMode.HOLD:
            return pal.hue_from
        case ColorMode.CYCLE:
            return hue_in_range(pal.hue_from, pal.hue_to, p)
        case ColorMode.RANDOM:
            # Seeded on (track, cycle): random-looking, but the same every time
            # the show is played. A show that looks different each night is a
            # show you cannot tune.
            rng = random.Random(f"{track.seed}:{cycle}:{track.id}")
            return hue_in_range(pal.hue_from, pal.hue_to, rng.random())
    return pal.hue_from


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

Renderer = Callable[[Track, float, int, float], float]
"""(track, phase 0..1, cycle number, energy) -> brightness amount 0..1"""


def _solid(track: Track, p: float, cycle: int, energy: float) -> float:
    return 1.0


def _pulse(track: Track, p: float, cycle: int, energy: float) -> float:
    return _curve(track.curve, p)


def _strobe(track: Track, p: float, cycle: int, energy: float) -> float:
    return 1.0 if p < track.duty else 0.0


def _breathe(track: Track, p: float, cycle: int, energy: float) -> float:
    return 0.5 - 0.5 * math.cos(2 * math.pi * p)


def _sweep(track: Track, p: float, cycle: int, energy: float) -> float:
    return 1.0                      # sweep moves the hue, not the brightness


def _chase(track: Track, p: float, cycle: int, energy: float) -> float:
    """On for a slice of the cycle. With `phase` staggered across tracks this
    is what makes a wave run around the room."""
    if p >= track.duty:
        return 0.0
    if track.curve is Curve.SQUARE:
        return 1.0
    # Snap to full at the start of the slice, then decay across it. Shaping the
    # slice with a sine would make the chase *dark* at the instant it fires.
    return _curve(Curve.FALL, p / track.duty)


def _sparkle(track: Track, p: float, cycle: int, energy: float) -> float:
    """Random flashes -- but seeded, so the same beat always sparkles the same."""
    rng = random.Random(f"{track.seed}:{cycle}:{track.id}:sparkle")
    if rng.random() > 0.35 + 0.4 * energy:
        return 0.0
    return _curve(Curve.FALL, p)


RENDERERS: dict[Shape, Renderer] = {
    Shape.SOLID: _solid,
    Shape.PULSE: _pulse,
    Shape.STROBE: _strobe,
    Shape.BREATHE: _breathe,
    Shape.SWEEP: _sweep,
    Shape.CHASE: _chase,
    Shape.SPARKLE: _sparkle,
}


# ---------------------------------------------------------------------------
# The one entry point
# ---------------------------------------------------------------------------

def render(track: Track, beat: float, energy: float = 1.0,
           index: int = 0, count: int = 1) -> Frame:
    """What this track's light number `index` should be, at this beat.

    A track can drive several lights. `spread` says how its pattern is dealt
    across them: 0 and they all do the same thing at the same moment (a group);
    1 and each light sits a little further round the cycle, so the pattern
    travels through the group. It is one number, and it is still a pure offset --
    nothing is remembered between frames.
    """
    offset = track.spread * (index / count) if count > 1 else 0.0

    # Where we are inside this track's own cycle. `rate` is in beats, so this
    # stays locked to the show when the tempo changes.
    pos = beat / track.rate + track.phase + offset
    cycle = math.floor(pos)
    p = pos - cycle

    amount = RENDERERS[track.shape](track, p, cycle, energy)

    # A linked track can run upside down: bright where its leader is dark.
    if track.invert:
        amount = 1.0 - amount

    # Energy scales the *depth* of the pattern, not its brightness: at low
    # energy a strobe becomes a shimmer rather than simply a dimmer strobe.
    amount = lerp(1.0, amount, clamp01(energy))

    bri = lerp(track.bri_min, track.bri_max, amount) * track.level
    return Frame(
        hue=_hue(track, cycle, p),
        saturation=track.palette.saturation,
        brightness=clamp01(bri / 100.0) * 100.0,
    )
