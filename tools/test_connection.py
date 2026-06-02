#!/usr/bin/env python3
"""Command-line diagnostic for the DL-EN1 — run this on the PC wired to the unit.

It connects over EtherNet/IP, reads the input assembly and prints both a raw
hex dump *and* the values decoded with the current data map. Use it to verify
connectivity and to line the byte offsets in ``config.yaml`` up with the real
device (move a probe and watch which bytes change).

Examples:
    python tools/test_connection.py
    python tools/test_connection.py --ip 192.168.0.10 --instance 100
    python tools/test_connection.py --watch          # poll until Ctrl+C
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Allow running as `python tools/test_connection.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensor.config import AppConfig          # noqa: E402
from sensor.driver.keyence_dlen1 import KeyenceDLEN1Driver  # noqa: E402


def hex_dump(data: bytes, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:04X}  {hex_part:<{width * 3}}  |{ascii_part}|")
    return "\n".join(lines)


def show_once(driver: KeyenceDLEN1Driver, cfg: AppConfig) -> None:
    raw = driver.read_raw()
    print(f"\n=== Raw input assembly ({len(raw)} bytes) ===")
    print(hex_dump(raw))

    print("\n=== Decoded with current data map ===")
    dec = cfg.display.decimals
    unit = cfg.display.unit
    print(f"{'CH':<6}{'value':>14}{'peak':>14}{'bottom':>14}{'pp':>14}  status")
    for r in driver.parse(raw):
        def f(x):
            return "---" if x is None else f"{x:.{dec}f}"
        status = "OK" if r.valid else "INVALID"
        print(f"{r.name:<6}{f(r.value):>14}{f(r.peak):>14}"
              f"{f(r.bottom):>14}{f(r.pp):>14}  {status} {r.judgment.value}")
    print(f"(unit: {unit})")


def main() -> int:
    p = argparse.ArgumentParser(description="DL-EN1 EtherNet/IP connection test")
    p.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"))
    p.add_argument("--ip", help="Ghi đè IP trong config")
    p.add_argument("--instance", type=int, help="Ghi đè input assembly instance")
    p.add_argument("--watch", action="store_true", help="Đọc liên tục đến khi Ctrl+C")
    p.add_argument("--interval", type=float, default=0.5, help="Chu kỳ khi --watch (giây)")
    args = p.parse_args()

    cfg = AppConfig.load(args.config)
    if args.ip:
        cfg.device.ip = args.ip
    if args.instance:
        cfg.device.assembly_instance = args.instance

    driver = KeyenceDLEN1Driver(cfg)
    print(f"Connecting to {cfg.device.ip} "
          f"(assembly instance {cfg.device.assembly_instance}) ...")
    try:
        driver.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"!! Connect failed: {exc}", file=sys.stderr)
        return 1
    print("Connected.")

    try:
        if args.watch:
            while True:
                show_once(driver, cfg)
                time.sleep(max(0.05, args.interval))
        else:
            show_once(driver, cfg)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:  # noqa: BLE001
        print(f"!! Read failed: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
