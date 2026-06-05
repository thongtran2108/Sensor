"""KEYENCE TCP command-socket driver.

Connects to the unit with a plain TCP socket and uses KEYENCE's ASCII command
protocol: send a command terminated by the line terminator (e.g. ``M0\\r\\n``)
and read back the reply (e.g. ``M0,+0012.3456,+0008.1200,...\\r\\n``).

Response parsing is intentionally forgiving and fully configurable because the
exact reply format depends on the unit/firmware:

* an optional leading echo token (``M0``) is dropped when ``strip_echo`` is set;
* the remaining comma-separated tokens are mapped to CH0, CH1, ... in order;
* tokens listed in ``invalid_tokens`` (or numbers in ``invalid_values``) become
  an invalid / over-range reading.

The full request/response text is kept in ``last_exchange`` so the UI and the
``tools/test_connection.py`` helper can show exactly what came back.
"""
from __future__ import annotations

import socket
from typing import List, Optional

from .base import SensorDriver
from ..models import SensorReading


def _looks_numeric(token: str) -> bool:
    try:
        float(token)
        return True
    except (TypeError, ValueError):
        return False


class KeyenceSocketDriver(SensorDriver):
    def __init__(self, config):
        super().__init__(config)
        self._sock: Optional[socket.socket] = None

    # --- lifecycle -------------------------------------------------------- #
    def connect(self) -> None:
        dev = self.config.device
        sock = socket.create_connection((dev.ip, dev.port), timeout=dev.timeout)
        sock.settimeout(dev.timeout)
        self._sock = sock

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    # --- low-level exchange ---------------------------------------------- #
    def _exchange(self, command: str) -> str:
        """Send one command and return the decoded reply (terminator stripped)."""
        if self._sock is None:
            raise ConnectionError("Socket chưa kết nối")
        dev = self.config.device
        term = dev.term
        payload = (command + term).encode(dev.encoding, errors="replace")
        self._sock.sendall(payload)

        term_bytes = term.encode(dev.encoding)
        buf = bytearray()
        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if term_bytes and term_bytes in buf:
                break

        reply = bytes(buf).decode(dev.encoding, errors="replace")
        return reply.strip("\r\n")

    # --- parsing ---------------------------------------------------------- #
    def _tokens(self, reply: str) -> List[str]:
        s = reply.strip()
        if not s:
            return []
        if s.upper().startswith("ER"):           # KEYENCE error response
            raise IOError(f"Thiết bị báo lỗi: {s}")
        parts = [p.strip() for p in s.split(",")]
        if self.config.protocol.strip_echo and parts and not _looks_numeric(parts[0]):
            parts = parts[1:]                    # drop leading echo like "M0"
        return parts

    def _to_value(self, token: str) -> Optional[float]:
        proto = self.config.protocol
        if token == "" or token in proto.invalid_tokens:
            return None
        try:
            num = float(token)
        except ValueError:
            return None
        if num in proto.invalid_values:
            return None
        return num * proto.scale

    # --- data ------------------------------------------------------------- #
    def read_all(self) -> List[SensorReading]:
        proto = self.config.protocol
        n = self.config.channels.count
        readings = [SensorReading(channel=ch, name=self.config.channels.name(ch))
                    for ch in range(n)]
        log: List[str] = []

        if proto.read_mode == "per_channel":
            for ch in range(n):
                cmd = proto.command_template.format(n=ch)
                reply = self._exchange(cmd)
                log.append(f">>> {cmd}\n<<< {reply!r}")
                toks = self._tokens(reply)
                # take the last numeric token as this channel's value
                val = self._to_value(toks[-1]) if toks else None
                readings[ch].value = val
        else:  # all_in_one
            # value command first, then any extra field commands (peak/bottom/...)
            field_cmds = {"value": proto.command}
            field_cmds.update(proto.extra_commands)
            for fieldname, cmd in field_cmds.items():
                reply = self._exchange(cmd)
                log.append(f">>> {cmd}\n<<< {reply!r}")
                toks = self._tokens(reply)
                for ch in range(n):
                    val = self._to_value(toks[ch]) if ch < len(toks) else None
                    setattr(readings[ch], fieldname, val)

        for r in readings:
            if r.pp is None and r.peak is not None and r.bottom is not None:
                r.pp = r.peak - r.bottom
            r.valid = r.value is not None

        self.last_exchange = "\n".join(log)
        return readings
