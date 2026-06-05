"""Abstract driver interface.

Keeping the UI behind this interface means a different transport (the TCP
command socket here, RS-232C, a recorded-file replayer, ...) can be dropped in
later without touching the GUI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..config import AppConfig
from ..models import SensorReading


class SensorDriver(ABC):
    """Common interface every transport implements."""

    def __init__(self, config: AppConfig):
        self.config = config
        # Human-readable log of the last request/response, shown in the UI's
        # raw panel and used to verify/calibrate the response parsing.
        self.last_exchange: str = ""

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
    def read_all(self) -> List[SensorReading]:
        """Read every channel once and return one reading per channel."""
        ...
