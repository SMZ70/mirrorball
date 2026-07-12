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
- **BLACK** — blackout
- tap any light to set its **shape, rate, colour range, phase** — live, while it plays
- **Save** — name a show and recall it later

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
