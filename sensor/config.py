"""Configuration model loaded from ``config.yaml``.

Every layout-dependent value (assembly instance, byte offsets, scaling, ...)
lives here so the program can be matched to a specific DL-EN1 configuration
*without touching the code*. See ``config.yaml`` for inline documentation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


# --------------------------------------------------------------------------- #
# Field / data-map specs
# --------------------------------------------------------------------------- #
@dataclass
class FieldSpec:
    """One numeric field inside a channel's data block."""

    offset: int          # byte offset relative to the start of the channel block
    type: str = "int32"  # int8/uint8/int16/uint16/int32/uint32/int64/uint64/float32/float64
    scale: float = 1.0   # engineering value = raw * scale

    @classmethod
    def from_dict(cls, d: dict) -> "FieldSpec":
        return cls(offset=int(d["offset"]),
                   type=str(d.get("type", "int32")),
                   scale=float(d.get("scale", 1.0)))


@dataclass
class StatusSpec:
    """Optional status word used to derive the HI/GO/LO judgment."""

    enabled: bool = False
    offset: int = 0
    type: str = "uint16"
    bits: Dict[str, int] = field(default_factory=dict)  # e.g. {hi:0, go:1, lo:2, alarm:7}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "StatusSpec":
        d = d or {}
        return cls(enabled=bool(d.get("enabled", False)),
                   offset=int(d.get("offset", 0)),
                   type=str(d.get("type", "uint16")),
                   bits={k: int(v) for k, v in (d.get("bits") or {}).items()})


@dataclass
class DataMap:
    """How the flat input-assembly byte array maps to per-channel values."""

    data_offset: int = 0          # bytes to skip before CH0's block (header)
    stride: int = 16              # bytes per channel block
    byte_order: str = "little"    # "little" or "big"
    fields: Dict[str, FieldSpec] = field(default_factory=dict)  # value/peak/bottom/pp
    status: StatusSpec = field(default_factory=StatusSpec)
    invalid_values: List[int] = field(default_factory=lambda: [
        999999999, -999999999, 2147483647, -2147483648,
    ])

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DataMap":
        d = d or {}
        fields = {k: FieldSpec.from_dict(v) for k, v in (d.get("fields") or {}).items()}
        return cls(
            data_offset=int(d.get("data_offset", 0)),
            stride=int(d.get("stride", 16)),
            byte_order=str(d.get("byte_order", "little")),
            fields=fields,
            status=StatusSpec.from_dict(d.get("status")),
            invalid_values=list(d.get("invalid_values", [
                999999999, -999999999, 2147483647, -2147483648])),
        )


@dataclass
class DeviceCfg:
    ip: str = "192.168.0.10"
    assembly_instance: int = 100   # input (T->O) assembly instance of the DL-EN1
    attribute: int = 3             # Assembly object data attribute
    unconnected: bool = True       # use unconnected explicit messaging
    route_path: bool = False       # CIP routing path (False = talk directly to device)
    timeout: float = 5.0

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DeviceCfg":
        d = d or {}
        return cls(
            ip=str(d.get("ip", "192.168.0.10")),
            assembly_instance=int(d.get("assembly_instance", 100)),
            attribute=int(d.get("attribute", 3)),
            unconnected=bool(d.get("unconnected", True)),
            route_path=bool(d.get("route_path", False)),
            timeout=float(d.get("timeout", 5.0)),
        )


@dataclass
class ChannelsCfg:
    count: int = 8
    names: Dict[int, str] = field(default_factory=dict)  # optional CH index -> custom name

    def name(self, ch: int) -> str:
        return self.names.get(ch, f"CH{ch}")

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ChannelsCfg":
        d = d or {}
        names = {int(k): str(v) for k, v in (d.get("names") or {}).items()}
        return cls(count=int(d.get("count", 8)), names=names)


@dataclass
class DisplayCfg:
    unit: str = "mm"
    decimals: int = 4

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DisplayCfg":
        d = d or {}
        return cls(unit=str(d.get("unit", "mm")), decimals=int(d.get("decimals", 4)))


@dataclass
class PollingCfg:
    interval_ms: int = 200

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "PollingCfg":
        d = d or {}
        return cls(interval_ms=int(d.get("interval_ms", 200)))


@dataclass
class AppConfig:
    device: DeviceCfg = field(default_factory=DeviceCfg)
    channels: ChannelsCfg = field(default_factory=ChannelsCfg)
    datamap: DataMap = field(default_factory=DataMap)
    display: DisplayCfg = field(default_factory=DisplayCfg)
    polling: PollingCfg = field(default_factory=PollingCfg)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "AppConfig":
        d = d or {}
        return cls(
            device=DeviceCfg.from_dict(d.get("device")),
            channels=ChannelsCfg.from_dict(d.get("channels")),
            datamap=DataMap.from_dict(d.get("datamap")),
            display=DisplayCfg.from_dict(d.get("display")),
            polling=PollingCfg.from_dict(d.get("polling")),
        )

    @classmethod
    def load(cls, path: str) -> "AppConfig":
        """Load config from a YAML file; fall back to defaults if missing."""
        if not path or not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)
