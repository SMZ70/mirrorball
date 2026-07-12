# mirrorball — design

## What this is

A DJ panel for Hue lights. Not a wall of buttons that fire canned effects — a
**sequencer**. You assign each light a *pattern* (a shape, a rate in beats, a
colour range), everything stays locked to one tempo, and you save the result as a
**show** you can recall, tweak and loop.

The distinction matters. A soundboard is a dead end: every new effect is new
code. A sequencer is a small set of primitives you *compose*, so the interesting
space grows without the codebase growing.

## The core idea: everything is a pure function of the beat

```
    frame(beat) -> {light_id: (colour, brightness)}
```

A pattern is a **pure function** of the beat clock and its parameters. No state,
no accumulation, no I/O. This one decision buys almost everything:

- **Testable** without a bridge, without lights, without sleeping.
- **Deterministic** — the same beat always renders the same frame, so a show
  looks the same tonight as it did last week (per-track seeded RNG for sparkle).
- **Composable** — layers just add.
- **No drift, no accumulation.** The REST-driven effects this replaces all
  mutated state frame to frame, and all broke the same way: brightness piling up,
  lights stranded lit on cancel, a "restore" target captured mid-strobe. A pure
  function of the clock cannot have those bugs.
- **Free time-travel** — scrub, loop, and "repeat" are just the clock.

Rates are in **beats, never seconds**. Change the BPM and the whole show follows.

## Model

```
Show
  bpm, master{brightness, energy}, blackout
  tracks[]

Track                     a set of lights, one pattern
  targets     light ids            <- one light, or a group
  spread      0 = unison … 1 = the pattern travels across the group
  pattern     pulse | strobe | breathe | sweep | chase | sparkle | solid
  rate        in beats: 4, 2, 1, 1/2, 1/4, 1/8      <- tempo per track
  phase       0..1, offsets this track against the beat (ripples, chases)
  palette     hue range + cycle|random|hold          <- colour range per track
  bri         min..max
  curve       sine | ramp | square | ease
  link        {follow, rate_scale, hue_shift, invert}  <- or follow another track
  level, mute, solo
```

A Show is a **JSON document**. Save = write it. Recall = load it. Share = send it.
That is the whole persistence story, and it will not rot.

## Architecture

```
  PWA (phone)  ──WebSocket(JSON)──►  Engine  ──driver──►  Bridge
   edits the Show                    renders frames
```

**The UI never talks to lights.** It edits the Show; the engine renders. So the
frontend stays dumb and swappable — which is exactly what makes it portable to a
native app later (same protocol, new view layer).

**The driver is pluggable**, and this is load-bearing:

| driver | rate | |
| --- | --- | --- |
| `RestDriver` | ~10 cmd/sec | the ceiling that makes effects smear |
| `StreamDriver` | ~50 frames/sec | Entertainment API over DTLS — what we use |

The REST ceiling is shared across *all* lights, so it gets worse the more of the
room you light. The Entertainment API streams to every light at once instead.

## Anti-tech-debt rules

1. **Core is pure.** `mirrorball/core/` imports no I/O, no network, no bridge. If
   it needs a bridge, it is in the wrong folder.
2. **One source of truth** — the Show document. No state hiding in the UI.
3. **Beats, not seconds.** Anything in seconds is a bug waiting for a tempo change.
4. **Typed at the boundary.** Pydantic models define the protocol.
5. **Patterns are data, not code.** Adding a shape means adding a pure function to
   a registry, not touching the engine.

## Groups and links

Setting six lights one at a time is tedious, and the interesting ideas are all
*relationships*: "these two together", "that one answers this one". Two additions
cover it, and both stay pure functions of the beat.

### A track drives a set of lights, with a spread

`Track.targets` is a list, and `Track.spread` says how the pattern is dealt across
them:

- **spread 0** — every light in the track fires in unison. That is a **group**.
- **spread 1** — the pattern is staggered evenly across the track's lights, so it
  *travels* through them. That is a wave, inside one track.

A single-light track is the degenerate case, so nothing special-cases it. The
per-light offset is `spread · i / n` added to the phase — still pure, still no
state.

### A track can follow another

`Track.link` = `{follow, rate_scale, hue_shift, invert}`. A follower inherits the
leader's **pattern** (shape, curve, rate, duty, palette) and keeps its own
**placement** (which lights, spread, level, brightness range, phase). Then:

- `rate_scale` — 2 = half speed, 0.5 = double time
- `hue_shift` — degrees around the wheel; 180 = the complementary colour
- `invert` — bright when the leader is dark
- `phase` — its own offset, so it can answer half a beat later

That is what "define one light relative to another" means in practice: an echo, a
counterpoint, a shadow.

**Linking is one level deep.** A follower follows its leader's *own* pattern,
never the leader's leader. A real constraint, chosen because it makes a cycle
impossible by construction rather than by a visited-set check that someone has to
remember to keep correct. Two tracks pointing at each other still render fine.

### Presets get a layout

A preset says how its voices meet the room:

- **each** — one track per light, voices cycled (the tour: `party`, `birthday`)
- **all** — every light in ONE track (`rave` in unison, `wave` travelling)
- **split** — lights dealt into one group per voice (call and answer)

## State

Done: the pure core; the `StreamDriver` at ~50 fps; the WebSocket API and show
store; the PWA panel (pattern editor, tap tempo, inline help, save/recall,
presets); groups and links; Docker.

Next, in rough order of appeal:

- **FX pads** — hold for momentary, tap to latch.
- **Beat detection from the phone's mic**, so the lights lock to whatever is
  actually playing in the room, with no hardware.
- **Timeline** — sections that advance on their own, so a show has an arc rather
  than a loop.

Not doing: an app-store build. The PWA installs on a phone; Capacitor can wrap it
later if there is ever a reason.
