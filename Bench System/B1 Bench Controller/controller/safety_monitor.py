"""
Safety watchdog for the test bench.

Runs a parallel monitoring thread that checks interlocks every 200ms.
Triggers emergency stop and raises alarms on safety violations.

Monitored conditions (from settings_bench.py):
  - Upstream pressure > 8.0 bar (SAFETY_PRESSURE_MAX)
  - Reservoir level < 20% (SAFETY_RESERVOIR_MIN)
  - Water temperature outside 5-40 C (SAFETY_TEMP_MIN/MAX)
  - Scale overload > 180 kg (SAFETY_SCALE_MAX)
  - E-stop hardware signal active
  - Contactor / MCB trip
  - VFD fault code non-zero
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)


class AlarmSeverity(Enum):
    WARNING = 'warning'
    CRITICAL = 'critical'
    EMERGENCY = 'emergency'


class AlarmCode(Enum):
    OVERPRESSURE = 'OVERPRESSURE'
    LOW_RESERVOIR = 'LOW_RESERVOIR'
    TEMP_HIGH = 'TEMP_HIGH'
    TEMP_LOW = 'TEMP_LOW'
    SCALE_OVERLOAD = 'SCALE_OVERLOAD'
    ESTOP_ACTIVE = 'ESTOP_ACTIVE'
    CONTACTOR_TRIP = 'CONTACTOR_TRIP'
    MCB_TRIP = 'MCB_TRIP'
    VFD_FAULT = 'VFD_FAULT'


@dataclass
class SafetyAlarm:
    """A single safety alarm event."""
    code: AlarmCode
    severity: AlarmSeverity
    message: str
    value: float | None = None
    limit: float | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_emergency(self) -> bool:
        return self.severity == AlarmSeverity.EMERGENCY


class SafetyMonitor:
    """
    Parallel safety watchdog.

    Usage:
        monitor = SafetyMonitor(sensor_manager, hardware_module)
        monitor.on_alarm(my_alarm_handler)
        monitor.start()

        # Check status
        if monitor.has_active_alarms:
            alarms = monitor.active_alarms

        monitor.stop()
    """

    def __init__(self, sensor_manager=None, hardware=None):
        """
        Args:
            sensor_manager: SensorManager instance for reading sensors.
            hardware: Hardware module (controller.hardware) for emergency_stop.
        """
        self._sensor_manager = sensor_manager
        self._hardware = hardware

        # Limits from settings
        self._pressure_max = getattr(settings, 'SAFETY_PRESSURE_MAX', 8.0)
        self._reservoir_min = getattr(settings, 'SAFETY_RESERVOIR_MIN', 20.0)
        self._scale_max = getattr(settings, 'SAFETY_SCALE_MAX', 180.0)
        self._temp_min = getattr(settings, 'SAFETY_TEMP_MIN', 5.0)
        self._temp_max = getattr(settings, 'SAFETY_TEMP_MAX', 40.0)

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._poll_interval = 0.2  # 200ms

        # Alarm state
        self._active_alarms: dict[AlarmCode, SafetyAlarm] = {}
        self._alarm_history: list[SafetyAlarm] = []
        self._callbacks: list[Callable[[SafetyAlarm], None]] = []
        self._estop_triggered = False

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def start(self, poll_interval: float = 0.2):
        """Start the safety monitoring thread."""
        if self._running:
            return
        self._poll_interval = poll_interval
        self._running = True
        self._estop_triggered = False
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name='SafetyMonitor',
            daemon=True,
        )
        self._thread.start()
        logger.info("Safety monitor started (%.0fms interval)", poll_interval * 1000)

    def stop(self):
        """Stop the safety monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Safety monitor stopped")

    def on_alarm(self, callback: Callable[['SafetyAlarm'], None]):
        """Register a callback for alarm events."""
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    #  Monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._check_all()
            except Exception:
                logger.exception("Safety monitor check error")
            time.sleep(self._poll_interval)

    def _check_all(self):
        """Run all safety checks against current sensor snapshot."""
        if not self._sensor_manager:
            return

        snap = self._sensor_manager.latest
        alarms: list[SafetyAlarm] = []

        # --- Overpressure (B4 Scale+Pressure Bridge) ---
        if snap.b4_scale_online and snap.pressure_upstream_bar > self._pressure_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.OVERPRESSURE,
                severity=AlarmSeverity.EMERGENCY,
                message=f"Upstream pressure {snap.pressure_upstream_bar:.2f} bar > {self._pressure_max} bar limit",
                value=snap.pressure_upstream_bar,
                limit=self._pressure_max,
            ))

        # --- Low reservoir (B6 Reservoir Monitor) ---
        if snap.b6_tank_online and snap.reservoir_level_pct < self._reservoir_min:
            alarms.append(SafetyAlarm(
                code=AlarmCode.LOW_RESERVOIR,
                severity=AlarmSeverity.CRITICAL,
                message=f"Reservoir level {snap.reservoir_level_pct:.1f}% < {self._reservoir_min}% minimum",
                value=snap.reservoir_level_pct,
                limit=self._reservoir_min,
            ))

        # --- Temperature out of range (B6 Reservoir Monitor) ---
        if snap.b6_tank_online and snap.water_temp_c > self._temp_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.TEMP_HIGH,
                severity=AlarmSeverity.CRITICAL,
                message=f"Water temperature {snap.water_temp_c:.1f} C > {self._temp_max} C limit",
                value=snap.water_temp_c,
                limit=self._temp_max,
            ))
        if snap.b6_tank_online and snap.water_temp_c < self._temp_min:
            alarms.append(SafetyAlarm(
                code=AlarmCode.TEMP_LOW,
                severity=AlarmSeverity.CRITICAL,
                message=f"Water temperature {snap.water_temp_c:.1f} C < {self._temp_min} C limit",
                value=snap.water_temp_c,
                limit=self._temp_min,
            ))

        # --- Scale overload (B4 Scale+Pressure Bridge) ---
        if snap.b4_scale_online and snap.weight_raw_kg > self._scale_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.SCALE_OVERLOAD,
                severity=AlarmSeverity.EMERGENCY,
                message=f"Scale weight {snap.weight_raw_kg:.1f} kg > {self._scale_max} kg limit",
                value=snap.weight_raw_kg,
                limit=self._scale_max,
            ))

        # --- E-stop active (B5 GPIO Controller) ---
        if snap.b5_gpio_online and snap.estop_active:
            alarms.append(SafetyAlarm(
                code=AlarmCode.ESTOP_ACTIVE,
                severity=AlarmSeverity.EMERGENCY,
                message="Hardware E-STOP is active",
            ))

        # --- Contactor trip (B5 GPIO Controller) ---
        if snap.b5_gpio_online and not snap.contactor_on:
            alarms.append(SafetyAlarm(
                code=AlarmCode.CONTACTOR_TRIP,
                severity=AlarmSeverity.EMERGENCY,
                message="Main contactor has tripped",
            ))

        # --- MCB trip (B5 GPIO Controller) ---
        if snap.b5_gpio_online and not snap.mcb_on:
            alarms.append(SafetyAlarm(
                code=AlarmCode.MCB_TRIP,
                severity=AlarmSeverity.EMERGENCY,
                message="MCB has tripped",
            ))

        # --- VFD fault (B2 VFD Bridge) ---
        if snap.b2_vfd_online and snap.vfd_fault != 0:
            alarms.append(SafetyAlarm(
                code=AlarmCode.VFD_FAULT,
                severity=AlarmSeverity.CRITICAL,
                message=f"VFD fault code: {snap.vfd_fault}",
                value=float(snap.vfd_fault),
            ))

        # Process alarms
        self._process_alarms(alarms)

    def _process_alarms(self, new_alarms: list[SafetyAlarm]):
        """Process newly detected alarms."""
        with self._lock:
            new_codes = {a.code for a in new_alarms}

            # Clear alarms that are no longer active
            cleared = [code for code in self._active_alarms if code not in new_codes]
            for code in cleared:
                logger.info("Safety alarm CLEARED: %s", code.value)
                del self._active_alarms[code]

            # Raise new alarms
            for alarm in new_alarms:
                if alarm.code not in self._active_alarms:
                    # New alarm
                    self._active_alarms[alarm.code] = alarm
                    self._alarm_history.append(alarm)
                    logger.warning("Safety alarm RAISED: %s — %s", alarm.code.value, alarm.message)
                    self._fire_callbacks(alarm)

                    # Trigger emergency stop for emergency-level alarms
                    if alarm.is_emergency and not self._estop_triggered:
                        self._trigger_emergency_stop(alarm)

    def _fire_callbacks(self, alarm: SafetyAlarm):
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(alarm)
            except Exception:
                logger.exception("Alarm callback error")

    def _trigger_emergency_stop(self, alarm: SafetyAlarm):
        """Trigger hardware emergency stop."""
        self._estop_triggered = True
        logger.critical(
            "EMERGENCY STOP triggered by safety monitor: %s", alarm.message
        )
        if self._hardware:
            try:
                self._hardware.emergency_stop()
            except Exception:
                logger.exception("Failed to execute emergency stop")

    # ------------------------------------------------------------------
    #  Status API
    # ------------------------------------------------------------------

    @property
    def has_active_alarms(self) -> bool:
        """Whether any alarms are currently active."""
        with self._lock:
            return len(self._active_alarms) > 0

    @property
    def active_alarms(self) -> list[SafetyAlarm]:
        """List of currently active alarms."""
        with self._lock:
            return list(self._active_alarms.values())

    @property
    def alarm_history(self) -> list[SafetyAlarm]:
        """Full alarm history for this session."""
        with self._lock:
            return list(self._alarm_history)

    @property
    def is_safe(self) -> bool:
        """True if no emergency alarms are active."""
        with self._lock:
            return not any(a.is_emergency for a in self._active_alarms.values())

    def clear_estop_latch(self):
        """Clear the E-stop latch so monitoring resumes normally."""
        with self._lock:
            self._estop_triggered = False
            logger.info("Safety monitor E-stop latch cleared")

    def check_snapshot(self, snapshot) -> list[SafetyAlarm]:
        """
        Check a single snapshot for alarms without firing callbacks.
        Useful for pre-flight checks before starting a test.

        Returns list of alarms (empty if all clear).
        """
        alarms = []

        if snapshot.pressure_upstream_bar > self._pressure_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.OVERPRESSURE,
                severity=AlarmSeverity.EMERGENCY,
                message=f"Pressure {snapshot.pressure_upstream_bar:.2f} bar exceeds {self._pressure_max} bar",
                value=snapshot.pressure_upstream_bar,
                limit=self._pressure_max,
            ))

        if snapshot.reservoir_level_pct < self._reservoir_min:
            alarms.append(SafetyAlarm(
                code=AlarmCode.LOW_RESERVOIR,
                severity=AlarmSeverity.CRITICAL,
                message=f"Reservoir {snapshot.reservoir_level_pct:.1f}% below {self._reservoir_min}%",
                value=snapshot.reservoir_level_pct,
                limit=self._reservoir_min,
            ))

        if snapshot.water_temp_c > self._temp_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.TEMP_HIGH, severity=AlarmSeverity.CRITICAL,
                message=f"Temp {snapshot.water_temp_c:.1f} C exceeds max",
                value=snapshot.water_temp_c, limit=self._temp_max))

        if snapshot.water_temp_c < self._temp_min:
            alarms.append(SafetyAlarm(
                code=AlarmCode.TEMP_LOW, severity=AlarmSeverity.CRITICAL,
                message=f"Temp {snapshot.water_temp_c:.1f} C below min",
                value=snapshot.water_temp_c, limit=self._temp_min))

        if snapshot.weight_raw_kg > self._scale_max:
            alarms.append(SafetyAlarm(
                code=AlarmCode.SCALE_OVERLOAD, severity=AlarmSeverity.EMERGENCY,
                message=f"Scale {snapshot.weight_raw_kg:.1f} kg exceeds max",
                value=snapshot.weight_raw_kg, limit=self._scale_max))

        if snapshot.estop_active:
            alarms.append(SafetyAlarm(
                code=AlarmCode.ESTOP_ACTIVE, severity=AlarmSeverity.EMERGENCY,
                message="E-STOP active"))

        if not snapshot.contactor_on:
            alarms.append(SafetyAlarm(
                code=AlarmCode.CONTACTOR_TRIP, severity=AlarmSeverity.EMERGENCY,
                message="Contactor tripped"))

        if not snapshot.mcb_on:
            alarms.append(SafetyAlarm(
                code=AlarmCode.MCB_TRIP, severity=AlarmSeverity.EMERGENCY,
                message="MCB tripped"))

        if snapshot.vfd_fault != 0:
            alarms.append(SafetyAlarm(
                code=AlarmCode.VFD_FAULT, severity=AlarmSeverity.CRITICAL,
                message=f"VFD fault {snapshot.vfd_fault}",
                value=float(snapshot.vfd_fault)))

        return alarms
