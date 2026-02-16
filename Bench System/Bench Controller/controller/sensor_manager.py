"""
Sensor manager — unified API for reading all field device sensors.

Uses either the hardware simulator or real serial handler depending on
HARDWARE_BACKEND setting. Provides a polling loop and on-demand reads.

Sensors polled:
  Bus 1 (B2): EM flow meter (F1, addr 1), weighing scale (F2, addr 2),
              4-20mA module (F3, addr 3), DUT meter (addr 20)
  Bus 2 (B3): VFD status (addr 1)
  GPIO: Valve positions, E-stop, contactor
  Analog: Reservoir level, temperature, environment
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SensorSnapshot:
    """Snapshot of all sensor readings at a point in time."""
    timestamp: float = 0.0

    # Flow
    flow_rate_lph: float = 0.0          # L/h from EM meter
    em_totalizer_l: float = 0.0         # Cumulative litres

    # Scale
    weight_kg: float = 0.0              # Tared weight
    weight_raw_kg: float = 0.0          # Raw weight

    # Pressure
    pressure_upstream_bar: float = 0.0  # PT-01
    pressure_downstream_bar: float = 0.0  # PT-02

    # Temperature
    water_temp_c: float = 0.0           # Reservoir / inline
    atm_temp_c: float = 0.0
    atm_humidity_pct: float = 0.0
    atm_baro_hpa: float = 0.0

    # Reservoir
    reservoir_level_pct: float = 0.0

    # DUT
    dut_connected: bool = False
    dut_totalizer_l: float | None = None

    # VFD
    vfd_running: bool = False
    vfd_freq_hz: float = 0.0
    vfd_target_hz: float = 0.0
    vfd_current_a: float = 0.0
    vfd_fault: int = 0

    # Valves
    valves: dict[str, bool] = field(default_factory=dict)
    diverter: str = 'BYPASS'

    # Tower
    tower_red: bool = False
    tower_yellow: bool = False
    tower_green: bool = True
    buzzer: bool = False

    # Infrastructure
    estop_active: bool = False
    contactor_on: bool = True
    mcb_on: bool = True

    # Comms
    lora_online: bool = False
    bus1_online: bool = False
    bus2_online: bool = False


class SensorManager:
    """
    Polls all sensors and provides a unified snapshot.

    Usage:
        manager = SensorManager(backend='simulator')
        manager.start(poll_interval=0.2)
        snapshot = manager.latest
        manager.stop()
    """

    def __init__(self, backend: str = 'simulator'):
        """
        Args:
            backend: 'simulator' or 'real'
        """
        self._backend = backend
        self._latest = SensorSnapshot()
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._poll_interval = 0.2  # 200ms default
        self._listeners: list[Callable[[SensorSnapshot], None]] = []

        # Backend references
        self._simulator = None
        self._bus_manager = None

    def _init_backend(self):
        """Initialise the appropriate backend."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            logger.info("SensorManager using SIMULATOR backend")
        else:
            from comms.serial_handler import BusManager
            self._bus_manager = BusManager()
            self._bus_manager.init_from_settings()
            results = self._bus_manager.connect_all()
            logger.info("SensorManager using REAL backend, connections: %s", results)

    @property
    def latest(self) -> SensorSnapshot:
        """Get the most recent sensor snapshot."""
        with self._lock:
            return self._latest

    def add_listener(self, callback: Callable[[SensorSnapshot], None]):
        """Register a callback for new sensor snapshots."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[SensorSnapshot], None]):
        """Remove a listener callback."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    #  Polling loop
    # ------------------------------------------------------------------

    def start(self, poll_interval: float = 0.2):
        """Start the polling loop in a background thread."""
        if self._running:
            return
        self._poll_interval = poll_interval
        self._init_backend()
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name='SensorManager',
            daemon=True,
        )
        self._thread.start()
        logger.info("SensorManager started (%.0fms interval)", poll_interval * 1000)

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._bus_manager:
            self._bus_manager.disconnect_all()
        logger.info("SensorManager stopped")

    def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                snapshot = self._read_all()
                with self._lock:
                    self._latest = snapshot
                # Notify listeners
                for cb in self._listeners:
                    try:
                        cb(snapshot)
                    except Exception:
                        logger.exception("Listener callback error")
            except Exception:
                logger.exception("SensorManager poll error")
            time.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    #  Read all sensors
    # ------------------------------------------------------------------

    def _read_all(self) -> SensorSnapshot:
        """Read all sensors from the active backend."""
        if self._backend == 'simulator':
            return self._read_simulator()
        else:
            return self._read_real()

    def _read_simulator(self) -> SensorSnapshot:
        """Read all sensor values from the simulator."""
        data = self._simulator.read_all_sensors()
        return SensorSnapshot(
            timestamp=time.time(),
            flow_rate_lph=data.get('FT-01', 0.0),
            em_totalizer_l=data.get('FT-01_totalizer', 0.0),
            weight_kg=data.get('WT-01', 0.0),
            weight_raw_kg=data.get('WT-01_raw', 0.0),
            pressure_upstream_bar=data.get('PT-01', 0.0),
            pressure_downstream_bar=data.get('PT-02', 0.0),
            water_temp_c=data.get('RES-TEMP', 22.0),
            atm_temp_c=data.get('ATM-TEMP', 25.0),
            atm_humidity_pct=data.get('ATM-HUM', 55.0),
            atm_baro_hpa=data.get('ATM-BARO', 1013.0),
            reservoir_level_pct=data.get('RES-LVL', 85.0),
            dut_connected=data.get('DUT_connected', False),
            dut_totalizer_l=data.get('DUT_totalizer'),
            vfd_running=data.get('P-01_running', False),
            vfd_freq_hz=data.get('P-01_freq', 0.0),
            vfd_target_hz=data.get('P-01_target', 0.0),
            vfd_current_a=data.get('P-01_current', 0.0),
            vfd_fault=data.get('P-01_fault', 0),
            valves={
                'SV1': data.get('SV1', False),
                'BV-L1': data.get('BV-L1', False),
                'BV-L2': data.get('BV-L2', False),
                'BV-L3': data.get('BV-L3', False),
                'SV-DRN': data.get('SV-DRN', False),
                'BV-BP': data.get('BV-BP', False),
            },
            diverter=data.get('diverter', 'BYPASS'),
            tower_red=data.get('TOWER_red', False),
            tower_yellow=data.get('TOWER_yellow', False),
            tower_green=data.get('TOWER_green', True),
            buzzer=data.get('TOWER_buzzer', False),
            estop_active=data.get('ESTOP', False),
            contactor_on=data.get('CONT', True),
            mcb_on=data.get('MCB', True),
            lora_online=data.get('LORA', False),
            bus1_online=data.get('BUS1', False),
            bus2_online=data.get('BUS2', False),
        )

    def _read_real(self) -> SensorSnapshot:
        """Read all sensor values via real serial hardware."""
        snap = SensorSnapshot(timestamp=time.time())
        bus1 = self._bus_manager.bus1 if self._bus_manager else None
        bus2 = self._bus_manager.bus2 if self._bus_manager else None

        # --- Bus 1 reads ---
        if bus1 and bus1.is_connected:
            snap.bus1_online = True
            try:
                # EM Flow Meter (F1, addr 1)
                r = bus1.modbus_read(1, 1, 0, 2)
                if r.get('ok'):
                    snap.flow_rate_lph = r['data'].get('value', 0.0)
                r = bus1.modbus_read(1, 1, 2, 2)
                if r.get('ok'):
                    snap.em_totalizer_l = r['data'].get('value', 0.0)
            except Exception:
                logger.debug("EM meter read failed")

            try:
                # Scale (F2, addr 2)
                r = bus1.modbus_read(1, 2, 0, 2)
                if r.get('ok'):
                    snap.weight_kg = r['data'].get('value', 0.0)
            except Exception:
                logger.debug("Scale read failed")

            try:
                # 4-20mA (F3, addr 3)
                r = bus1.modbus_read(1, 3, 0, 1)
                if r.get('ok'):
                    snap.pressure_upstream_bar = r['data'].get('value', 0.0)
                r = bus1.modbus_read(1, 3, 1, 1)
                if r.get('ok'):
                    snap.pressure_downstream_bar = r['data'].get('value', 0.0)
                r = bus1.modbus_read(1, 3, 2, 1)
                if r.get('ok'):
                    snap.water_temp_c = r['data'].get('value', 22.0)
            except Exception:
                logger.debug("4-20mA module read failed")

            try:
                # DUT (addr 20)
                r = bus1.modbus_read(1, 20, 0, 2)
                if r.get('ok'):
                    snap.dut_connected = True
                    snap.dut_totalizer_l = r['data'].get('value', 0.0)
                else:
                    snap.dut_connected = False
            except Exception:
                snap.dut_connected = False

            try:
                # GPIO: E-stop, contactor
                r = bus1.gpio_get('ESTOP')
                if r.get('ok'):
                    snap.estop_active = bool(r['data'].get('state', 0))
                r = bus1.gpio_get('CONT')
                if r.get('ok'):
                    snap.contactor_on = bool(r['data'].get('state', 1))
            except Exception:
                logger.debug("GPIO read failed")

        # --- Bus 2 reads ---
        if bus2 and bus2.is_connected:
            snap.bus2_online = True
            try:
                # VFD status (addr 1)
                r = bus2.modbus_read(2, 1, 0x2100, 1)
                if r.get('ok'):
                    snap.vfd_running = bool(r['data'].get('value', 0) & 0x01)
                r = bus2.modbus_read(2, 1, 0x2103, 1)
                if r.get('ok'):
                    snap.vfd_freq_hz = r['data'].get('value', 0) / 100.0
                r = bus2.modbus_read(2, 1, 0x2104, 1)
                if r.get('ok'):
                    snap.vfd_current_a = r['data'].get('value', 0) / 100.0
                r = bus2.modbus_read(2, 1, 0x2105, 1)
                if r.get('ok'):
                    snap.vfd_fault = r['data'].get('value', 0)
            except Exception:
                logger.debug("VFD read failed")

        return snap

    # ------------------------------------------------------------------
    #  On-demand single device read
    # ------------------------------------------------------------------

    def read_device(self, device_id: str) -> dict[str, Any]:
        """Read a single device. Returns dict with state/value."""
        if self._backend == 'simulator':
            return self._simulator.read_device(device_id)
        # Real: read from latest snapshot
        snap = self.latest
        device_map = {
            'FT-01': {'value': snap.flow_rate_lph, 'totalizer': snap.em_totalizer_l},
            'WT-01': {'value': snap.weight_kg},
            'PT-01': {'value': snap.pressure_upstream_bar},
            'PT-02': {'value': snap.pressure_downstream_bar},
            'RES-LVL': {'value': snap.reservoir_level_pct},
            'RES-TEMP': {'value': snap.water_temp_c},
            'ATM-TEMP': {'value': snap.atm_temp_c},
            'ATM-HUM': {'value': snap.atm_humidity_pct},
            'ATM-BARO': {'value': snap.atm_baro_hpa},
            'P-01': {
                'state': 'running' if snap.vfd_running else 'stopped',
                'frequency': snap.vfd_freq_hz,
                'current': snap.vfd_current_a,
                'fault': snap.vfd_fault,
            },
            'DUT': {
                'state': 'connected' if snap.dut_connected else 'disconnected',
                'totalizer': snap.dut_totalizer_l,
            },
        }
        if device_id in device_map:
            return device_map[device_id]
        # Valve
        if device_id in snap.valves:
            return {'state': 'open' if snap.valves[device_id] else 'closed'}
        return {'error': f'Unknown device: {device_id}'}
