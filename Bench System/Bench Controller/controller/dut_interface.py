"""
DUT (Device Under Test) interface.

Handles reading from the water meter being tested, supporting two modes:
  1. RS485 Auto-Read: Read totalizer register via Modbus (addr 20 on Bus 1)
  2. Manual Entry: Operator enters before/after readings on touch keypad

The DUT volume is always: after_reading - before_reading (in litres).
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# DUT Modbus address on Bus 1
DUT_MODBUS_ADDR = 20
DUT_BUS = 1
DUT_TOTALIZER_REG = 0


class DUTMode(Enum):
    RS485 = 'rs485'
    MANUAL = 'manual'


class DUTState(Enum):
    IDLE = 'IDLE'
    WAITING_BEFORE = 'WAITING_BEFORE'
    MEASURING = 'MEASURING'
    WAITING_AFTER = 'WAITING_AFTER'
    COMPLETE = 'COMPLETE'
    ERROR = 'ERROR'


@dataclass
class DUTReading:
    """A pair of before/after DUT readings for one Q-point."""
    before_l: float = 0.0
    after_l: float = 0.0
    volume_l: float = 0.0
    mode: DUTMode = DUTMode.RS485
    timestamp_before: float = 0.0
    timestamp_after: float = 0.0

    @property
    def is_valid(self) -> bool:
        return self.after_l >= self.before_l and self.timestamp_after > 0


class DUTInterface:
    """
    High-level DUT interface.

    Usage (RS485 auto-read):
        dut = DUTInterface(backend='simulator', mode=DUTMode.RS485)
        dut.init_backend()

        before = dut.read_before()     # Record totalizer before collection
        # ... water flows through DUT ...
        after = dut.read_after()        # Record totalizer after collection
        reading = dut.get_reading()     # Get DUTReading with volume

    Usage (Manual entry):
        dut = DUTInterface(mode=DUTMode.MANUAL)
        dut.set_before_reading(1234.567)  # Operator enters before value
        # ... water flows through DUT ...
        dut.set_after_reading(1244.789)   # Operator enters after value
        reading = dut.get_reading()
    """

    def __init__(
        self,
        backend: str = 'simulator',
        mode: DUTMode = DUTMode.RS485,
    ):
        self._backend = backend
        self._mode = mode
        self._lock = threading.RLock()
        self._simulator = None
        self._serial_handler = None

        # State
        self._state = DUTState.IDLE
        self._before: float = 0.0
        self._after: float = 0.0
        self._timestamp_before: float = 0.0
        self._timestamp_after: float = 0.0

    def init_backend(self):
        """Initialise the backend for RS485 mode."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            logger.info("DUTInterface using SIMULATOR backend")
        else:
            logger.info("DUTInterface using REAL backend")

    def set_serial_handler(self, handler):
        """Set the serial handler for real hardware mode."""
        self._serial_handler = handler

    @property
    def mode(self) -> DUTMode:
        return self._mode

    def set_mode(self, mode: DUTMode):
        """Switch between RS485 and MANUAL mode."""
        with self._lock:
            self._mode = mode
            self.reset()
            logger.info("DUT mode set to %s", mode.value)

    @property
    def state(self) -> DUTState:
        return self._state

    # ------------------------------------------------------------------
    #  RS485 auto-read operations
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """Check if DUT meter is responding on RS485."""
        if self._mode != DUTMode.RS485:
            return False

        if self._backend == 'simulator':
            return self._simulator.dut_connected if self._simulator else False

        # Real: try a read
        reading = self._read_totalizer()
        return reading is not None

    def read_totalizer(self) -> float | None:
        """
        Read current DUT totalizer value via RS485.

        Returns totalizer in litres, or None if read failed.
        """
        if self._mode != DUTMode.RS485:
            logger.warning("read_totalizer called in manual mode")
            return None
        return self._read_totalizer()

    def _read_totalizer(self) -> float | None:
        """Internal totalizer read."""
        if self._backend == 'simulator':
            if self._simulator and self._simulator.dut_connected:
                return self._simulator.dut_totalizer
            return None

        # Real hardware
        if not self._serial_handler:
            return None
        try:
            result = self._serial_handler.modbus_read(
                DUT_BUS, DUT_MODBUS_ADDR, DUT_TOTALIZER_REG, 2
            )
            if result.get('ok'):
                return result['data'].get('value')
            return None
        except Exception:
            logger.debug("DUT totalizer read failed")
            return None

    def read_before(self) -> float | None:
        """
        Record the 'before' totalizer reading (RS485 mode).

        Returns the totalizer value, or None on failure.
        """
        with self._lock:
            if self._mode == DUTMode.RS485:
                value = self._read_totalizer()
                if value is not None:
                    self._before = value
                    self._timestamp_before = time.time()
                    self._state = DUTState.MEASURING
                    logger.info("DUT before reading: %.4f L", value)
                    return value
                else:
                    self._state = DUTState.ERROR
                    logger.error("Failed to read DUT before totalizer")
                    return None
            else:
                # Manual mode: enter WAITING_BEFORE state
                self._state = DUTState.WAITING_BEFORE
                logger.info("DUT waiting for manual BEFORE entry")
                return None

    def read_after(self) -> float | None:
        """
        Record the 'after' totalizer reading (RS485 mode).

        Returns the totalizer value, or None on failure.
        """
        with self._lock:
            if self._mode == DUTMode.RS485:
                value = self._read_totalizer()
                if value is not None:
                    self._after = value
                    self._timestamp_after = time.time()
                    self._state = DUTState.COMPLETE
                    logger.info("DUT after reading: %.4f L (volume=%.4f L)",
                                value, self._after - self._before)
                    return value
                else:
                    self._state = DUTState.ERROR
                    logger.error("Failed to read DUT after totalizer")
                    return None
            else:
                # Manual mode: enter WAITING_AFTER state
                self._state = DUTState.WAITING_AFTER
                logger.info("DUT waiting for manual AFTER entry")
                return None

    # ------------------------------------------------------------------
    #  Manual entry operations
    # ------------------------------------------------------------------

    def set_before_reading(self, value: float) -> bool:
        """
        Set the manual 'before' reading (operator enters from DUT display).

        Args:
            value: Totalizer reading in litres.

        Returns True on success.
        """
        with self._lock:
            if value < 0:
                logger.error("Invalid before reading: %.4f (must be >= 0)", value)
                return False
            self._before = value
            self._timestamp_before = time.time()
            self._state = DUTState.MEASURING
            logger.info("DUT manual before: %.4f L", value)
            return True

    def set_after_reading(self, value: float) -> bool:
        """
        Set the manual 'after' reading (operator enters from DUT display).

        Args:
            value: Totalizer reading in litres (must be >= before reading).

        Returns True on success.
        """
        with self._lock:
            if value < self._before:
                logger.error(
                    "Invalid after reading: %.4f < before %.4f",
                    value, self._before,
                )
                return False
            self._after = value
            self._timestamp_after = time.time()
            self._state = DUTState.COMPLETE
            logger.info("DUT manual after: %.4f L (volume=%.4f L)",
                        value, self._after - self._before)
            return True

    # ------------------------------------------------------------------
    #  Results
    # ------------------------------------------------------------------

    def get_reading(self) -> DUTReading:
        """
        Get the current DUT reading (before/after/volume).

        Returns DUTReading. Check is_valid to confirm completeness.
        """
        with self._lock:
            volume = max(0, self._after - self._before)
            return DUTReading(
                before_l=self._before,
                after_l=self._after,
                volume_l=volume,
                mode=self._mode,
                timestamp_before=self._timestamp_before,
                timestamp_after=self._timestamp_after,
            )

    @property
    def dut_volume_l(self) -> float:
        """Shortcut: DUT volume = after - before."""
        with self._lock:
            return max(0, self._after - self._before)

    def reset(self):
        """Reset the interface for a new Q-point measurement."""
        with self._lock:
            self._before = 0.0
            self._after = 0.0
            self._timestamp_before = 0.0
            self._timestamp_after = 0.0
            self._state = DUTState.IDLE
