#!/usr/bin/env python3
"""Command-line tester — run this on the PC that can reach the sensor unit.

It opens a TCP socket, sends the command (default ``M0``) and prints the raw
reply *and* the values decoded with the current settings. Use it to confirm the
IP/port and to see the real response format so the parser/scale in
``config.yaml`` can be matched to your device.

Examples:
    python tools/test_connection.py
    python tools/test_connection.py --ip 192.168.0.10 --port 8501
    python tools/test_connection.py --command M0 --watch
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Allow running as `python tools/test_connection.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensor.config import AppConfig                       # noqa: E402
from sensor.driver.keyence_socket import KeyenceSocketDriver  # noqa: E402


def show_once(driver: KeyenceSocketDriver, cfg: AppConfig) -> None:
    readings = driver.read_all()

    print("\n=== Raw exchange (gửi >>> / nhận <<<) ===")
    print(driver.last_exchange or "(trống)")

    print("\n=== Decoded ===")
    dec = cfg.display.decimals
    print(f"{'CH':<6}{'value':>14}{'peak':>14}{'bottom':>14}{'pp':>14}  status")
    for r in readings:
        def f(x):
            return "---" if x is None else f"{x:.{dec}f}"
        status = "OK" if r.valid else "INVALID"
        print(f"{r.name:<6}{f(r.value):>14}{f(r.peak):>14}"
              f"{f(r.bottom):>14}{f(r.pp):>14}  {status} {r.judgment.value}")
    print(f"(unit: {cfg.display.unit})")


def main() -> int:
    p = argparse.ArgumentParser(description="KEYENCE TCP socket connection test")
    p.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"))
    p.add_argument("--ip", help="Ghi đè IP trong config")
    p.add_argument("--port", type=int, help="Ghi đè cổng TCP")
    p.add_argument("--command", help="Ghi đè lệnh gửi đi (mặc định M0)")
    p.add_argument("--watch", action="store_true", help="Đọc liên tục đến khi Ctrl+C")
    p.add_argument("--interval", type=float, default=0.5, help="Chu kỳ khi --watch (giây)")
    args = p.parse_args()

    cfg = AppConfig.load(args.config)
    if args.ip:
        cfg.device.ip = args.ip
    if args.port:
        cfg.device.port = args.port
    if args.command:
        cfg.protocol.command = args.command

    driver = KeyenceSocketDriver(cfg)
    print(f"Connecting to {cfg.device.ip}:{cfg.device.port} "
          f"(command {cfg.protocol.command!r}, term {cfg.device.terminator}) ...")
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
