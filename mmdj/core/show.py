"""The Show: the single source of truth.

A Show is a JSON document. The UI edits it, the engine renders it, saving it is
`json.dump`. There is no other state anywhere -- no hidden globals, nothing
living only in the browser. Recall, undo, share and "repeat" all fall out of
this for free.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class Link(BaseModel):
    """One track defined relative to another.

    The follower inherits the leader's *pattern* (shape, curve, rate, duty,
    palette) and keeps its own *placement* (which lights, spread, level,
    brightness, phase). That split is the whole idea: "same idea, over here,
    a bit later, in the opposite colour".
    """
    follow: str                                  # the leader's track id
    rate_scale: float = Field(1.0, gt=0, le=16)  # 2 = half speed, 0.5 = double time
    hue_shift: float = Field(0.0, ge=-360, le=360)   # 180 = complementary colour
    invert: bool = False                         # bright when the leader is dark


class Track(BaseModel):
    """A pattern, and the lights it drives.

    `rate` is in BEATS, so a track set to 0.5 fires twice a beat and stays
    locked to the show when the tempo changes. Seconds would drift apart.

    `targets` is a LIST: a track can drive one light or six. `spread` decides
    what that means -- 0 and they fire in unison (a group), 1 and the pattern is
    dealt evenly across them, so it travels. A single-light track is just the
    degenerate case, which is why nothing special-cases it.
    """
    id: str
    targets: list[str] = Field(default_factory=list)     # light ids
    target_kind: Literal["light", "room"] = "light"
    name: str = ""

    shape: Shape = Shape.PULSE
    curve: Curve = Curve.SINE
    rate: float = Field(1.0, gt=0, le=64)        # cycle length in beats
    phase: float = Field(0.0, ge=0, lt=1)        # offset within the cycle
    duty: float = Field(0.5, gt=0, le=1)         # how much of the cycle is "on"
    spread: float = Field(0.0, ge=0, le=1)       # 0 = unison, 1 = dealt across

    palette: Palette = Field(default_factory=Palette)
    bri_min: float = Field(0.0, ge=0, le=100)
    bri_max: float = Field(100.0, ge=0, le=100)

    level: float = Field(1.0, ge=0, le=1)        # channel fader
    link: Link | None = None                     # defined relative to another track
    invert: bool = False                         # set by a link; see Show.effective
    mute: bool = False
    solo: bool = False
    seed: int = 0                                # keeps SPARKLE repeatable

    @model_validator(mode="before")
    @classmethod
    def _accept_v1(cls, data: object) -> object:
        """A v1 track named one light as `target`. Shows saved back then must
        still load -- they are the user's work, not our schema's problem."""
        if isinstance(data, dict) and "target" in data and not data.get("targets"):
            data = {**data, "targets": [data["target"]]}
            data.pop("target", None)
        return data


class Master(BaseModel):
    brightness: float = Field(1.0, ge=0, le=1)
    energy: float = Field(1.0, ge=0, le=1)       # scales pattern depth globally


class Show(BaseModel):
    """Everything. Save this, and you have saved the night."""
    version: int = 2
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

    def effective(self, track: Track) -> Track:
        """The track as it will actually render, with any link resolved.

        A follower takes the leader's PATTERN and keeps its own PLACEMENT. It
        follows the leader's own pattern and never the leader's leader: linking
        is one level deep, which makes a cycle impossible by construction rather
        than by a visited-set that someone has to remember to maintain.
        """
        if track.link is None:
            return track

        leader = next((t for t in self.tracks if t.id == track.link.follow), None)
        if leader is None or leader.id == track.id:
            return track.model_copy(update={"link": None})    # a dangling link is just a track

        pal = leader.palette
        shift = track.link.hue_shift
        return track.model_copy(update={
            # inherited: the pattern
            "shape": leader.shape,
            "curve": leader.curve,
            "duty": leader.duty,
            "rate": min(64.0, leader.rate * track.link.rate_scale),
            "palette": pal.model_copy(update={
                "hue_from": (pal.hue_from + shift) % 360,
                "hue_to": (pal.hue_to + shift) % 360,
                "mode": pal.mode,
            }),
            # its own: where it plays, how loud, and which way up
            "invert": track.link.invert,
        })
