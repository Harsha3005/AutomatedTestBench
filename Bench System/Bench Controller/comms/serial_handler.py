"""
Serial handler for USB communication with ESP32 bridges.

Protocol: JSON lines over 115200 baud USB serial.
Commands sent as JSON objects, responses received as JSON objects.
Thread-safe with a lock for concurrent access.

Bridges:
  Bus 1 (B2): /dev/ttyBENCH_BUS — sensors, valves, tower light
  Bus 2 (B3): /dev/ttyVFD_BUS   — VFD Delta (isolated)
"""

import json
import logging
import threading
import time
from typing import Any

import serial

logger = logging.getLogger(__name__)

# Response timeout per command (seconds)
DEFAULT_TIMEOUT = 2.0


class SerialHandler:
    """Thread-safe JSON serial handler for a single USB-serial bridge."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._lock = threading.Lock()
        self._serial: serial.Serial | None = None
        self._connected = False

    # ------------------------------------------------------------------
    #  Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open the serial port. Returns True on success."""
        with self._lock:
            if self._connected:
                return True
            try:
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )
                # Flush any stale data
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                self._connected = True
                logger.info("Serial connected: %s @ %d baud", self.port, self.baudrate)
                return True
            except serial.SerialException as e:
                logger.error("Serial connect failed on %s: %s", self.port, e)
                self._connected = False
                return False

    def disconnect(self):
        """Close the serial port."""
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._serial = None
            self._connected = False
            logger.info("Serial disconnected: %s", self.port)

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    #  Low-level I/O
    # ------------------------------------------------------------------

    def _send_raw(self, data: bytes):
        """Write raw bytes to serial port. Caller must hold lock."""
        if not self._serial or not self._serial.is_open:
            raise ConnectionError(f"Serial port {self.port} not open")
        self._serial.write(data)
        self._serial.flush()

    def _recv_line(self, timeout: float | None = None) -> str | None:
        """Read one line from serial. Caller must hold lock."""
        if not self._serial or not self._serial.is_open:
            raise ConnectionError(f"Serial port {self.port} not open")
        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout
        try:
            line = self._serial.readline()
            if line:
                return line.decode('utf-8', errors='replace').strip()
            return None
        finally:
            self._serial.timeout = old_timeout

    # ------------------------------------------------------------------
    #  Command API
    # ------------------------------------------------------------------

    def send_command(
        self,
        cmd: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Send a JSON command and wait for JSON response.

        Args:
            cmd: Command dict, e.g. {"cmd": "MB_READ", "bus": 1, "addr": 1, ...}
            timeout: Override response timeout (seconds).

        Returns:
            Response dict with at least {"ok": bool}.

        Raises:
            ConnectionError: If port not open.
            TimeoutError: If no response within timeout.
            ValueError: If response is not valid JSON.
        """
        with self._lock:
            if not self.is_connected:
                raise ConnectionError(f"Serial port {self.port} not connected")

            # Serialize and send
            line = json.dumps(cmd, separators=(',', ':')) + '\n'
            self._send_raw(line.encode('utf-8'))
            logger.debug("TX [%s]: %s", self.port, line.strip())

            # Wait for response
            t = timeout or self.timeout
            response_str = self._recv_line(timeout=t)
            if response_str is None:
                raise TimeoutError(
                    f"No response from {self.port} within {t}s for cmd={cmd.get('cmd')}"
                )

            logger.debug("RX [%s]: %s", self.port, response_str)

            try:
                return json.loads(response_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response: {response_str!r}") from e

    # ------------------------------------------------------------------
    #  Convenience commands
    # ------------------------------------------------------------------

    def modbus_read(
        self,
        bus: int,
        addr: int,
        reg: int,
        count: int = 1,
    ) -> dict[str, Any]:
        """Read Modbus registers via bridge."""
        return self.send_command({
            'cmd': 'MB_READ',
            'bus': bus,
            'addr': addr,
            'reg': reg,
            'count': count,
        })

    def modbus_write(
        self,
        bus: int,
        addr: int,
        reg: int,
        value: int,
    ) -> dict[str, Any]:
        """Write a single Modbus register via bridge."""
        return self.send_command({
            'cmd': 'MB_WRITE',
            'bus': bus,
            'addr': addr,
            'reg': reg,
            'value': value,
        })

    def gpio_set(self, pin: str, state: int) -> dict[str, Any]:
        """Set a GPIO pin HIGH (1) or LOW (0)."""
        return self.send_command({'cmd': 'GPIO_SET', 'pin': pin, 'state': state})

    def gpio_get(self, pin: str) -> dict[str, Any]:
        """Read a GPIO pin state."""
        return self.send_command({'cmd': 'GPIO_GET', 'pin': pin})

    def valve_control(self, valve: str, action: str) -> dict[str, Any]:
        """Control a valve: action = 'OPEN' or 'CLOSE'."""
        return self.send_command({'cmd': 'VALVE', 'valve': valve, 'action': action})

    def diverter_control(self, position: str) -> dict[str, Any]:
        """Control 3-way diverter: position = 'COLLECT' or 'BYPASS'."""
        return self.send_command({'cmd': 'DIVERTER', 'position': position})

    def get_status(self) -> dict[str, Any]:
        """Get bridge status."""
        return self.send_command({'cmd': 'STATUS'})


# ---------------------------------------------------------------------------
#  Bus Manager — manages both serial bridges
# ---------------------------------------------------------------------------

class BusManager:
    """Manages Bus 1 (sensors) and Bus 2 (VFD) serial connections."""

    def __init__(self):
        self.bus1: SerialHandler | None = None
        self.bus2: SerialHandler | None = None

    def init_from_settings(self):
        """Initialise handlers from Django settings."""
        from django.conf import settings
        port1 = getattr(settings, 'BENCH_SERIAL_PORT_BUS1', None)
        port2 = getattr(settings, 'BENCH_SERIAL_PORT_BUS2', None)
        baud = getattr(settings, 'BENCH_SERIAL_BAUD', 115200)

        if port1:
            self.bus1 = SerialHandler(port1, baud)
        if port2:
            self.bus2 = SerialHandler(port2, baud)

    def connect_all(self) -> dict[str, bool]:
        """Connect both buses. Returns connection status per bus."""
        results = {}
        if self.bus1:
            results['bus1'] = self.bus1.connect()
        if self.bus2:
            results['bus2'] = self.bus2.connect()
        return results

    def disconnect_all(self):
        """Disconnect both buses."""
        if self.bus1:
            self.bus1.disconnect()
        if self.bus2:
            self.bus2.disconnect()

    @property
    def status(self) -> dict[str, bool]:
        return {
            'bus1': self.bus1.is_connected if self.bus1 else False,
            'bus2': self.bus2.is_connected if self.bus2 else False,
        }
