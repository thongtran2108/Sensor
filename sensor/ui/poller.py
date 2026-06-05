"""Background polling worker.

Network I/O must never run on the GUI thread or the window freezes. This
``QObject`` is moved onto its own ``QThread``; a ``QTimer`` living in that
thread drives ``read_all`` and the results are delivered to the UI through
queued signals.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from ..driver.base import SensorDriver


class PollWorker(QObject):
    readings_ready = Signal(list)        # List[SensorReading]
    raw_ready = Signal(str)              # request/response log (raw text)
    error = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self, driver: SensorDriver, interval_ms: int = 200, parent=None):
        super().__init__(parent)
        self._driver = driver
        self._interval = max(20, int(interval_ms))
        self._timer: QTimer | None = None

    # Called inside the worker thread (via a queued signal connection).
    @Slot()
    def open(self) -> None:
        try:
            self._driver.connect()
        except Exception as exc:  # noqa: BLE001 - surface any connect error to UI
            self.error.emit(f"Không kết nối được: {exc}")
            self.connection_changed.emit(False)
            return

        self.connection_changed.emit(True)
        if self._timer is None:
            self._timer = QTimer()
            self._timer.setTimerType(Qt.PreciseTimer)
            self._timer.timeout.connect(self._poll)
        self._timer.start(self._interval)

    @Slot()
    def close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        try:
            self._driver.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self.connection_changed.emit(False)

    @Slot(int)
    def set_interval(self, ms: int) -> None:
        self._interval = max(20, int(ms))
        if self._timer is not None and self._timer.isActive():
            self._timer.start(self._interval)

    @Slot()
    def _poll(self) -> None:
        try:
            readings = self._driver.read_all()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Lỗi đọc dữ liệu: {exc}")
            return

        self.readings_ready.emit(readings)
        raw = getattr(self._driver, "last_exchange", "")
        if raw:
            self.raw_ready.emit(raw)
