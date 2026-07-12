"""Register with the Hue bridge and get an Entertainment clientkey.

The clientkey (a DTLS pre-shared key) is issued ONLY at the moment an app key is
created, and only if you ask for it. mmhue's registration never did, which is
why streaming is not available to us today -- the existing key cannot be
upgraded, it has to be a fresh one.

Requires someone to press the physical link button on the bridge. This polls for
a minute so the press does not have to be perfectly timed.

    uv run python scripts/register_bridge.py <bridge-ip>
"""

from __future__ import annotations

import asyncio
import json
import ssl
import sys
from pathlib import Path

import aiohttp

POLL_SECONDS = 60
DEVICE_TYPE = "mmdj#sequencer"


async def register(host: str) -> dict | None:
    # The bridge serves a self-signed cert on its own IP; verification would
    # fail on principle and buy us nothing on a LAN we already trust.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"https://{host}/api"
    payload = {"devicetype": DEVICE_TYPE, "generateclientkey": True}

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as session:
        for remaining in range(POLL_SECONDS, 0, -1):
            async with session.post(url, json=payload) as resp:
                data = await resp.json()

            entry = data[0] if isinstance(data, list) and data else {}

            if "success" in entry:
                return entry["success"]

            err = entry.get("error", {})
            if err.get("type") != 101:          # 101 = "link button not pressed"
                print(f"bridge said: {err.get('description', data)}")
                return None

            print(f"  waiting for the link button... {remaining}s", end="\r", flush=True)
            await asyncio.sleep(1)

    print("\ntimed out -- nobody pressed the button")
    return None


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    host = sys.argv[1]
    print(f"Press the round button on the Hue bridge at {host} now.\n")

    result = await register(host)
    if not result:
        return 1

    print("\n\nregistered.\n")
    out = Path("bridge.json")
    out.write_text(json.dumps({
        "host": host,
        "app_key": result["username"],
        "client_key": result["clientkey"],
    }, indent=2) + "\n")
    print(f"  app key    : {result['username'][:12]}...")
    print(f"  client key : {'yes' if result.get('clientkey') else 'MISSING'}")
    print(f"\n  -> {out} (gitignored; it is a credential)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
