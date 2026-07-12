"""The Show: the single source of truth.

A Show is a JSON document. The UI edits it, the engine renders it, saving it is
`json.dump`. There is no other state anywhere -- no hidden globals, nothing
living only in the browser. Recall, undo, share and "repeat" all fall out of
this for free.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Shape(StrEnum):
    """What a track does over one cycle. Adding one means adding a pure
    function to patterns.RENDERERS -- the engine never changes."""
    SOLID = "solid"        # hold a colour
    PULSE = "pulse"        # swell up and back down
    STROBE = "strobe"      # hard on/off
    BREATHE = "breathe"    # slow, soft sine
    SWEEP = "sweep"        # travel through the palette
    CHASE = "chase"        # on for a slice of the cycle, off the rest
    SPARKLE = "sparkle"    # random flashes, seeded so it stays repeatable


class Curve(StrEnum):
    SINE = "sine"
    RAMP = "ramp"          # saw: rise, then snap back
    FALL = "fall"          # snap up, then decay -- reads as a *hit*
    SQUARE = "square"
    EASE = "ease"


class ColorMode(StrEnum):
    HOLD = "hold"          # first hue, unchanging
    CYCLE = "cycle"        # walk the range over the cycle
    RANDOM = "random"      # new hue each cycle (seeded)


class Palette(BaseModel):
    """A colour range, per track. 'l1 does golds, l2 does teals.'"""
    hue_from: float = Field(30.0, ge=0, le=360)
    hue_to: float = Field(50.0, ge=0, le=360)
    saturation: float = Field(1.0, ge=0, le=1)
    mode: ColorMode = ColorMode.CYCLE


class Track(BaseModel):
    """One light (or one room) with one pattern.

    `rate` is in BEATS, so a track set to 0.5 fires twice a beat and stays
    locked to the show when the tempo changes. Seconds would drift apart.
    """
    id: str
    target: str                                  # light id, or room id
    target_kind: Literal["light", "room"] = "light"
    name: str = ""

    shape: Shape = Shape.PULSE
    curve: Curve = Curve.SINE
    rate: float = Field(1.0, gt=0, le=64)        # cycle length in beats
    phase: float = Field(0.0, ge=0, lt=1)        # offset within the cycle
    duty: float = Field(0.5, gt=0, le=1)         # how much of the cycle is "on"

    palette: Palette = Field(default_factory=Palette)
    bri_min: float = Field(0.0, ge=0, le=100)
    bri_max: float = Field(100.0, ge=0, le=100)

    level: float = Field(1.0, ge=0, le=1)        # channel fader
    mute: bool = False
    solo: bool = False
    seed: int = 0                                # keeps SPARKLE repeatable


class Master(BaseModel):
    brightness: float = Field(1.0, ge=0, le=1)
    energy: float = Field(1.0, ge=0, le=1)       # scales pattern depth globally


class Show(BaseModel):
    """Everything. Save this, and you have saved the night."""
    version: int = 1
    name: str = "untitled"
    bpm: float = Field(120.0, ge=40, le=220)
    master: Master = Field(default_factory=Master)
    blackout: bool = False
    tracks: list[Track] = Field(default_factory=list)

    def active_tracks(self) -> list[Track]:
        """Solo wins over mute, as on every mixer ever built."""
        soloed = [t for t in self.tracks if t.solo]
        if soloed:
            return soloed
        return [t for t in self.tracks if not t.mute]
