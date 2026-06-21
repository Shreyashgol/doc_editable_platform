"""Virus scanning via ClamAV (clamd INSTREAM), with a no-op scanner for disabled environments."""

from __future__ import annotations

import socket
import struct

from ...core.errors import InfrastructureError, VirusDetectedError
from ...domain.ports import VirusScanner


class ClamAVScanner(VirusScanner):
    def __init__(self, host: str, port: int, *, timeout: float = 30.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    def scan(self, data: bytes) -> None:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
                sock.sendall(b"zINSTREAM\x00")
                # Stream in chunks: 4-byte big-endian length prefix, then bytes; 0-length ends.
                view = memoryview(data)
                chunk = 1 << 16
                for i in range(0, len(view), chunk):
                    part = view[i : i + chunk]
                    sock.sendall(struct.pack("!L", len(part)) + part)
                sock.sendall(struct.pack("!L", 0))
                response = sock.recv(4096).decode(errors="replace").strip()
        except OSError as exc:  # pragma: no cover - network
            raise InfrastructureError(f"clamav unreachable: {exc}") from exc

        if "FOUND" in response:
            signature = response.split(":", 1)[-1].strip()
            raise VirusDetectedError(f"malware detected: {signature}")


class NullVirusScanner(VirusScanner):
    """Used when scanning is disabled (local/dev). Always passes; documented as insecure for prod."""

    def scan(self, data: bytes) -> None:
        return None
