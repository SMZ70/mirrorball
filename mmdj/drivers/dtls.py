"""DTLS, via openssl.

Python has no DTLS in the standard library, so this used python-mbedtls first.
That was a mistake and it cost an evening: its handshake has no retransmission
timer, so if the bridge's first flight does not arrive immediately it blocks
forever with no error. It worked twice and then never again -- which looked like
a wedged bridge, and was not.

Proof it is the library and not the bridge: with the same credentials, on the
same socket, at the same moment,

    openssl s_client -dtls1_2 -psk ... -connect <bridge>:2100
    => New, TLSv1.2, Cipher is PSK-AES128-GCM-SHA256

handshakes first time, every time, while python-mbedtls hangs.

So: let openssl do the DTLS. We spawn `s_client` and write frames to its stdin;
each write becomes one datagram. It is a subprocess rather than a library call,
which is not elegant -- but it is the part of this system that has to be
reliable, and openssl's DTLS is battle-tested in a way that a thin binding is
not.
"""

from __future__ import annotations

import asyncio
import shutil

from loguru import logger

HANDSHAKE_TIMEOUT = 8.0


class DtlsPipe:
    """A DTLS connection to the bridge, held open by openssl."""

    def __init__(self, host: str, port: int, identity: str, psk_hex: str) -> None:
        self.host = host
        self.port = port
        self.identity = identity
        self.psk_hex = psk_hex
        self._proc: asyncio.subprocess.Process | None = None
        self._drain: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return bool(self._proc and self._proc.returncode is None)

    async def open(self) -> None:
        if not shutil.which("openssl"):
            raise RuntimeError("openssl is not installed; it is how mmdj speaks DTLS")

        self._proc = await asyncio.create_subprocess_exec(
            "openssl", "s_client",
            "-dtls1_2",
            "-connect", f"{self.host}:{self.port}",
            "-psk_identity", self.identity,
            "-psk", self.psk_hex,
            "-cipher", "PSK-AES128-GCM-SHA256",
            # NOT -quiet: it suppresses the very handshake banner we wait on.
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for the handshake to actually complete before claiming success --
        # openssl prints the negotiated cipher once it is up.
        try:
            await asyncio.wait_for(self._await_handshake(), timeout=HANDSHAKE_TIMEOUT)
        except TimeoutError:
            await self.close()
            raise ConnectionError("DTLS handshake timed out") from None

        logger.info("DTLS up: {}:{}", self.host, self.port)

    async def _await_handshake(self) -> None:
        """openssl announces the negotiated cipher on stdout once it is up."""
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                raise ConnectionError("openssl exited during the handshake")
            text = line.decode(errors="replace")
            if "Cipher is" in text:
                # Keep draining stdout forever after this. openssl writes the
                # peer's replies there, and a full pipe would block the process
                # -- which would silently stop the lights mid-show.
                self._drain = asyncio.create_task(self._drain_stdout())
                return
            if "handshake failure" in text.lower():
                raise ConnectionError(f"DTLS handshake failed: {text.strip()}")

    async def _drain_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while await self._proc.stdout.read(4096):
                pass
        except (asyncio.CancelledError, Exception):
            pass

    async def send(self, packet: bytes) -> None:
        """One write, one datagram."""
        if not self.connected or not self._proc or not self._proc.stdin:
            return
        try:
            self._proc.stdin.write(packet)
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            logger.warning("DTLS pipe closed")
            self._proc = None

    async def close(self) -> None:
        if self._drain:
            self._drain.cancel()
            self._drain = None
        proc, self._proc = self._proc, None
        if not proc or proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (ProcessLookupError, TimeoutError):
            with_kill = getattr(proc, "kill", None)
            if with_kill:
                with_kill()
