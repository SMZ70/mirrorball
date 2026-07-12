"""Shows that ship with mmdj.

A preset is NOT a saved Show. A saved Show names the lights it drives, and those
names are this house's -- they would be meaningless on another bridge, and they
have no business in the repo. A preset is a list of *voices* instead: "the first
light does a hot chase, the second answers with a strobe". Voices are dealt onto
whatever lights the entertainment area actually has, cycling if there are more
lights than voices.

So a preset is a recipe, and `build()` cooks it for the room it finds itself in.
Add one by adding an entry to PRESETS -- there is nothing else to touch.
"""

from __future__ import annotations

from dataclasses import dataclass

from mmdj.bridge import Light
from mmdj.core.show import ColorMode, Curve, Master, Palette, Shape, Show, Track


@dataclass(frozen=True, slots=True)
class Voice:
    """One light's part. `phase=None` means "spread these out around the room",
    which is what turns a chase into something that travels."""
    shape: Shape
    curve: Curve
    rate: float
    hue: tuple[float, float]
    mode: ColorMode = ColorMode.CYCLE
    duty: float = 0.5
    bri: tuple[float, float] = (0.0, 100.0)
    level: float = 1.0
    phase: float | None = None
    saturation: float = 1.0


@dataclass(frozen=True, slots=True)
class Preset:
    bpm: float
    voices: list[Voice]
    energy: float = 1.0
    note: str = ""


# ── The shows ───────────────────────────────────────────────────────────────
#
# Hues, for reference: 0 red · 30 orange · 50 gold · 120 green · 180 cyan
#                      220 blue · 275 violet · 320 magenta · 360 red again

