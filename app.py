#!/usr/bin/env python3
"""Entry point for the KEYENCE TCP-socket sensor test GUI.

Usage:
    python app.py [--config config.yaml]
"""
from __future__ import annotations

import argparse
import os
import sys

from sensor.config import AppConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="KEYENCE TCP-socket sensor monitor")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "config.yaml"),
        help="Đường dẫn file cấu hình YAML (mặc định: config.yaml)",
    )
    args = parser.parse_args()

    config = AppConfig.load(args.config)

    # Import Qt only here so `--help` works without a display.
    from PySide6.QtWidgets import QApplication
    from sensor.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow(config)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
