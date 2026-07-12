"""Colour, kept deliberately simple: hue in degrees, and the conversion out.

The engine works in hue/brightness because that is what patterns think in. The
driver decides what the bridge wants (CIE xy today, RGB when streaming).
"""

from __future__ import annotations

from colorsys import hsv_to_rgb
from dataclasses import dataclass

WHITE_XY = (0.3127, 0.3290)   # CIE D65


@dataclass(frozen=True, slots=True)
class Rgb:
    r: float   # 0..1
    g: float
    b: float


def hue_to_rgb(hue_deg: float, saturation: float = 1.0) -> Rgb:
    r, g, b = hsv_to_rgb((hue_deg % 360.0) / 360.0, saturation, 1.0)
    return Rgb(r, g, b)


def hue_to_xy(hue_deg: float, saturation: float = 1.0) -> tuple[float, float]:
    """Hue -> CIE xy, for the REST driver."""
    c = hue_to_rgb(hue_deg, saturation)
    x = c.r * 0.4124 + c.g * 0.3576 + c.b * 0.1805
    y = c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
    z = c.r * 0.0193 + c.g * 0.1192 + c.b * 0.9505
    total = x + y + z
    if total <= 0:
        return WHITE_XY
    return x / total, y / total


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp01(t)


def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def lerp_hue(a: float, b: float, t: float) -> float:
    """Interpolate the short way round the colour wheel.

    Naive interpolation from 350 to 10 travels backwards through the whole
    spectrum -- green, blue, everything -- instead of stepping across zero.
    """
    diff = ((b - a + 180.0) % 360.0) - 180.0
    return (a + diff * clamp01(t)) % 360.0


def hue_in_range(hue_from: float, hue_to: float, t: float) -> float:
    """Walk a palette range forwards around the wheel.

    Distinct from lerp_hue, and the difference matters. lerp_hue takes the
    *short* way (blending two colours), so 0 -> 360 does not move at all: they
    are the same point on the wheel. But a palette of 0 -> 360 means "the whole
    spectrum". So a range always travels forwards, and a zero-width range that
    was not written as a single colour means all the way round.
    """
    span = (hue_to - hue_from) % 360.0
    if span == 0.0 and hue_to != hue_from:
        span = 360.0                      # 0 -> 360: the full wheel
    return (hue_from + span * clamp01(t)) % 360.0