PRESETS: dict[str, Preset] = {

    # Everything at once: every light a different pattern. The house's default.
    "party": Preset(bpm=120, note="one of each — the tour", voices=[
        Voice(Shape.PULSE,   Curve.SINE,   1.0,  (30, 55)),
        Voice(Shape.CHASE,   Curve.FALL,   1.0,  (320, 350)),
        Voice(Shape.STROBE,  Curve.SQUARE, 0.5,  (180, 200)),
        Voice(Shape.BREATHE, Curve.SINE,   4.0,  (265, 290)),
        Voice(Shape.SPARKLE, Curve.FALL,   0.5,  (45, 60)),
        Voice(Shape.SWEEP,   Curve.SINE,   8.0,  (0, 360)),
    ]),

    # 6/8. The dohol on the offbeat is what makes it bandari rather than a
    # disco: hard hits that decay, not swells.
    "bandari": Preset(bpm=150, note="6/8, hot and driving", voices=[
        Voice(Shape.CHASE,   Curve.FALL,   0.25, (0, 25),   duty=0.35, bri=(0, 100)),
        Voice(Shape.STROBE,  Curve.FALL,   0.5,  (35, 55),  duty=0.3,  bri=(0, 100)),
        Voice(Shape.CHASE,   Curve.FALL,   0.25, (10, 40),  duty=0.35, bri=(0, 100)),
        Voice(Shape.PULSE,   Curve.FALL,   0.75, (330, 360), bri=(5, 95)),
        Voice(Shape.SPARKLE, Curve.FALL,   0.25, (45, 60),  bri=(0, 100)),
        Voice(Shape.CHASE,   Curve.FALL,   0.5,  (20, 50),  duty=0.4,  bri=(0, 100)),
    ]),

    # Confetti. Every colour, all the time, nothing held for long.
    "birthday": Preset(bpm=128, note="confetti — the whole wheel", voices=[
        Voice(Shape.SPARKLE, Curve.FALL,   0.25, (0, 360), ColorMode.RANDOM, bri=(0, 100)),
        Voice(Shape.CHASE,   Curve.FALL,   0.5,  (0, 360), ColorMode.RANDOM, duty=0.4),
        Voice(Shape.PULSE,   Curve.SINE,   1.0,  (0, 360), ColorMode.CYCLE,  bri=(10, 100)),
        Voice(Shape.STROBE,  Curve.SQUARE, 0.25, (0, 360), ColorMode.RANDOM, duty=0.35),
    ]),

    # For when the music stops but the evening has not. Nothing snaps.
    "chill": Preset(bpm=70, energy=0.6, note="slow, warm, no hard edges", voices=[
        Voice(Shape.BREATHE, Curve.SINE, 8.0,  (20, 45),   bri=(25, 70)),
        Voice(Shape.BREATHE, Curve.SINE, 12.0, (270, 320), bri=(20, 60)),
        Voice(Shape.SWEEP,   Curve.SINE, 16.0, (10, 50),   bri=(30, 65)),
        Voice(Shape.SOLID,   Curve.SINE, 8.0,  (25, 35),   ColorMode.HOLD, bri=(35, 50)),
    ]),

    # Everything together, no phase spread: the room becomes one lamp.
    "rave": Preset(bpm=140, note="hard strobe, all as one", voices=[
        Voice(Shape.STROBE, Curve.SQUARE, 0.125, (180, 200), duty=0.4, bri=(0, 100), phase=0.0),
        Voice(Shape.STROBE, Curve.SQUARE, 0.125, (300, 330), duty=0.4, bri=(0, 100), phase=0.0),
        Voice(Shape.STROBE, Curve.SQUARE, 0.25,  (0, 360), ColorMode.RANDOM,
              duty=0.5, bri=(0, 100), phase=0.5),
    ]),

    # One idea, done properly: a wave that runs around the room. The phases are
    # left to spread themselves, which is the whole trick.
    "wave": Preset(bpm=100, note="a wave running around the room", voices=[
        Voice(Shape.CHASE, Curve.FALL, 2.0, (170, 210), duty=0.45, bri=(0, 100)),
    ]),

    # Flicker. Random hue per cycle in a narrow band of reds -- it reads as fire
    # precisely because it never repeats and never leaves the band.
    "fire": Preset(bpm=90, energy=0.85, note="flicker, embers, no blue", voices=[
        Voice(Shape.SPARKLE, Curve.FALL, 0.5, (0, 30),  ColorMode.RANDOM, bri=(15, 100)),
        Voice(Shape.PULSE,   Curve.FALL, 1.5, (10, 40), ColorMode.RANDOM, bri=(25, 90)),
        Voice(Shape.SPARKLE, Curve.FALL, 0.75, (20, 50), ColorMode.RANDOM, bri=(10, 95)),
        Voice(Shape.BREATHE, Curve.SINE, 6.0, (5, 25),  ColorMode.CYCLE,  bri=(30, 70)),
    ]),

    # Slow travel across the whole spectrum. Good for dinner, good for a photo.
    "sunset": Preset(bpm=60, energy=0.7, note="a long drift, orange to violet", voices=[
        Voice(Shape.SWEEP, Curve.SINE, 24.0, (10, 300), bri=(40, 90)),
        Voice(Shape.SWEEP, Curve.SINE, 24.0, (350, 280), bri=(35, 85), phase=0.25),
        Voice(Shape.BREATHE, Curve.SINE, 10.0, (300, 340), bri=(30, 75)),
    ]),
}


def names() -> list[str]:
    return list(PRESETS)


def info() -> list[dict]:
    """What the panel needs to draw a preset before loading it: what it is
    called, what it sounds like, and what colours it will put in the room."""
    return [
        {
            "name": name,
            "note": preset.note,
            "bpm": preset.bpm,
            "hues": [list(v.hue) for v in preset.voices],
        }
        for name, preset in PRESETS.items()
    ]


def build(name: str, lights: list[Light]) -> Show:
    """Deal a preset's voices onto the lights we actually have."""
    preset = PRESETS[name]
    n = max(len(lights), 1)

    tracks = []
    for i, light in enumerate(lights):
        v = preset.voices[i % len(preset.voices)]
        lo, hi = v.hue
        tracks.append(Track(
            id=f"t{i}",
            target=light.id,
            name=light.name,
            shape=v.shape,
            curve=v.curve,
            rate=v.rate,
            # No phase given? Spread this light around the cycle. That is what
            # makes a chase travel instead of every light firing at once.
            phase=v.phase if v.phase is not None else (i / n) % 1.0,
            duty=v.duty,
            palette=Palette(hue_from=lo, hue_to=hi, mode=v.mode, saturation=v.saturation),
            bri_min=v.bri[0],
            bri_max=v.bri[1],
            level=v.level,
            seed=i,
        ))

    return Show(
        name=name,
        bpm=preset.bpm,
        master=Master(brightness=1.0, energy=preset.energy),
        tracks=tracks,
    )
