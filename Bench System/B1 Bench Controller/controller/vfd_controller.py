"""
VFD controller for Delta VFD022EL43A.

Controls the 3HP pump via Modbus RTU through the B3 ESP32 bridge (Bus 2).
Supports simulator and real hardware backends.

VFD Register Map (Delta VFD022EL43A):
  0x2000: Control Word
    - 0x0001 = Run Forward
    - 0x0003 = Emergency Stop
    - 0x0005 = Normal Stop
  0x2001: Frequency Setpoint (Hz × 100)
  0x2100: Status Word (bitmask)
  0x2103: Actual Output Frequency (Hz × 100)
  0x2104: Actual Output Current (A × 100)
  0x2105: Fault Code (0 = none)
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# VFD Modbus registers
REG_CONTROL = 0x2000
REG_FREQ_SETPOINT = 0x2001
REG_STATUS = 0x2100
REG_ACTUAL_FREQ = 0x2103
REG_ACTUAL_CURRENT = 0x2104
REG_FAULT = 0x2105

# Control word values
CMD_RUN_FORWARD = 0x0001
CMD_EMERGENCY_STOP = 0x0003
CMD_NORMAL_STOP = 0x0005

# Limits
VFD_FREQ_MIN = 5.0   # Hz
VFD_FREQ_MAX = 50.0  # Hz
VFD_ADDR = 1          # Modbus address on Bus 2
VFD_BUS = 2


@dataclass
class VFDStatus:
    """Current VFD state."""
    running: bool = False
    frequency_hz: float = 0.0
    target_hz: float = 0.0
    current_a: float = 0.0
    fault_code: int = 0
    connected: bool = False
    last_read: float = 0.0

    @property
    def faulted(self) -> bool:
        return self.fault_code != 0


class VFDController:
    """
    High-level VFD controller.

    Usage:
        vfd = VFDController(backend='simulator')
        vfd.start(frequency=30.0)
        status = vfd.read_status()
        vfd.set_frequency(40.0)
        vfd.stop()
    """

    def __init__(self, backend: str = 'simulator'):
        self._backend = backend
        self._lock = threading.Lock()
        self._simulator = None
        self._serial = None
        self._status = VFDStatus()

    def init_backend(self):
        """Initialise the appropriate backend."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            self._status.connected = True
            logger.info("VFDController using SIMULATOR backend")
        else:
            from comms.serial_handler import BusManager
            # The bus manager should already be initialised elsewhere;
            # here we just need the bus2 handler
            logger.info("VFDController using REAL backend")

    def set_serial_handler(self, serial_handler):
        """Set the serial handler for real hardware mode."""
        self._serial = serial_handler
        self._status.connected = serial_handler is not None and serial_handler.is_connected

    # ------------------------------------------------------------------
    #  Commands
    # ------------------------------------------------------------------

    def start(self, frequency: float = 10.0) -> bool:
        """
        Start the VFD at the given frequency.

        Args:
            frequency: Target frequency in Hz (5.0 - 50.0)

        Returns:
            True if command was sent successfully.
        """
        frequency = max(VFD_FREQ_MIN, min(VFD_FREQ_MAX, frequency))

        with self._lock:
            if self._backend == 'simulator':
                self._simulator.vfd_start(frequency)
                self._status.running = True
                self._status.target_hz = frequency
                return True
            else:
                return self._real_start(frequency)

    def stop(self) -> bool:
        """Normal stop — VFD ramps down."""
        with self._lock:
            if self._backend == 'simulator':
                self._simulator.vfd_stop()
                self._status.running = False
                self._status.target_hz = 0.0
                return True
            else:
                return self._real_write_control(CMD_NORMAL_STOP)

    def emergency_stop(self) -> bool:
        """Emergency stop — immediate halt."""
        with self._lock:
            if self._backend == 'simulator':
                self._simulator.vfd_emergency_stop()
                self._status.running = False
                self._status.target_hz = 0.0
                self._status.frequency_hz = 0.0
                return True
            else:
                return self._real_write_control(CMD_EMERGENCY_STOP)

    def set_frequency(self, frequency: float) -> bool:
        """
        Change target frequency while running.

        Args:
            frequency: Target frequency in Hz (5.0 - 50.0)
        """
        frequency = max(VFD_FREQ_MIN, min(VFD_FREQ_MAX, frequency))

        with self._lock:
            if self._backend == 'simulator':
                self._simulator.vfd_set_frequency(frequency)
                self._status.target_hz = frequency
                return True
            else:
                return self._real_set_frequency(frequency)

    def read_status(self) -> VFDStatus:
        """Read current VFD status."""
        with self._lock:
            if self._backend == 'simulator':
                self._simulator.update()
                sim = self._simulator
                self._status = VFDStatus(
                    running=sim.vfd_running,
                    frequency_hz=sim.vfd_actual_freq,
                    target_hz=sim.vfd_target_freq,
                    current_a=max(0, sim.vfd_current),
                    fault_code=sim.vfd_fault,
                    connected=True,
                    last_read=time.time(),
                )
            else:
                self._real_read_status()
            return self._status

    # ------------------------------------------------------------------
    #  Real hardware (Bus 2 serial)
    # ------------------------------------------------------------------

    def _real_start(self, frequency: float) -> bool:
        """Start VFD via real Modbus."""
        if not self._serial or not self._serial.is_connected:
            logger.error("VFD serial not connected")
            return False
        try:
            # Set frequency first, then run
            freq_val = int(frequency * 100)
            r1 = self._serial.modbus_write(VFD_BUS, VFD_ADDR, REG_FREQ_SETPOINT, freq_val)
            r2 = self._serial.modbus_write(VFD_BUS, VFD_ADDR, REG_CONTROL, CMD_RUN_FORWARD)
            ok = r1.get('ok', False) and r2.get('ok', False)
            if ok:
                self._status.running = True
                self._status.target_hz = frequency
            return ok
        except Exception:
            logger.exception("VFD start failed")
            return False

    def _real_write_control(self, cmd: int) -> bool:
        """Write control word to VFD."""
        if not self._serial or not self._serial.is_connected:
            return False
        try:
            r = self._serial.modbus_write(VFD_BUS, VFD_ADDR, REG_CONTROL, cmd)
            return r.get('ok', False)
        except Exception:
            logger.exception("VFD control write failed")
            return False

    def _real_set_frequency(self, frequency: float) -> bool:
        """Write frequency setpoint."""
        if not self._serial or not self._serial.is_connected:
            return False
        try:
            freq_val = int(frequency * 100)
            r = self._serial.modbus_write(VFD_BUS, VFD_ADDR, REG_FREQ_SETPOINT, freq_val)
            if r.get('ok', False):
                self._status.target_hz = frequency
                return True
            return False
        except Exception:
            logger.exception("VFD set frequency failed")
            return False

    def _real_read_status(self):
        """Read all status registers from VFD."""
        if not self._serial or not self._serial.is_connected:
            self._status.connected = False
            return

        try:
            self._status.connected = True
            self._status.last_read = time.time()

            r = self._serial.modbus_read(VFD_BUS, VFD_ADDR, REG_STATUS, 1)
            if r.get('ok'):
                self._status.running = bool(r['data'].get('value', 0) & 0x01)

            r = self._serial.modbus_read(VFD_BUS, VFD_ADDR, REG_ACTUAL_FREQ, 1)
            if r.get('ok'):
                self._status.frequency_hz = r['data'].get('value', 0) / 100.0

            r = self._serial.modbus_read(VFD_BUS, VFD_ADDR, REG_ACTUAL_CURRENT, 1)
            if r.get('ok'):
                self._status.current_a = r['data'].get('value', 0) / 100.0

            r = self._serial.modbus_read(VFD_BUS, VFD_ADDR, REG_FAULT, 1)
            if r.get('ok'):
                self._status.fault_code = r['data'].get('value', 0)

        except Exception:
            logger.exception("VFD status read failed")
            self._status.connected = False
