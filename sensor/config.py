"""Configuration model loaded from ``config.yaml``.

The transport is a plain TCP socket speaking KEYENCE's ASCII command protocol
(e.g. send ``M0\\r\\n``, read the reply). Everything that depends on the device
(IP, port, command text, line terminator, value scaling, ...) lives here so the
program can be matched to a device *without touching the code*.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

# Named line terminators -> actual control characters. Using names avoids the
# YAML single/double-quote escaping pitfalls around "\r\n".
TERMINATORS = {"CRLF": "\r\n", "CR": "\r", "LF": "\n"}


def resolve_terminator(value: str) -> str:
    """Turn 'CRLF' / 'CR' / 'LF' or a literal like '\\r\\n' into real chars."""
    if value in TERMINATORS:
        return TERMINATORS[value]
    # interpret backslash escapes such as "\r\n" written literally
    return value.encode("utf-8").decode("unicode_escape")


@dataclass
class DeviceCfg:
    ip: str = "192.168.0.10"
    port: int = 8501                 # TCP port of the command server (custom)
    timeout: float = 2.0             # socket timeout in seconds
    encoding: str = "ascii"          # KEYENCE command protocol is ASCII
    terminator: str = "CRLF"         # CRLF | CR | LF | literal e.g. "\r\n"

    @property
    def term(self) -> str:
        return resolve_terminator(self.terminator)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DeviceCfg":
        d = d or {}
        return cls(
            ip=str(d.get("ip", "192.168.0.10")),
            port=int(d.get("port", 8501)),
            timeout=float(d.get("timeout", 2.0)),
            encoding=str(d.get("encoding", "ascii")),
            terminator=str(d.get("terminator", "CRLF")),
        )


@dataclass
class ProtocolCfg:
    """How to ask for values and how to read the reply."""

    # "all_in_one": send `command` once, reply has one value per channel
    #               (comma separated).
    # "per_channel": send `command_template` once per channel (e.g. M0, M1, ...)
    read_mode: str = "all_in_one"
    command: str = "M0"                     # value command (all_in_one)
    command_template: str = "M{n}"          # per-channel command (per_channel)
    extra_commands: Dict[str, str] = field(default_factory=dict)  # field -> command
    strip_echo: bool = True                 # drop a leading echo token like "M0"
    scale: float = 1.0                      # value = parsed_number * scale
    invalid_tokens: List[str] = field(default_factory=lambda: [
        "F", "FFFFFF", "-FFFFFF", "------", "OVER", "FFFF",
    ])
    invalid_values: List[float] = field(default_factory=lambda: [
        999999999, -999999999,
    ])

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ProtocolCfg":
        d = d or {}
        return cls(
            read_mode=str(d.get("read_mode", "all_in_one")),
            command=str(d.get("command", "M0")),
            command_template=str(d.get("command_template", "M{n}")),
            extra_commands={str(k): str(v) for k, v in (d.get("extra_commands") or {}).items()},
            strip_echo=bool(d.get("strip_echo", True)),
            scale=float(d.get("scale", 1.0)),
            invalid_tokens=list(d.get("invalid_tokens", [
                "F", "FFFFFF", "-FFFFFF", "------", "OVER", "FFFF"])),
            invalid_values=list(d.get("invalid_values", [999999999, -999999999])),
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
    protocol: ProtocolCfg = field(default_factory=ProtocolCfg)
    channels: ChannelsCfg = field(default_factory=ChannelsCfg)
    display: DisplayCfg = field(default_factory=DisplayCfg)
    polling: PollingCfg = field(default_factory=PollingCfg)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "AppConfig":
        d = d or {}
        return cls(
            device=DeviceCfg.from_dict(d.get("device")),
            protocol=ProtocolCfg.from_dict(d.get("protocol")),
            channels=ChannelsCfg.from_dict(d.get("channels")),
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
