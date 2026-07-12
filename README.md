# mmdj

A light sequencer for the house. Each light gets a *pattern* — a shape, a rate in
beats, a colour range — and the engine renders them all as a pure function of the
beat, streamed to the Hue bridge at 50 fps over the Entertainment API.

It is a sequencer, not a soundboard: you set lights up once, save the show, and
recall it. See [PLAN.md](PLAN.md) for the design and why it is built this way.

## Run it

It lives on the Raspberry Pi, in Docker, and starts on boot:

```bash
docker compose up -d --build
```

Then open **http://<pi>:8090** — phone-friendly, "Add to Home Screen" for an app
icon.

- **▶ / ■** — play, and hand the lights back
- **TAP** — tap four times in time with the music; everything locks to that tempo
- **BLACK** — force every light to zero without stopping. The show keeps running
  underneath, still on the beat, so releasing it drops you back in time rather
  than restarting. It is the "kill the room for a second" button, not ■.
- tap any light to set its **shape, rate, colour range, phase** — live, while it plays
- **Presets** — tap one to load it (see below)
- **My shows** — tap a saved show to load it; **Save** names the current one

## Presets

Eight ship with mmdj: `party` `bandari` `birthday` `chill` `rave` `wave` `fire`
`sunset`. Tap one and it loads — including while a show is playing, which swaps
the lights over without a gap.

A preset is **not** a saved show. A saved show names the lights it drives, and
those ids belong to one house; a preset is a list of *voices* ("first light does
a hot chase, second answers with a strobe") that get dealt onto whatever lights
the entertainment area actually has, cycling if there are more lights than
voices. So presets work on any bridge, and nothing about this house is in the
repo.

Add one by adding an entry to `PRESETS` in `mmdj/core/presets.py`. There is
nothing else to touch, and a test builds every preset against 1, 6 and 12 lights
to make sure it still renders.

A preset is a starting point, not a straitjacket: load one, change it, name it,
Save. It lands in `shows/` as your own show and the preset stays pristine.

## Deploy from a laptop

```bash
./scripts/deploy.sh
```

rsyncs the source to the Pi and rebuilds. Credentials are not in the repo or the
image: `bridge.json` lives on the host and is mounted in, as is `shows/`.

## Credentials

```bash
uv run python scripts/register_bridge.py <bridge-ip>   # press the link button
```

Writes `bridge.json` (gitignored): the bridge IP, an app key, and the *clientkey*
that the Entertainment stream uses as its DTLS pre-shared key.

## Tech stack

| | |
|---|---|
| **Language** | Python 3.12, `uv` for deps and lockfile |
| **Core** | pure functions — a show is rendered *from the beat*, with no accumulated state |
| **Model** | pydantic — a `Show` is a JSON document, and validation is the schema |
| **Server** | FastAPI + uvicorn, one WebSocket |
| **Lights** | Hue **Entertainment API** — UDP, DTLS-PSK, ~50 fps |
| **DTLS** | `openssl s_client` as a subprocess (see below) |
| **Discovery** | Hue REST (CLIP v2) over aiohttp — only to ask what lights exist |
| **Panel** | plain HTML/CSS/JS, no framework, no build step — a PWA you can install |
| **Logs** | loguru · **Lint** ruff · **Tests** pytest |
| **Runs on** | Docker, on the Raspberry Pi, `restart: unless-stopped` |

Three decisions carry the design:

**Rendering is a pure function of the beat.** `render(track, beat) -> Frame` — no
state carried between frames. Replay beat 4 an hour later and you get the same
frame. Every mmhue dance broke the other way: brightness accumulated frame to
frame until the contrast washed out. It also means the entire core is testable
without a bridge, a light, or a `sleep`.

**Rates are in beats, not seconds.** Change the tempo and the whole show moves
together, because nothing was ever measured in wall-clock time.

**The panel is disposable.** It edits a `Show` and sends it over the socket; it
never touches a light. A native app later is a new view over the same protocol,
not a rewrite.

## Notes for the next person

- **openssl is the DTLS stack.** Frames are piped through `openssl s_client`.
  `python-mbedtls` was tried first and its handshake has no retransmission timer,
  so it blocks forever with no error. See `mmdj/drivers/dtls.py`.
- **While a show plays, the bridge gives mmdj exclusive ownership** of the
  entertainment area. Stopping releases it. mmhue and the Telegram bot can drive
  those lights again the moment you press ■.

## Tests

```bash
uv run pytest       # the core is pure: no bridge, no lights, no sleeping
```
