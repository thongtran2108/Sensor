"""KEYENCE DL-EN1 (EtherNet/IP) driver.

The DL-EN1 aggregates the measured values of every GT2/IB/IG amplifier on the
DIN-rail bus and exposes them through an EtherNet/IP *input assembly*. This
driver reads that assembly with an explicit CIP message
(``Get_Attribute_Single`` on the Assembly object, class ``0x04``) and returns
the raw bytes; decoding into per-channel values is done by the shared
``SensorDriver.parse`` using the configurable data map.

Why explicit messaging: it needs no real-time I/O scanner on the PC side and
works from an ordinary office/laptop NIC. If your unit only serves the data
over cyclic (implicit) I/O, the assembly instance / attribute may differ --
adjust ``config.yaml`` and verify with ``tools/test_connection.py``.
"""
from __future__ import annotations

from .base import SensorDriver

# Assembly object class code (CIP).
_ASSEMBLY_CLASS = 0x04


class KeyenceDLEN1Driver(SensorDriver):
    def __init__(self, config):
        super().__init__(config)
        self._drv = None  # pycomm3.CIPDriver

    # --- lifecycle -------------------------------------------------------- #
    def connect(self) -> None:
        # Imported lazily so the UI can start even if pycomm3 is missing.
        from pycomm3 import CIPDriver

        dev = self.config.device
        drv = CIPDriver(dev.ip)
        drv.open()
        self._drv = drv

    def disconnect(self) -> None:
        if self._drv is not None:
            try:
                self._drv.close()
            finally:
                self._drv = None

    @property
    def connected(self) -> bool:
        return self._drv is not None and getattr(self._drv, "connected", False)

    # --- data ------------------------------------------------------------- #
    def read_raw(self) -> bytes:
        if not self.connected:
            raise ConnectionError("Not connected to DL-EN1")

        from pycomm3 import Services

        dev = self.config.device
        tag = self._drv.generic_message(
            service=Services.get_attribute_single,
            class_code=_ASSEMBLY_CLASS,
            instance=dev.assembly_instance,
            attribute=dev.attribute,
            data_type=None,                 # None -> return raw bytes
            connected=not dev.unconnected,
            unconnected_send=dev.unconnected,
            route_path=dev.route_path,
            name="read_assembly",
        )
        if not tag:
            raise IOError(f"CIP read failed: {tag.error}")

        value = tag.value
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if value is None:
            return b""
        # Defensive fallback: some pycomm3 versions wrap raw data.
        return bytes(value)
