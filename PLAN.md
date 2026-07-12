# mmdj — a light sequencer for the house

## What this is

A DJ panel for the Hue lights. Not a wall of buttons that fire canned effects —
a **sequencer**. You assign each light a *pattern* (a shape, a rate in beats, a
colour range), everything stays locked to one tempo, and you save the result as
a **show** you can recall, tweak and loop.

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
- **No drift, no accumulation.** Every dance I wrote today had bugs from mutating
  state frame to frame: brightness piling up, lights stranded lit, restore
  targets captured mid-strobe. A pure function of the clock cannot have them.
- **Free time-travel** — scrub, loop, and "repeat" are just the clock.

Rates are in **beats, never seconds**. Change the BPM and the whole show follows.

## Model

```
Show
  bpm, master{brightness, energy}, blackout
  tracks[]

Track                     one light (or one room), one pattern
  target      light id | room id
  pattern     pulse | strobe | breathe | sweep | chase | sparkle | solid
  rate        in beats: 4, 2, 1, 1/2, 1/4, 1/8      <- tempo per light
  phase       0..1, offsets this track against the beat (ripples, chases)
  palette     hue range or list + cycle|random|hold  <- colour range per light
  bri         min..max
  curve       sine | ramp | square | ease
  level, mute, solo
```

A Show is a **JSON document**. Save = write it. Recall = load it. Share = send it.
That is the whole persistence story, and it will not rot.

## Architecture

```
  PWA (phone)  ──WebSocket(JSON patches)──►  Engine  ──driver──►  Bridge
   edits the Show                            renders frames
```

**The UI never talks to lights.** It edits the Show; the engine renders. So the
frontend stays dumb and swappable — which is exactly what makes it portable to a
native app later (same protocol, new view layer).

**The driver is pluggable**, and this is load-bearing:

| driver | rate | status |
| --- | --- | --- |
| `RestDriver` | ~10 cmd/sec | works today |
| `StreamDriver` | ~50 frames/sec | needs a bridge **clientkey** |

The Hue REST API accepts about ten commands a second — the ceiling that wrecked
every dance today (bandari throttled into a smear; the birthday opening taking
37s to detonate). The **Entertainment API** streams over DTLS at ~50Hz instead.
That is the difference between a toy and an instrument: real fades, draggable
faders, strobes that land on the beat.

**Blocked on one physical act:** the clientkey is only issued when an app key is
created, and ours never asked for one. It needs someone to press the button on
the Hue bridge. Until then the engine runs on `RestDriver` and everything else
proceeds — no design changes when the key arrives, just a different driver.

## Anti-tech-debt rules

1. **Core is pure.** `mmdj/core/` imports no I/O, no aiohue, no network. If it
   needs a bridge, it is in the wrong folder.
2. **One source of truth** — the Show document. No state hiding in the UI.
3. **Beats, not seconds.** Anything in seconds is a bug waiting for a tempo change.
4. **Typed at the boundary.** Pydantic models define the protocol; the frontend
   gets generated types. No stringly-typed JSON.
5. **Patterns are data, not code.** Adding a shape means adding a pure function
   to a registry, not touching the engine.

## Phases

- **P1 — core** (now): clock, colour, patterns, Show model, engine, REST driver,
  tests. Play a show from the CLI.
- **P2 — API**: FastAPI + WebSocket. Live patching, save/load shows.
- **P3 — the panel**: PWA. Track list, per-light pattern editor, tap tempo,
  master, blackout, save/recall.
- **P4 — streaming**: `StreamDriver` at 50Hz once the clientkey exists.
- **P5 — performance**: FX pads (hold = momentary, tap = latch), and beat
  detection from the phone's mic so the lights lock to whatever is playing.

## Not doing

- Rewriting mmhue. It keeps the bot, the scenes and the birthday party. mmdj is
  the performance instrument; they can share the bridge and hand off cleanly.
- An app store build. The PWA installs on a phone. Capacitor can wrap it later
  if there is ever a reason.

## P6 — groups and links (ergonomics)

Setting six lights one at a time is tedious, and the interesting ideas are all
*relationships*: "these two together", "that one answers this one". Two additions
cover it, and both stay pure functions of the beat.

### A track drives a set of lights, with a spread

`Track.targets` is a list, and `Track.spread` says how the pattern is dealt
across them:

- **spread 0** — every light in the track fires in unison. That is a **group**.
- **spread 1** — the pattern is staggered evenly across the track's lights, so it
  *travels* through them. That is a wave, inside one track.

A single-light track is just the degenerate case, so nothing special-cases it.
The per-light offset is `spread · i / n` added to the phase -- still a pure
function, still no state.

### A track can follow another

`Track.link` = `{follow, rate_scale, hue_shift, invert}`. A follower inherits the
leader's **pattern** (shape, curve, rate, duty, palette) and keeps its own
**placement** (which lights, spread, level, brightness range, phase). Then:

- `rate_scale` — 2 = half speed, 0.5 = double time
- `hue_shift` — degrees around the wheel; 180 = the complementary colour
- `invert` — bright when the leader is dark
- `phase` — its own offset, so it can answer half a beat later

This is what "define one relative to another" means in practice: an echo, a
counterpoint, a shadow.

**Linking is one level deep.** A follower follows its leader's *own* pattern,
never the leader's leader. That is a real constraint, chosen because it makes a
cycle impossible by construction rather than by a visited-set check that someone
has to remember to keep correct.

### Presets get a layout

A preset says how its voices meet the room:

- **each** — one track per light, voices cycled (the tour: `party`, `birthday`)
- **all** — every light in ONE track (`rave` in unison, `wave` travelling)
- **split** — lights dealt into one group per voice (call and answer)
