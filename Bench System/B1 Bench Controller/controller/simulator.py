"""
Full hardware simulator for the test bench.

Replaces in-memory _sim_states from bench_ui/views.py with a physics-based
simulation that models realistic sensor dynamics, actuator transitions,
and test flow behaviour.

Thread-safe — can be polled from sensor_manager and controlled from
vfd_controller or state_machine concurrently.

Simulated devices (23):
  Reservoir: RES-LVL, RES-TEMP
  Pump: P-01 (VFD 0-50 Hz)
  Main line: SV1, PT-01, DUT, PT-02, FT-01
  Test lanes: BV-L1, BV-L2, BV-L3
  Collection: WT-01, SV-DRN
  Bypass: BV-BP
  Environment: ATM-TEMP, ATM-HUM
  Indicators: TOWER, MCB, CONT
  Comms: LORA, B2_VFD, B3_METER, B4_SCALE, B5_GPIO, B6_TANK
"""

import logging
import math
import random
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Physical constants and defaults
# ---------------------------------------------------------------------------

WATER_DENSITY_20C = 998.2  # kg/m3 at 20 degC
GRAVITY = 9.81


class HardwareSimulator:
    """
    Physics-based hardware simulator for the IIIT-B test bench.

    Key behaviours:
      - VFD ramps frequency at ~5 Hz/s
      - Flow rate is proportional to VFD frequency (linear model)
      - Pressure correlates with flow and valve state
      - Scale weight accumulates when diverter is COLLECT and pump running
      - Valve transitions take ~0.5s
      - Sensor readings have realistic noise
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._last_update = time.time()

        # --- Valve states ---
        # True = open, False = closed
        self.valves: dict[str, bool] = {
            'SV1': False,
            'BV-L1': False,
            'BV-L2': False,
            'BV-L3': False,
            'SV-DRN': False,
            'BV-BP': False,
        }

        # --- Diverter ---
        # 'BYPASS' or 'COLLECT'
        self.diverter_position: str = 'BYPASS'

        # --- Pump / VFD ---
        self.vfd_running: bool = False
        self.vfd_target_freq: float = 0.0    # Hz setpoint
        self.vfd_actual_freq: float = 0.0    # Hz actual (ramps)
        self.vfd_current: float = 0.0        # Amps
        self.vfd_fault: int = 0              # 0 = no fault
        self.vfd_ramp_rate: float = 5.0      # Hz/s

        # --- Sensors ---
        self.reservoir_level: float = 85.0   # %
        self.reservoir_temp: float = 22.0    # degC
        self.pressure_upstream: float = 0.0  # bar
        self.pressure_downstream: float = 0.0  # bar
        self.flow_rate: float = 0.0          # L/h
        self.em_totalizer: float = 0.0       # L (cumulative)
        self.scale_weight: float = 0.0       # kg
        self.scale_tared: bool = False
        self.scale_tare_offset: float = 0.0  # kg

        # --- DUT (meter under test) ---
        self.dut_connected: bool = False
        self.dut_totalizer: float = 0.0      # L
        self.dut_error_pct: float = 1.5      # Simulated DUT error %

        # --- Environment ---
        self.atm_temp: float = 25.0          # degC
        self.atm_humidity: float = 55.0      # %RH

        # --- Indicators ---
        self.tower_red: bool = False
        self.tower_yellow: bool = False
        self.tower_green: bool = True        # Idle = green
        self.buzzer: bool = False

        # --- Infrastructure ---
        self.mcb_on: bool = True
        self.contactor_on: bool = True
        self.estop_active: bool = False

        # --- Comms (per-channel online status) ---
        self.lora_online: bool = True
        self.b2_vfd_online: bool = True
        self.b3_meter_online: bool = True
        self.b4_scale_online: bool = True
        self.b5_gpio_online: bool = True
        self.b6_tank_online: bool = True

    # ------------------------------------------------------------------
    #  Physics update (call periodically or before reading sensors)
    # ------------------------------------------------------------------

    def update(self):
        """Advance the simulation by elapsed wall-clock time."""
        with self._lock:
            now = time.time()
            dt = now - self._last_update
            if dt <= 0:
                return
            self._last_update = now

            # Clamp dt to prevent huge jumps
            dt = min(dt, 1.0)

            self._update_vfd(dt)
            self._update_flow(dt)
            self._update_pressures()
            self._update_scale(dt)
            self._update_environment(dt)
            self._update_reservoir(dt)

    def _update_vfd(self, dt: float):
        """Ramp VFD frequency toward target."""
        if not self.vfd_running or self.vfd_fault:
            # Ramp down
            if self.vfd_actual_freq > 0:
                self.vfd_actual_freq = max(
                    0, self.vfd_actual_freq - self.vfd_ramp_rate * dt
                )
            self.vfd_current = self.vfd_actual_freq * 0.15  # rough A/Hz
            return

        diff = self.vfd_target_freq - self.vfd_actual_freq
        if abs(diff) < 0.1:
            self.vfd_actual_freq = self.vfd_target_freq
        else:
            step = self.vfd_ramp_rate * dt
            if diff > 0:
                self.vfd_actual_freq = min(
                    self.vfd_target_freq, self.vfd_actual_freq + step
                )
            else:
                self.vfd_actual_freq = max(
                    self.vfd_target_freq, self.vfd_actual_freq - step
                )

        # Motor current ~ proportional to frequency
        self.vfd_current = self.vfd_actual_freq * 0.15 + random.gauss(0, 0.05)

    def _update_flow(self, dt: float):
        """Calculate flow based on VFD freq and valve states."""
        # Flow only if SV1 open and at least one lane valve open
        sv1_open = self.valves.get('SV1', False)
        lane_open = any(
            self.valves.get(v, False) for v in ('BV-L1', 'BV-L2', 'BV-L3')
        )

        if sv1_open and lane_open and self.vfd_actual_freq > 0:
            # Linear flow model: 50 Hz → 2500 L/h
            base_flow = self.vfd_actual_freq * 50.0  # L/h
            # Add noise ±0.5%
            self.flow_rate = base_flow * (1 + random.gauss(0, 0.005))
        elif self.valves.get('BV-BP', False) and self.vfd_actual_freq > 0:
            # Bypass open — flow recirculates, no measured flow
            self.flow_rate = random.gauss(0, 0.5)
        else:
            self.flow_rate = max(0, self.flow_rate * 0.9)  # Decay

        # EM totalizer (litres)
        flow_l_per_sec = max(0, self.flow_rate) / 3600.0
        self.em_totalizer += flow_l_per_sec * dt

        # DUT totalizer (with simulated error)
        if self.dut_connected:
            dut_flow = flow_l_per_sec * (1 + self.dut_error_pct / 100.0)
            self.dut_totalizer += dut_flow * dt

    def _update_pressures(self):
        """Pressure based on flow and valve state."""
        if self.flow_rate > 10:
            # Upstream pressure: 1.5 - 6 bar range depending on flow
            base_p = 1.5 + (self.flow_rate / 2500.0) * 4.5
            self.pressure_upstream = base_p + random.gauss(0, 0.02)
            # Downstream: slightly less (DUT pressure drop)
            self.pressure_downstream = (
                self.pressure_upstream - 0.1 - (self.flow_rate / 2500.0) * 0.3
                + random.gauss(0, 0.02)
            )
        else:
            self.pressure_upstream = max(0, self.pressure_upstream * 0.95)
            self.pressure_downstream = max(0, self.pressure_downstream * 0.95)

    def _update_scale(self, dt: float):
        """Accumulate weight on collection tank scale."""
        if self.diverter_position == 'COLLECT' and self.flow_rate > 10:
            # Convert flow (L/h) to kg/s using density at reservoir temp
            flow_l_per_sec = self.flow_rate / 3600.0
            density = WATER_DENSITY_20C / 1000.0  # kg/L approx
            mass_rate = flow_l_per_sec * density
            self.scale_weight += mass_rate * dt

        # Drain: weight decreases when drain valve open
        if self.valves.get('SV-DRN', False) and self.scale_weight > 0:
            drain_rate = 5.0  # kg/s
            self.scale_weight = max(0, self.scale_weight - drain_rate * dt)

        # Add scale noise
        if self.scale_weight > 0:
            self.scale_weight = max(0, self.scale_weight + random.gauss(0, 0.002))

    def _update_environment(self, dt: float):
        """Slow drift on environmental sensors."""
        self.atm_temp += random.gauss(0, 0.01 * dt)
        self.atm_temp = max(15, min(45, self.atm_temp))
        self.atm_humidity += random.gauss(0, 0.05 * dt)
        self.atm_humidity = max(20, min(95, self.atm_humidity))

        # Reservoir temp drifts very slowly
        self.reservoir_temp += random.gauss(0, 0.005 * dt)
        self.reservoir_temp = max(5, min(40, self.reservoir_temp))

    def _update_reservoir(self, dt: float):
        """Reservoir level changes with flow."""
        if self.flow_rate > 10 and self.diverter_position == 'COLLECT':
            # Level drops when water goes to collection tank
            self.reservoir_level -= (self.flow_rate / 3600.0) * dt * 0.01
        if self.valves.get('SV-DRN', False) and self.scale_weight > 0:
            # Level recovers when draining back to reservoir
            self.reservoir_level += 0.05 * dt
        # Bypass returns water to reservoir (level stays)
        self.reservoir_level = max(0, min(100, self.reservoir_level))

    # ------------------------------------------------------------------
    #  Actuator commands
    # ------------------------------------------------------------------

    def set_valve(self, valve_id: str, state: bool):
        """Open (True) or close (False) a valve."""
        with self._lock:
            if valve_id not in self.valves:
                raise ValueError(f"Unknown valve: {valve_id}")

            # Mutual exclusion: lane valves — only one open at a time
            if state and valve_id in ('BV-L1', 'BV-L2', 'BV-L3'):
                for v in ('BV-L1', 'BV-L2', 'BV-L3'):
                    if v != valve_id:
                        self.valves[v] = False

            self.valves[valve_id] = state
            logger.debug("Valve %s → %s", valve_id, 'OPEN' if state else 'CLOSED')

    def set_diverter(self, position: str):
        """Set diverter: 'COLLECT' or 'BYPASS'."""
        with self._lock:
            if position not in ('COLLECT', 'BYPASS'):
                raise ValueError(f"Invalid diverter position: {position}")
            self.diverter_position = position
            logger.debug("Diverter → %s", position)

    def vfd_start(self, frequency: float = 10.0):
        """Start VFD at target frequency (Hz)."""
        with self._lock:
            frequency = max(0, min(50.0, frequency))
            self.vfd_running = True
            self.vfd_target_freq = frequency
            self.vfd_fault = 0
            logger.debug("VFD start → %.1f Hz", frequency)

    def vfd_stop(self):
        """Normal VFD stop (ramps down)."""
        with self._lock:
            self.vfd_running = False
            self.vfd_target_freq = 0.0
            logger.debug("VFD stop")

    def vfd_emergency_stop(self):
        """Emergency stop — immediate frequency to zero."""
        with self._lock:
            self.vfd_running = False
            self.vfd_target_freq = 0.0
            self.vfd_actual_freq = 0.0
            self.vfd_current = 0.0
            logger.debug("VFD EMERGENCY STOP")

    def vfd_set_frequency(self, frequency: float):
        """Change VFD target frequency while running."""
        with self._lock:
            frequency = max(0, min(50.0, frequency))
            self.vfd_target_freq = frequency

    def tare_scale(self) -> float:
        """Tare the scale. Returns tare offset."""
        with self._lock:
            self.scale_tare_offset = self.scale_weight
            self.scale_tared = True
            logger.debug("Scale tared at %.3f kg", self.scale_tare_offset)
            return self.scale_tare_offset

    def set_tower_light(self, red: bool = False, yellow: bool = False,
                        green: bool = False, buzzer: bool = False):
        """Set tower light state."""
        with self._lock:
            self.tower_red = red
            self.tower_yellow = yellow
            self.tower_green = green
            self.buzzer = buzzer

    def trigger_estop(self):
        """Simulate hardware E-stop activation."""
        with self._lock:
            self.estop_active = True
            self.contactor_on = False
            self.vfd_running = False
            self.vfd_actual_freq = 0.0
            self.vfd_target_freq = 0.0
            self.vfd_current = 0.0
            # All valves close (spring return)
            for v in self.valves:
                self.valves[v] = False
            self.tower_red = True
            self.tower_yellow = False
            self.tower_green = False
            logger.warning("E-STOP ACTIVATED (simulated)")

    def reset_estop(self):
        """Reset E-stop."""
        with self._lock:
            self.estop_active = False
            self.contactor_on = True
            self.tower_red = False
            self.tower_green = True
            logger.info("E-STOP RESET")

    def connect_dut(self, error_pct: float = 1.5):
        """Simulate connecting a DUT meter with a known error percentage."""
        with self._lock:
            self.dut_connected = True
            self.dut_error_pct = error_pct
            self.dut_totalizer = 0.0
            logger.debug("DUT connected, simulated error=%.2f%%", error_pct)

    def disconnect_dut(self):
        """Disconnect DUT."""
        with self._lock:
            self.dut_connected = False

    # ------------------------------------------------------------------
    #  Sensor readings (call update() first for fresh values)
    # ------------------------------------------------------------------

    def read_all_sensors(self) -> dict[str, Any]:
        """Return a snapshot of all sensor values."""
        self.update()
        with self._lock:
            tared_weight = self.scale_weight - self.scale_tare_offset if self.scale_tared else self.scale_weight
            return {
                # Reservoir
                'RES-LVL': round(self.reservoir_level, 1),
                'RES-TEMP': round(self.reservoir_temp, 2),
                # Pressures
                'PT-01': round(self.pressure_upstream, 3),
                'PT-02': round(self.pressure_downstream, 3),
                # Flow
                'FT-01': round(max(0, self.flow_rate), 1),
                'FT-01_totalizer': round(self.em_totalizer, 4),
                # Scale
                'WT-01': round(max(0, tared_weight), 3),
                'WT-01_raw': round(self.scale_weight, 3),
                # DUT
                'DUT_connected': self.dut_connected,
                'DUT_totalizer': round(self.dut_totalizer, 4) if self.dut_connected else None,
                # Environment
                'ATM-TEMP': round(self.atm_temp, 1),
                'ATM-HUM': round(self.atm_humidity, 1),
                # VFD
                'P-01_running': self.vfd_running,
                'P-01_freq': round(self.vfd_actual_freq, 1),
                'P-01_target': round(self.vfd_target_freq, 1),
                'P-01_current': round(max(0, self.vfd_current), 2),
                'P-01_fault': self.vfd_fault,
                # Valves
                'SV1': self.valves['SV1'],
                'BV-L1': self.valves['BV-L1'],
                'BV-L2': self.valves['BV-L2'],
                'BV-L3': self.valves['BV-L3'],
                'SV-DRN': self.valves['SV-DRN'],
                'BV-BP': self.valves['BV-BP'],
                'diverter': self.diverter_position,
                # Tower light
                'TOWER_red': self.tower_red,
                'TOWER_yellow': self.tower_yellow,
                'TOWER_green': self.tower_green,
                'TOWER_buzzer': self.buzzer,
                # Infrastructure
                'MCB': self.mcb_on,
                'CONT': self.contactor_on,
                'ESTOP': self.estop_active,
                # Comms (per-channel)
                'LORA': self.lora_online,
                'B2_VFD': self.b2_vfd_online,
                'B3_METER': self.b3_meter_online,
                'B4_SCALE': self.b4_scale_online,
                'B5_GPIO': self.b5_gpio_online,
                'B6_TANK': self.b6_tank_online,
            }

    def read_device(self, device_id: str) -> dict[str, Any]:
        """Read a single device's state. Returns dict with state/value."""
        all_sensors = self.read_all_sensors()

        # Map device_id to the appropriate sensor data
        if device_id in self.valves:
            return {'state': 'open' if all_sensors[device_id] else 'closed'}
        elif device_id == 'P-01':
            return {
                'state': 'running' if all_sensors['P-01_running'] else 'stopped',
                'frequency': all_sensors['P-01_freq'],
                'target': all_sensors['P-01_target'],
                'current': all_sensors['P-01_current'],
                'fault': all_sensors['P-01_fault'],
            }
        elif device_id == 'TOWER':
            return {
                'red': all_sensors['TOWER_red'],
                'yellow': all_sensors['TOWER_yellow'],
                'green': all_sensors['TOWER_green'],
                'buzzer': all_sensors['TOWER_buzzer'],
            }
        elif device_id == 'DUT':
            return {
                'state': 'connected' if all_sensors['DUT_connected'] else 'disconnected',
                'totalizer': all_sensors['DUT_totalizer'],
            }
        elif device_id in ('MCB', 'CONT'):
            return {'state': 'on' if all_sensors[device_id] else 'off'}
        elif device_id in ('LORA', 'B2_VFD', 'B3_METER', 'B4_SCALE', 'B5_GPIO', 'B6_TANK'):
            return {
                'state': 'online' if all_sensors[device_id] else 'offline',
                'last_seen': time.time(),
            }
        elif device_id in all_sensors:
            return {'value': all_sensors[device_id]}
        else:
            return {'error': f'Unknown device: {device_id}'}

    # ------------------------------------------------------------------
    #  Command interface (matches serial_handler JSON protocol)
    # ------------------------------------------------------------------

    def process_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """
        Process a command dict in the same format as serial_handler.
        Used by sensor_manager when HARDWARE_BACKEND='simulator'.

        Supports all 6-node command sets:
          B2: MB_READ, MB_WRITE (VFD)
          B3: MB_READ, MB_WRITE (EM + DUT)
          B4: SCALE_READ, SCALE_TARE, SCALE_ZERO, SCALE_RAW, PRESSURE_READ
          B5: VALVE, TOWER, SENSOR_READ, GPIO_SET, GPIO_GET
          B6: TANK_READ, TANK_LEVEL, TANK_TEMP
          All: STATUS
        """
        command = cmd.get('cmd', '')

        if command == 'MB_READ':
            return self._handle_mb_read(cmd)
        elif command == 'MB_WRITE':
            return self._handle_mb_write(cmd)
        elif command == 'VALVE':
            return self._handle_valve(cmd)
        elif command == 'DIVERTER':
            return self._handle_diverter(cmd)
        elif command == 'GPIO_SET':
            return self._handle_gpio_set(cmd)
        elif command == 'GPIO_GET':
            return self._handle_gpio_get(cmd)
        elif command == 'SCALE_READ':
            return self._handle_scale_read()
        elif command == 'SCALE_TARE':
            return self._handle_scale_tare()
        elif command == 'SCALE_ZERO':
            return self._handle_scale_tare()
        elif command == 'PRESSURE_READ':
            return self._handle_pressure_read()
        elif command == 'SENSOR_READ':
            return self._handle_sensor_read()
        elif command == 'TANK_READ':
            return self._handle_tank_read()
        elif command == 'TANK_LEVEL':
            return self._handle_tank_level()
        elif command == 'TANK_TEMP':
            return self._handle_tank_temp()
        elif command == 'TOWER':
            return self._handle_tower_cmd(cmd)
        elif command == 'STATUS':
            return self._handle_status()
        else:
            return {'ok': False, 'error': 'UNKNOWN_CMD', 'message': f'Unknown: {command}'}

    def _handle_mb_read(self, cmd: dict) -> dict:
        """Simulate Modbus read. Routes by addr (no bus param needed)."""
        self.update()
        addr = cmd.get('addr', 0)
        reg = cmd.get('reg', 0)

        with self._lock:
            # VFD (addr 1, high register range 0x2000+) — B2 channel
            if addr == 1 and reg >= 0x2000:
                if reg == 0x2100:
                    status = 0x01 if self.vfd_running else 0x00
                    return {'ok': True, 'data': {'values': [status]}}
                elif reg == 0x2103:
                    return {'ok': True, 'data': {'values': [int(self.vfd_actual_freq * 100)]}}
                elif reg == 0x2104:
                    return {'ok': True, 'data': {'values': [int(max(0, self.vfd_current) * 100)]}}
                elif reg == 0x2105:
                    return {'ok': True, 'data': {'values': [self.vfd_fault]}}

            # EM Flow Meter (addr 1, low register range) — B3 channel
            elif addr == 1:
                if reg == 0:
                    return {'ok': True, 'data': {'values': [round(self.flow_rate, 1), round(self.em_totalizer, 4)]}}
                elif reg == 2:
                    return {'ok': True, 'data': {'values': [round(self.em_totalizer, 4)]}}

            # DUT (addr 20) — B3 channel
            elif addr == 20:
                if self.dut_connected:
                    return {'ok': True, 'data': {'values': [round(self.dut_totalizer, 4)]}}
                else:
                    return {'ok': False, 'error': 'TIMEOUT', 'message': 'DUT not connected'}

        return {'ok': False, 'error': 'INVALID_ADDR', 'message': f'No device at addr={addr}'}

    def _handle_mb_write(self, cmd: dict) -> dict:
        """Simulate Modbus write. Routes by addr (no bus param needed)."""
        addr = cmd.get('addr', 0)
        reg = cmd.get('reg', 0)
        value = cmd.get('value', 0)

        with self._lock:
            # VFD (addr 1, high register range) — B2 channel
            if addr == 1 and reg >= 0x2000:
                if reg == 0x2000:  # Control word
                    if value == 0x0001:  # Run forward
                        self.vfd_running = True
                        return {'ok': True}
                    elif value == 0x0003:  # Emergency stop
                        self.vfd_emergency_stop()
                        return {'ok': True}
                    elif value == 0x0005:  # Normal stop
                        self.vfd_stop()
                        return {'ok': True}
                elif reg == 0x2001:  # Frequency setpoint (Hz * 100)
                    freq = value / 100.0
                    self.vfd_set_frequency(freq)
                    return {'ok': True}

        return {'ok': False, 'error': 'INVALID_WRITE', 'message': f'Cannot write addr={addr} reg={reg}'}

    # ------------------------------------------------------------------
    #  B4 Scale+Pressure command handlers
    # ------------------------------------------------------------------

    def _handle_scale_read(self) -> dict:
        """Simulate SCALE_READ (B4)."""
        self.update()
        with self._lock:
            w = self.scale_weight - self.scale_tare_offset if self.scale_tared else self.scale_weight
            return {'ok': True, 'data': {
                'weight_kg': round(max(0, w), 3),
                'stale': False,
                'age_ms': 0,
            }}

    def _handle_scale_tare(self) -> dict:
        """Simulate SCALE_TARE / SCALE_ZERO (B4)."""
        self.tare_scale()
        return {'ok': True}

    def _handle_pressure_read(self) -> dict:
        """Simulate PRESSURE_READ (B4). Returns MPa."""
        self.update()
        with self._lock:
            return {'ok': True, 'data': {
                'pt01_mpa': round(self.pressure_upstream / 10.0, 4),  # bar → MPa
                'pt02_mpa': round(self.pressure_downstream / 10.0, 4),
                'pt01_ma': 0.0,
                'pt02_ma': 0.0,
            }}

    # ------------------------------------------------------------------
    #  B5 GPIO Controller command handlers
    # ------------------------------------------------------------------

    def _handle_sensor_read(self) -> dict:
        """Simulate SENSOR_READ (B5). Returns atm sensors + E-stop."""
        with self._lock:
            return {'ok': True, 'data': {
                'atm_temp_c': round(self.atm_temp, 1),
                'atm_hum_pct': round(self.atm_humidity, 1),
                'estop_active': self.estop_active,
            }}

    def _handle_tower_cmd(self, cmd: dict) -> dict:
        """Simulate TOWER command (B5)."""
        r = cmd.get('r', -1)
        g = cmd.get('g', -1)
        buz = cmd.get('buz', -1)
        with self._lock:
            if r >= 0:
                self.tower_red = bool(r)
            if g >= 0:
                self.tower_green = bool(g)
            if buz >= 0:
                self.buzzer = bool(buz)
        return {'ok': True}

    # ------------------------------------------------------------------
    #  B6 Reservoir Monitor command handlers
    # ------------------------------------------------------------------

    def _handle_tank_read(self) -> dict:
        """Simulate TANK_READ (B6). Returns level + temp."""
        self.update()
        with self._lock:
            return {'ok': True, 'data': {
                'level_pct': round(self.reservoir_level, 1),
                'dist_cm': 0.0,
                'temp_c': round(self.reservoir_temp, 2),
            }}

    def _handle_tank_level(self) -> dict:
        """Simulate TANK_LEVEL (B6)."""
        self.update()
        with self._lock:
            return {'ok': True, 'data': {
                'level_pct': round(self.reservoir_level, 1),
                'dist_cm': 0.0,
            }}

    def _handle_tank_temp(self) -> dict:
        """Simulate TANK_TEMP (B6)."""
        self.update()
        with self._lock:
            return {'ok': True, 'data': {
                'temp_c': round(self.reservoir_temp, 2),
                'sensor_ok': True,
            }}

    # ------------------------------------------------------------------
    #  B5 GPIO valve/diverter/gpio handlers
    # ------------------------------------------------------------------

    def _handle_valve(self, cmd: dict) -> dict:
        """Handle VALVE command. Accepts both 'name' (firmware) and 'valve' (legacy)."""
        valve = cmd.get('name', '') or cmd.get('valve', '')
        # Translate firmware underscores back to Django hyphens
        valve = valve.replace('_', '-')
        action = cmd.get('action', '').upper()
        try:
            self.set_valve(valve, action == 'OPEN')
            return {'ok': True, 'data': {'valve': valve, 'state': action.lower()}}
        except ValueError as e:
            return {'ok': False, 'error': 'INVALID_VALVE', 'message': str(e)}

    def _handle_diverter(self, cmd: dict) -> dict:
        """Handle DIVERTER command."""
        position = cmd.get('position', '').upper()
        try:
            self.set_diverter(position)
            return {'ok': True, 'data': {'position': position}}
        except ValueError as e:
            return {'ok': False, 'error': 'INVALID_POSITION', 'message': str(e)}

    def _handle_gpio_set(self, cmd: dict) -> dict:
        """Handle GPIO_SET command."""
        pin = cmd.get('pin', '')
        state = cmd.get('state', 0)

        with self._lock:
            if pin in self.valves:
                self.valves[pin] = bool(state)
            elif pin == 'TOWER_RED':
                self.tower_red = bool(state)
            elif pin == 'TOWER_YELLOW':
                self.tower_yellow = bool(state)
            elif pin == 'TOWER_GREEN':
                self.tower_green = bool(state)
            elif pin == 'BUZZER':
                self.buzzer = bool(state)
            else:
                return {'ok': False, 'error': 'INVALID_PIN', 'message': f'Unknown pin: {pin}'}

        return {'ok': True, 'data': {'pin': pin, 'state': state}}

    def _handle_gpio_get(self, cmd: dict) -> dict:
        """Handle GPIO_GET command."""
        pin = cmd.get('pin', '')

        with self._lock:
            if pin in self.valves:
                return {'ok': True, 'data': {'pin': pin, 'state': int(self.valves[pin])}}
            elif pin == 'ESTOP':
                return {'ok': True, 'data': {'pin': pin, 'state': int(self.estop_active)}}
            elif pin == 'CONT':
                return {'ok': True, 'data': {'pin': pin, 'state': int(self.contactor_on)}}

        return {'ok': False, 'error': 'INVALID_PIN', 'message': f'Unknown pin: {pin}'}

    def _handle_status(self) -> dict:
        """Handle STATUS command — return bridge health."""
        return {
            'ok': True,
            'data': {
                'uptime': int(time.time() - self._last_update),
                'estop': self.estop_active,
                'contactor': self.contactor_on,
            },
        }


# ---------------------------------------------------------------------------
#  Module-level singleton (lazy init)
# ---------------------------------------------------------------------------

_simulator: HardwareSimulator | None = None
_sim_lock = threading.Lock()


def get_simulator() -> HardwareSimulator:
    """Get or create the global simulator instance."""
    global _simulator
    if _simulator is None:
        with _sim_lock:
            if _simulator is None:
                _simulator = HardwareSimulator()
                logger.info("Hardware simulator initialised")
    return _simulator
