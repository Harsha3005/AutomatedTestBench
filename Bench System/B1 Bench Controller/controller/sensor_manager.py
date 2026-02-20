"""
Sensor manager — unified API for reading all field device sensors.

Uses either the hardware simulator or real serial handler depending on
HARDWARE_BACKEND setting. Provides a polling loop and on-demand reads.

6-Node Architecture:
  Ch1 B2 VFD Bridge:     VFD status (Modbus addr 1, regs 0x2100+)
  Ch2 B3 Meter Bridge:   EM flow meter (addr 1), DUT meter (addr 20)
  Ch3 B4 Scale+Pressure: Scale (SCALE_READ), Pressure (PRESSURE_READ)
  Ch4 B5 GPIO Controller: E-stop, atmospheric sensors (SENSOR_READ)
  Ch5 B6 Reservoir Monitor:   Reservoir level + temp (TANK_READ)
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
    scale_power_on: bool = False        # Scale relay state

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

    # Comms — per-channel online status
    lora_online: bool = False
    b2_vfd_online: bool = False
    b3_meter_online: bool = False
    b4_scale_online: bool = False
    b5_gpio_online: bool = False
    b6_tank_online: bool = False


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
        self._scale_power_on = False

        # Backend references
        self._simulator = None
        self._channel_manager = None

    def _init_backend(self):
        """Initialise the appropriate backend."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            logger.info("SensorManager using SIMULATOR backend")
        else:
            from comms.serial_handler import ChannelManager
            self._channel_manager = ChannelManager()
            self._channel_manager.init_from_settings()
            results = self._channel_manager.connect_all()
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

    def set_scale_power(self, on: bool):
        """Update cached scale power state (called by hardware.scale_power_on/off)."""
        self._scale_power_on = on

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
        if self._channel_manager:
            self._channel_manager.disconnect_all()
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
            b2_vfd_online=data.get('B2_VFD', False),
            b3_meter_online=data.get('B3_METER', False),
            b4_scale_online=data.get('B4_SCALE', False),
            b5_gpio_online=data.get('B5_GPIO', False),
            b6_tank_online=data.get('B6_TANK', False),
            scale_power_on=True,
        )

    def _read_real(self) -> SensorSnapshot:
        """Read all sensor values via real serial hardware (6-channel)."""
        snap = SensorSnapshot(timestamp=time.time(), scale_power_on=self._scale_power_on)
        ch = self._channel_manager
        if not ch:
            return snap

        # --- B3 Meter Bridge: EM flow + DUT totalizer ---
        meter = ch.get('meter')
        if meter and meter.is_connected:
            snap.b3_meter_online = True
            try:
                # EM Flow Meter (addr 1, reg 0 = flow, reg 2 = totalizer)
                r = meter.modbus_read(1, 0, 2)
                if r.get('ok'):
                    values = r.get('data', {}).get('values', [])
                    if len(values) >= 1:
                        snap.flow_rate_lph = float(values[0])
                    if len(values) >= 2:
                        snap.em_totalizer_l = float(values[1])
            except Exception:
                logger.debug("EM meter read failed")

            try:
                # DUT (addr 20, reg 0 = totalizer)
                r = meter.modbus_read(20, 0, 2)
                if r.get('ok'):
                    snap.dut_connected = True
                    values = r.get('data', {}).get('values', [])
                    if values:
                        snap.dut_totalizer_l = float(values[0])
                else:
                    snap.dut_connected = False
            except Exception:
                snap.dut_connected = False

        # --- B4 Scale + Pressure Bridge ---
        scale = ch.get('scale')
        if scale and scale.is_connected:
            snap.b4_scale_online = True
            try:
                r = scale.scale_read()
                if r.get('ok'):
                    d = r.get('data', {})
                    w = d.get('weight_kg')
                    if w is not None:
                        snap.weight_kg = float(w)
                        snap.weight_raw_kg = float(w)
            except Exception:
                logger.debug("Scale read failed")

            try:
                r = scale.pressure_read()
                if r.get('ok'):
                    d = r.get('data', {})
                    pt01 = d.get('pt01_mpa')
                    pt02 = d.get('pt02_mpa')
                    if pt01 is not None:
                        snap.pressure_upstream_bar = float(pt01) * 10.0  # MPa → bar
                    if pt02 is not None:
                        snap.pressure_downstream_bar = float(pt02) * 10.0
            except Exception:
                logger.debug("Pressure read failed")

        # --- B5 GPIO Controller: E-stop + atmospheric ---
        gpio = ch.get('gpio')
        if gpio and gpio.is_connected:
            snap.b5_gpio_online = True
            try:
                r = gpio.sensor_read()
                if r.get('ok'):
                    d = r.get('data', {})
                    snap.estop_active = bool(d.get('estop_active', False))
                    atm_temp = d.get('atm_temp_c')
                    if atm_temp is not None:
                        snap.atm_temp_c = float(atm_temp)
                    atm_hum = d.get('atm_hum_pct')
                    if atm_hum is not None:
                        snap.atm_humidity_pct = float(atm_hum)
                    # Barometric pressure — XY-MD02 doesn't provide this;
                    # reads from firmware if a BMP280/BME280 is added later,
                    # otherwise uses standard atmosphere (1013.25 hPa).
                    atm_baro = d.get('atm_baro_hpa')
                    if atm_baro is not None:
                        snap.atm_baro_hpa = float(atm_baro)
                    else:
                        snap.atm_baro_hpa = 1013.25
            except Exception:
                logger.debug("GPIO sensor read failed")

        # --- B6 Reservoir Monitor: reservoir level + temperature ---
        tank = ch.get('tank')
        if tank and tank.is_connected:
            snap.b6_tank_online = True
            try:
                r = tank.tank_read()
                if r.get('ok'):
                    d = r.get('data', {})
                    level = d.get('level_pct')
                    if level is not None:
                        snap.reservoir_level_pct = float(level)
                    temp = d.get('temp_c')
                    if temp is not None:
                        snap.water_temp_c = float(temp)
            except Exception:
                logger.debug("Tank read failed")

        # --- B2 VFD Bridge: VFD status ---
        vfd = ch.get('vfd')
        if vfd and vfd.is_connected:
            snap.b2_vfd_online = True
            try:
                r = vfd.modbus_read(1, 0x2100, 1)
                if r.get('ok'):
                    values = r.get('data', {}).get('values', [])
                    if values:
                        snap.vfd_running = bool(values[0] & 0x01)
                r = vfd.modbus_read(1, 0x2103, 1)
                if r.get('ok'):
                    values = r.get('data', {}).get('values', [])
                    if values:
                        snap.vfd_freq_hz = values[0] / 100.0
                r = vfd.modbus_read(1, 0x2104, 1)
                if r.get('ok'):
                    values = r.get('data', {}).get('values', [])
                    if values:
                        snap.vfd_current_a = values[0] / 100.0
                r = vfd.modbus_read(1, 0x2105, 1)
                if r.get('ok'):
                    values = r.get('data', {}).get('values', [])
                    if values:
                        snap.vfd_fault = values[0]
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
