"""Main window for the sensor test GUI."""
from __future__ import annotations

import csv
import datetime as _dt
from typing import List, Optional

from PySide6.QtCore import QMetaObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
)

from ..config import AppConfig
from ..driver.keyence_socket import KeyenceSocketDriver
from ..models import SensorReading
from .poller import PollWorker

# Table columns
COL_CH, COL_VALUE, COL_STATUS = range(3)


class MainWindow(QMainWindow):
    # Signals to the worker (delivered to the worker thread as queued calls).
    request_open = Signal()
    request_close = Signal()
    request_interval = Signal(int)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self._thread: Optional[QThread] = None
        self._worker: Optional[PollWorker] = None
        self._driver: Optional[KeyenceSocketDriver] = None
        self._connected = False

        self._csv_file = None
        self._csv_writer = None
        self._last_update: Optional[_dt.datetime] = None

        self.setWindowTitle("KEYENCE Sensor Monitor — TCP socket")
        self.resize(1000, 560)

        self._build_toolbar()
        self._build_table()
        self._build_hex_dock()
        self._build_statusbar()
        self._update_conn_ui(False)

    # ------------------------------------------------------------------ UI -- #
    def _build_toolbar(self) -> None:
        tb = QToolBar("Kết nối")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel(" IP: "))
        self.ip_edit = QLineEdit(self.config.device.ip)
        self.ip_edit.setFixedWidth(120)
        tb.addWidget(self.ip_edit)

        tb.addWidget(QLabel("  Port: "))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.config.device.port)
        self.port_spin.setToolTip("Cổng TCP của thiết bị (tự đặt)")
        tb.addWidget(self.port_spin)

        tb.addWidget(QLabel("  Lệnh: "))
        self.command_edit = QLineEdit(self.config.protocol.command)
        self.command_edit.setFixedWidth(70)
        self.command_edit.setToolTip("Lệnh gửi đi (terminator CR/LF tự thêm), ví dụ M0")
        tb.addWidget(self.command_edit)

        tb.addWidget(QLabel("  Chu kỳ (ms): "))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(20, 10000)
        self.interval_spin.setSingleStep(20)
        self.interval_spin.setValue(self.config.polling.interval_ms)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        tb.addWidget(self.interval_spin)

        tb.addSeparator()
        self.connect_btn = QPushButton("Kết nối")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        tb.addWidget(self.connect_btn)

        tb.addSeparator()
        self.csv_chk = QCheckBox("Ghi CSV")
        self.csv_chk.toggled.connect(self._on_csv_toggled)
        tb.addWidget(self.csv_chk)

        self.hex_chk = QCheckBox("Xem dữ liệu thô")
        self.hex_chk.toggled.connect(lambda on: self.hex_dock.setVisible(on))
        tb.addWidget(self.hex_chk)

    def _build_table(self) -> None:
        unit = self.config.display.unit
        headers = ["Kênh", f"Giá trị ({unit})", "Trạng thái"]
        n = self.config.channels.count
        self.table = QTableWidget(n, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        mono = QFont("Monospace")
        mono.setStyleHint(QFont.TypeWriter)

        for ch in range(n):
            name_item = QTableWidgetItem(self.config.channels.name(ch))
            name_item.setTextAlignment(Qt.AlignCenter)
            f = name_item.font()
            f.setBold(True)
            name_item.setFont(f)
            self.table.setItem(ch, COL_CH, name_item)

            value_item = QTableWidgetItem("---")
            value_item.setFont(mono)
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(ch, COL_VALUE, value_item)

            status_item = QTableWidgetItem("--")
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(ch, COL_STATUS, status_item)

        self.setCentralWidget(self.table)

    def _build_hex_dock(self) -> None:
        self.hex_dock = QDockWidget("Giao tiếp thô (lệnh gửi / phản hồi)", self)
        self.hex_view = QPlainTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setFont(QFont("Monospace"))
        self.hex_dock.setWidget(self.hex_view)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.hex_dock)
        self.hex_dock.setVisible(False)

    def _build_statusbar(self) -> None:
        self.conn_label = QLabel()
        self.update_label = QLabel("")
        self.statusBar().addWidget(self.conn_label, 1)
        self.statusBar().addPermanentWidget(self.update_label)

    # -------------------------------------------------------------- actions -- #
    def _on_connect_clicked(self) -> None:
        if self._connected or self._thread is not None:
            self.request_close.emit()
            return
        self._start_connection()

    def _start_connection(self) -> None:
        # Pull the latest values from the toolbar into the config.
        self.config.device.ip = self.ip_edit.text().strip()
        self.config.device.port = self.port_spin.value()
        self.config.protocol.command = self.command_edit.text().strip() or "M0"
        self.config.polling.interval_ms = self.interval_spin.value()

        self._driver = KeyenceSocketDriver(self.config)
        self._worker = PollWorker(self._driver, self.config.polling.interval_ms)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        # UI -> worker
        self.request_open.connect(self._worker.open)
        self.request_close.connect(self._worker.close)
        self.request_interval.connect(self._worker.set_interval)
        # worker -> UI
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.readings_ready.connect(self._on_readings)
        self._worker.raw_ready.connect(self._on_raw)
        self._worker.error.connect(self._on_error)

        self._thread.start()
        self.connect_btn.setEnabled(False)
        self.conn_label.setText(f"Đang kết nối tới {self.config.device.ip} ...")
        self.request_open.emit()

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None
        self._driver = None

    def _on_interval_changed(self, ms: int) -> None:
        self.config.polling.interval_ms = ms
        if self._connected:
            self.request_interval.emit(ms)

    # ------------------------------------------------------------- signals -- #
    def _on_connection_changed(self, ok: bool) -> None:
        was_connected = self._connected
        self._connected = ok
        self._update_conn_ui(ok)
        if ok:
            self.conn_label.setText(f"● Đã kết nối — {self.config.device.ip}")
        else:
            # Either a connect failure or a user-initiated disconnect; in both
            # cases the worker thread is finished with its work.
            self._teardown_thread()
            self._mark_all_stale()
            # On a failed connect, keep the error message set by _on_error;
            # only show the plain "disconnected" text for a clean disconnect.
            if was_connected:
                self.conn_label.setText("○ Đã ngắt kết nối")

    def _on_readings(self, readings: List[SensorReading]) -> None:
        dec = self.config.display.decimals
        for r in readings:
            if r.channel >= self.table.rowCount():
                continue
            self._set_num(r.channel, COL_VALUE, r.fmt("value", dec), r.valid)

            sitem = self.table.item(r.channel, COL_STATUS)
            sitem.setText("OK" if r.valid else "Lỗi/Tràn")
            sitem.setForeground(QColor("#1b8a3a") if r.valid else QColor("#c0392b"))

        self._last_update = _dt.datetime.now()
        self.update_label.setText("Cập nhật: " + self._last_update.strftime("%H:%M:%S.%f")[:-3])
        self._write_csv(readings)

    def _on_raw(self, raw: str) -> None:
        if self.hex_dock.isVisible():
            self.hex_view.setPlainText(raw)

    def _on_error(self, msg: str) -> None:
        self.conn_label.setText("⚠ " + msg)

    # -------------------------------------------------------------- helpers -- #
    def _set_num(self, row: int, col: int, text: str, valid: bool) -> None:
        item = self.table.item(row, col)
        item.setText(text)
        item.setForeground(QColor("#202020") if valid else QColor("#9aa0a6"))

    def _mark_all_stale(self) -> None:
        for ch in range(self.table.rowCount()):
            self._set_num(ch, COL_VALUE, "---", False)
            self.table.item(ch, COL_STATUS).setText("--")

    def _update_conn_ui(self, connected: bool) -> None:
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Ngắt kết nối" if connected else "Kết nối")
        for w in (self.ip_edit, self.port_spin, self.command_edit):
            w.setEnabled(not connected)

    # ------------------------------------------------------------------ CSV -- #
    def _on_csv_toggled(self, on: bool) -> None:
        if on:
            default = "sensor_log_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
            path, _ = QFileDialog.getSaveFileName(self, "Lưu log CSV", default, "CSV (*.csv)")
            if not path:
                self.csv_chk.setChecked(False)
                return
            try:
                self._csv_file = open(path, "w", newline="", encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "CSV", f"Không mở được file:\n{exc}")
                self.csv_chk.setChecked(False)
                return
            self._csv_writer = csv.writer(self._csv_file)
            header = ["timestamp"]
            for ch in range(self.config.channels.count):
                header.append(self.config.channels.name(ch))   # one value column per channel
            self._csv_writer.writerow(header)
        else:
            self._close_csv()

    def _write_csv(self, readings: List[SensorReading]) -> None:
        if self._csv_writer is None:
            return
        dec = self.config.display.decimals

        def fmt(x):
            return "" if x is None else round(x, dec)   # empty cell = invalid/over-range

        row = [_dt.datetime.now().isoformat(timespec="milliseconds")]
        by_ch = {r.channel: r for r in readings}
        for ch in range(self.config.channels.count):
            r = by_ch.get(ch)
            row.append(fmt(r.value) if r is not None else "")
        self._csv_writer.writerow(row)
        self._csv_file.flush()

    def _close_csv(self) -> None:
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            finally:
                self._csv_file = None
                self._csv_writer = None

    # ------------------------------------------------------------- shutdown -- #
    def closeEvent(self, event) -> None:
        # Stop the timer + disconnect *inside* the worker thread before we tear
        # the thread down, so no QTimer is destroyed across threads.
        if self._worker is not None and self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "close", Qt.BlockingQueuedConnection)
        self._teardown_thread()
        self._close_csv()
        event.accept()
