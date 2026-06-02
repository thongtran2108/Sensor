"""Data models shared between the driver and the UI."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Judgment(str, Enum):
    """Tolerance judgment reported by the amplifier (best-effort)."""

    HI = "HI"      # over upper limit
    GO = "GO"      # within tolerance (OK)
    LO = "LO"      # under lower limit
    NONE = "--"    # not available / not configured


@dataclass
class SensorReading:
    """One sample for a single channel (amplifier) of the DL-EN1 bus.

    All numeric fields are *scaled* engineering values (e.g. millimetres).
    A field is ``None`` when it is not configured or the raw value is an
    over-range / invalid sentinel.
    """

    channel: int                       # hardware channel index: CH0, CH1, ...
    name: str                          # display name (default "CH0", "CH1", ...)
    value: Optional[float] = None      # current measured value
    peak: Optional[float] = None       # peak (max hold)
    bottom: Optional[float] = None     # bottom (min hold)
    pp: Optional[float] = None         # peak-to-peak (= peak - bottom)
    judgment: Judgment = Judgment.NONE
    valid: bool = False                # True when the current value is usable
    raw: Optional[bytes] = None        # raw per-channel bytes (debug / hex view)

    def fmt(self, field: str, decimals: int) -> str:
        """Format a numeric field for display, or '---' if unavailable."""
        v = getattr(self, field)
        if v is None:
            return "---"
        return f"{v:.{decimals}f}"
