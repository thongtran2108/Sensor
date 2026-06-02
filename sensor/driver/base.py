"""Abstract driver interface.

Keeping the UI behind this interface means a different transport (RS-232C
DL-RS1A, PROFINET DL-PN1, a recorded-file replayer, ...) can be dropped in
later without touching the GUI.
"""
from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from typing import List, Optional

from ..config import AppConfig, DataMap
from ..models import Judgment, SensorReading

# struct format characters per type name
_TYPE_FMT = {
    "int8": "b", "uint8": "B",
    "int16": "h", "uint16": "H",
    "int32": "i", "uint32": "I",
    "int64": "q", "uint64": "Q",
    "float32": "f", "float64": "d",
}


def _order_char(byte_order: str) -> str:
    return "<" if str(byte_order).lower().startswith("little") else ">"


def read_scalar(buf: bytes, offset: int, type_name: str, byte_order: str):
    """Unpack one scalar from ``buf``; return ``None`` if out of bounds."""
    fmt = _TYPE_FMT.get(type_name)
    if fmt is None:
        raise ValueError(f"Unknown field type: {type_name!r}")
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(buf):
        return None
    return struct.unpack_from(_order_char(byte_order) + fmt, buf, offset)[0]


def _judgment_from_status(word: Optional[int], bits: dict) -> Judgment:
    if word is None or not bits:
        return Judgment.NONE
    if "hi" in bits and word & (1 << bits["hi"]):
        return Judgment.HI
    if "lo" in bits and word & (1 << bits["lo"]):
        return Judgment.LO
    if "go" in bits and word & (1 << bits["go"]):
        return Judgment.GO
    return Judgment.NONE


class SensorDriver(ABC):
    """Common interface every transport implements."""

    def __init__(self, config: AppConfig):
        self.config = config

    # --- lifecycle -------------------------------------------------------- #
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        ...

    # --- data ------------------------------------------------------------- #
    @abstractmethod
    def read_raw(self) -> bytes:
        """Return the raw input-assembly byte array from the device."""
        ...

    def read_all(self) -> List[SensorReading]:
        """Read once and parse into per-channel readings."""
        return self.parse(self.read_raw())

    # --- parsing (shared) ------------------------------------------------- #
    def parse(self, raw: bytes) -> List[SensorReading]:
        """Decode a raw assembly buffer into one reading per channel."""
        dm: DataMap = self.config.datamap
        order = dm.byte_order
        out: List[SensorReading] = []

        for ch in range(self.config.channels.count):
            base = dm.data_offset + ch * dm.stride
            r = SensorReading(channel=ch, name=self.config.channels.name(ch))
            r.raw = raw[base: base + dm.stride] if 0 <= base < len(raw) else b""

            raw_fields = {}
            for fname, spec in dm.fields.items():
                raw_fields[fname] = read_scalar(raw, base + spec.offset, spec.type, order)

            def scaled(fname: str):
                iv = raw_fields.get(fname)
                if iv is None or iv in dm.invalid_values:
                    return None
                return iv * dm.fields[fname].scale

            v_raw = raw_fields.get("value")
            r.valid = v_raw is not None and v_raw not in dm.invalid_values
            r.value = scaled("value")
            r.peak = scaled("peak")
            r.bottom = scaled("bottom")

            if "pp" in dm.fields:
                r.pp = scaled("pp")
            elif r.peak is not None and r.bottom is not None:
                r.pp = r.peak - r.bottom

            if dm.status.enabled:
                sword = read_scalar(raw, base + dm.status.offset, dm.status.type, order)
                r.judgment = _judgment_from_status(sword, dm.status.bits)

            out.append(r)
        return out
