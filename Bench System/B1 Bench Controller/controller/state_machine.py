"""
Test execution state machine.

Orchestrates a full ISO 4064 Q1-Q8 calibration test cycle through 12 states.
Runs in a background daemon thread, coordinating all controller singletons
(VFD, valves, PID, gravimetric, DUT, safety, tower light, sensors).

Thread-safe. Abortable from any external thread (UI, safety monitor).

Usage:
    from controller.state_machine import start_test_machine, abort_active_test

    sm = start_test_machine(test_id=42)
    sm.abort('operator request')
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY_S = 2.0
SENSOR_RECORD_INTERVAL_S = 2.0
FLOW_STABILIZE_TIMEOUT_S = 120.0
PUMP_CONFIRM_TIMEOUT_S = 10.0
DRAIN_TIMEOUT_S = 60.0
MANUAL_DUT_TIMEOUT_S = 300.0
ABORT_CHECK_INTERVAL_S = 0.2


# ---------------------------------------------------------------------------
#  Enums and exceptions
# ---------------------------------------------------------------------------

class TestState(Enum):
    IDLE = 'IDLE'
    PRE_CHECK = 'PRE_CHECK'
    LINE_SELECT = 'LINE_SELECT'
    PUMP_START = 'PUMP_START'
    FLOW_STABILIZE = 'FLOW_STABILIZE'
    TARE_SCALE = 'TARE_SCALE'
    MEASURE = 'MEASURE'
    CALCULATE = 'CALCULATE'
    DRAIN = 'DRAIN'
    NEXT_POINT = 'NEXT_POINT'
    COMPLETE = 'COMPLETE'
    EMERGENCY_STOP = 'EMERGENCY_STOP'


class AbortError(Exception):
    """Raised when abort is requested."""
    pass


class PreCheckError(Exception):
    """Raised when pre-check validation fails."""
    pass


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QPointParams:
    """Parameters for a single Q-point from ISO4064Standard."""
    q_point: str
    flow_rate_lph: float
    test_volume_l: float
    duration_s: int
    mpe_pct: float
    zone: str


@dataclass
class ManualDUTRequest:
    """Request for operator to enter a DUT reading."""
    test_id: int
    q_point: str
    reading_type: str      # 'before' or 'after'
    requested_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
#  State Machine
# ---------------------------------------------------------------------------

class TestStateMachine:
    """Orchestrates a full ISO 4064 Q1-Q8 test cycle."""

    def __init__(self, test_id: int):
        self._test_id = test_id
        self._state = TestState.IDLE
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

        # Abort mechanism
        self._abort_requested = False
        self._abort_reason = ''

        # Manual DUT callback support
        self._manual_dut_event = threading.Event()
        self._manual_dut_callbacks: list = []

        # Sensor recording throttle
        self._last_sensor_record = 0.0

        # Q-point tracking
        self._q_points: list[QPointParams] = []
        self._current_q_idx = 0

        # Controller references (filled in _initialize)
        self._sensor_mgr = None
        self._vfd = None
        self._valves = None
        self._pid = None
        self._safety = None
        self._tower = None
        self._grav = None
        self._dut = None

        # Test and meter (filled in _initialize)
        self._test = None
        self._meter = None

        # Measurement results (set in _state_measure, used in _state_calculate)
        self._last_grav_result = None
        self._last_dut_reading = None
        self._last_snap = None

    # ==================================================================
    #  Public API
    # ==================================================================

    @property
    def state(self) -> TestState:
        with self._lock:
            return self._state

    @property
    def test_id(self) -> int:
        return self._test_id

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_q_point(self) -> str:
        with self._lock:
            if 0 <= self._current_q_idx < len(self._q_points):
                return self._q_points[self._current_q_idx].q_point
            return ''

    def start(self):
        """Start the state machine in a background daemon thread."""
        if self.is_running:
            raise RuntimeError("State machine already running")
        self._thread = threading.Thread(
            target=self._run,
            name=f'TestSM-{self._test_id}',
            daemon=True,
        )
        self._thread.start()
        logger.info("State machine started for Test #%d", self._test_id)

    def abort(self, reason: str = ''):
        """Request abort from any thread (UI button, safety callback)."""
        with self._lock:
            self._abort_requested = True
            self._abort_reason = reason
        self._manual_dut_event.set()
        logger.warning("Abort requested for Test #%d: %s", self._test_id, reason)

    def on_manual_dut_request(self, callback):
        """Register callback for manual DUT entry prompts."""
        self._manual_dut_callbacks.append(callback)

    def submit_manual_dut_reading(self, reading_type: str, value: float,
                                   entered_by=None) -> bool:
        """Called by UI when operator enters a manual DUT reading."""
        if reading_type == 'before':
            ok = self._dut.set_before_reading(value)
        elif reading_type == 'after':
            ok = self._dut.set_after_reading(value)
        else:
            return False
        if ok:
            # Persist the manual entry in DB (non-fatal)
            try:
                close_old_connections()
                from testing.services import record_manual_dut_entry
                record_manual_dut_entry(
                    test=self._test,
                    q_point=self.current_q_point,
                    reading_type=reading_type,
                    value=value,
                    entered_by=entered_by,
                )
                close_old_connections()
            except Exception:
                logger.debug("Failed to record DUT manual entry", exc_info=True)
            self._manual_dut_event.set()
        return ok

    def join(self, timeout: float = None):
        """Wait for the state machine thread to finish."""
        if self._thread:
            self._thread.join(timeout=timeout)

    # ==================================================================
    #  Main run loop
    # ==================================================================

    def _run(self):
        """Main state machine execution."""
        try:
            self._db_safe(self._initialize)
            self._db_safe(self._state_pre_check)
            self._state_line_select()
            self._state_pump_start()

            for q_idx in range(len(self._q_points)):
                self._current_q_idx = q_idx
                q = self._q_points[q_idx]
                self._state_flow_stabilize(q)
                self._state_tare_scale()
                self._state_measure(q)
                self._db_safe(self._state_calculate, q)
                self._state_drain()
                self._db_safe(self._state_next_point, q_idx)

            self._db_safe(self._state_complete)
        except AbortError:
            self._db_safe(self._state_emergency_stop, self._abort_reason)
        except PreCheckError as e:
            self._db_safe(self._state_emergency_stop, f"Pre-check failed: {e}")
        except Exception as e:
            logger.exception("State machine error for Test #%d", self._test_id)
            self._db_safe(self._state_emergency_stop, f"Unexpected error: {e}")
        finally:
            self._cleanup()

    # ==================================================================
    #  State handlers
    # ==================================================================

    def _initialize(self):
        """Load test, resolve Q-points, acquire controller references."""
        from testing.models import Test, ISO4064Standard
        from testing.services import start_test
        from controller.hardware import (
            get_sensor_manager, get_vfd_controller, get_valve_controller,
            get_pid_controller, get_safety_monitor, get_tower_light,
            get_gravimetric_engine, get_dut_interface,
        )
        from controller.dut_interface import DUTMode

        self._set_state(TestState.IDLE)

        self._test = Test.objects.select_related('meter').get(pk=self._test_id)
        self._meter = self._test.meter

        # Load Q-point parameters
        iso_params = ISO4064Standard.objects.filter(
            meter_size=self._meter.meter_size,
            meter_class=self._test.test_class,
        ).order_by('q_point')

        self._q_points = [
            QPointParams(
                q_point=p.q_point,
                flow_rate_lph=p.flow_rate_lph,
                test_volume_l=p.test_volume_l,
                duration_s=p.duration_s,
                mpe_pct=p.mpe_pct,
                zone=p.zone,
            )
            for p in iso_params
        ]

        if not self._q_points:
            raise PreCheckError(
                f"No ISO 4064 parameters for {self._meter.meter_size} / {self._test.test_class}"
            )

        # Acquire controller singletons
        self._sensor_mgr = get_sensor_manager()
        self._vfd = get_vfd_controller()
        self._valves = get_valve_controller()
        self._pid = get_pid_controller()
        self._safety = get_safety_monitor()
        self._tower = get_tower_light()
        self._grav = get_gravimetric_engine()

        dut_mode = DUTMode.RS485 if self._meter.dut_mode == 'rs485' else DUTMode.MANUAL
        self._dut = get_dut_interface(mode=dut_mode)
        if self._dut.mode != dut_mode:
            self._dut.set_mode(dut_mode)

        # Register safety alarm callback
        self._safety.on_alarm(self._on_safety_alarm)

        # Start the test
        start_test(self._test)
        logger.info("Test #%d initialized: %s %s, %d Q-points, DUT=%s",
                     self._test_id, self._meter.meter_size, self._test.test_class,
                     len(self._q_points), self._meter.dut_mode)

    def _state_pre_check(self):
        """Validate all hardware systems before starting."""
        self._set_state(TestState.PRE_CHECK)
        self._update_test_state('Q1', 'PRE_CHECK')
        self._check_abort()

        from controller.tower_light import LightPattern
        self._tower.set_pattern(LightPattern.TESTING)

        snap = self._sensor_mgr.latest
        alarms = self._safety.check_snapshot(snap)
        emergency_alarms = [a for a in alarms if a.is_emergency]
        if emergency_alarms:
            msgs = '; '.join(a.message for a in emergency_alarms)
            raise PreCheckError(f"Safety alarms: {msgs}")

        if snap.timestamp == 0:
            raise PreCheckError("Sensor manager has no data")

        vfd_status = self._vfd.read_status()
        if vfd_status.faulted:
            raise PreCheckError(f"VFD fault code {vfd_status.fault_code}")
        if not vfd_status.connected:
            raise PreCheckError("VFD not connected")

        from controller.dut_interface import DUTMode
        if self._dut.mode == DUTMode.RS485 and not self._dut.is_connected():
            raise PreCheckError("DUT meter not responding on RS485")

        if snap.reservoir_level_pct < 30.0:
            raise PreCheckError(
                f"Reservoir level too low: {snap.reservoir_level_pct:.1f}%"
            )

        self._record_sensor_reading('Q1', trigger='event', event_label='pre_check_pass')
        logger.info("Test #%d PRE_CHECK passed", self._test_id)

    def _state_line_select(self):
        """Open the correct lane valve for the meter size."""
        self._set_state(TestState.LINE_SELECT)
        self._update_test_state_safe('Q1', 'LINE_SELECT')
        self._check_abort()

        ok = self._valves.select_lane(self._meter.meter_size)
        if not ok:
            raise AbortError(f"Failed to select lane for {self._meter.meter_size}")

        self._valves.open_valve('SV1')
        self._valves.set_diverter('BYPASS')

        logger.info("Test #%d LINE_SELECT: %s, SV1 open, BYPASS",
                     self._test_id, self._meter.meter_size)

    def _state_pump_start(self):
        """Start VFD and confirm it is running."""
        self._set_state(TestState.PUMP_START)
        self._update_test_state_safe('Q1', 'PUMP_START')
        self._check_abort()

        initial_freq = getattr(settings, 'PID_OUTPUT_MIN', 5.0)
        ok = self._vfd.start(frequency=initial_freq)
        if not ok:
            raise AbortError("VFD start command failed")

        deadline = time.time() + PUMP_CONFIRM_TIMEOUT_S
        while time.time() < deadline:
            self._check_abort()
            status = self._vfd.read_status()
            if status.running and status.frequency_hz > 0:
                logger.info("Test #%d PUMP_START confirmed: %.1f Hz",
                            self._test_id, status.frequency_hz)
                return
            time.sleep(ABORT_CHECK_INTERVAL_S)

        raise AbortError("VFD did not confirm running within timeout")

    def _state_flow_stabilize(self, q: QPointParams):
        """PID loop to reach and stabilize at target flow rate."""
        self._set_state(TestState.FLOW_STABILIZE)
        self._update_test_state_safe(q.q_point, 'FLOW_STABILIZE')

        from controller.tower_light import LightPattern
        self._tower.set_pattern(LightPattern.STABILIZING)

        self._pid.reset()
        self._pid.set_target(q.flow_rate_lph)
        self._pid.enable()

        deadline = time.time() + FLOW_STABILIZE_TIMEOUT_S
        while time.time() < deadline:
            self._check_abort()

            snap = self._sensor_mgr.latest
            output_hz = self._pid.compute(snap.flow_rate_lph)
            self._vfd.set_frequency(output_hz)
            self._maybe_record_sensor(q.q_point)

            if self._pid.is_stable:
                logger.info("Test #%d %s stable at %.1f L/h (target %.1f)",
                            self._test_id, q.q_point, snap.flow_rate_lph, q.flow_rate_lph)
                self._tower.set_pattern(LightPattern.TESTING)
                return

            time.sleep(ABORT_CHECK_INTERVAL_S)

        # Timeout — non-fatal, proceed
        logger.warning("Test #%d FLOW_STABILIZE timeout for %s", self._test_id, q.q_point)
        self._tower.set_pattern(LightPattern.TESTING)

    def _state_tare_scale(self):
        """Zero the weighing scale before collection."""
        self._set_state(TestState.TARE_SCALE)
        q_label = self._q_points[self._current_q_idx].q_point
        self._update_test_state_safe(q_label, 'TARE_SCALE')
        self._check_abort()

        self._valves.set_diverter('BYPASS')
        time.sleep(0.5)

        ok = self._retry(lambda: self._grav.tare(), "Scale tare")
        if not ok:
            raise AbortError("Scale tare failed after retries")

        self._record_sensor_reading_safe(q_label, trigger='event', event_label='tare_complete')
        logger.info("Test #%d TARE complete for %s", self._test_id, q_label)

    def _state_measure(self, q: QPointParams):
        """Divert water to collection, read DUT, wait for target weight."""
        self._set_state(TestState.MEASURE)
        self._update_test_state_safe(q.q_point, 'MEASURE')
        self._check_abort()

        self._dut.reset()

        # DUT before reading
        self._read_dut('before', q)

        # Start collection
        self._record_sensor_reading_safe(q.q_point, trigger='event', event_label='collect_start')
        self._grav.start_collection()

        # Wait for target weight
        target_weight_kg = q.test_volume_l * 0.998
        max_wait = q.duration_s * 2.0
        deadline = time.time() + max_wait

        while time.time() < deadline:
            self._check_abort()
            snap = self._sensor_mgr.latest
            self._maybe_record_sensor(q.q_point)

            output_hz = self._pid.compute(snap.flow_rate_lph)
            self._vfd.set_frequency(output_hz)

            if snap.weight_kg >= target_weight_kg:
                break

            time.sleep(ABORT_CHECK_INTERVAL_S)

        # Stop collection and measure
        grav_result = self._grav.stop_collection_and_measure()

        # DUT after reading
        self._read_dut('after', q)

        self._last_grav_result = grav_result
        self._last_dut_reading = self._dut.get_reading()
        self._last_snap = self._sensor_mgr.latest

        self._record_sensor_reading_safe(q.q_point, trigger='event', event_label='collect_end')
        logger.info("Test #%d MEASURE %s: grav=%.4f L, DUT=%.4f L",
                     self._test_id, q.q_point, grav_result.volume_l,
                     self._last_dut_reading.volume_l)

    def _state_calculate(self, q: QPointParams):
        """Compute error%, pass/fail via services."""
        self._set_state(TestState.CALCULATE)
        self._update_test_state(q.q_point, 'CALCULATE')
        self._check_abort()

        from testing.services import process_q_point_result

        try:
            result = process_q_point_result(
                test=self._test,
                q_point=q.q_point,
                gravimetric_result=self._last_grav_result,
                dut_reading=self._last_dut_reading,
                pressure_up_bar=self._last_snap.pressure_upstream_bar,
                pressure_dn_bar=self._last_snap.pressure_downstream_bar,
            )
            verdict = "PASS" if result.passed else "FAIL"
            logger.info("Test #%d %s: error=%.3f%%, MPE=%.1f%% -> %s",
                        self._test_id, q.q_point, result.error_pct, result.mpe_pct, verdict)
        except Exception as e:
            logger.error("Test #%d CALCULATE %s error: %s", self._test_id, q.q_point, e)

    def _state_drain(self):
        """Drain collection tank."""
        self._set_state(TestState.DRAIN)
        q_label = self._q_points[self._current_q_idx].q_point
        self._update_test_state_safe(q_label, 'DRAIN')
        self._check_abort()

        from controller.tower_light import LightPattern
        self._tower.set_pattern(LightPattern.DRAINING)

        self._pid.disable()
        self._vfd.set_frequency(getattr(settings, 'PID_OUTPUT_MIN', 5.0))

        ok = self._grav.drain_tank(timeout_s=DRAIN_TIMEOUT_S)
        if not ok:
            logger.warning("Test #%d DRAIN timeout for %s", self._test_id, q_label)

        self._tower.set_pattern(LightPattern.TESTING)

    def _state_next_point(self, q_idx: int):
        """Advance to next Q-point."""
        self._set_state(TestState.NEXT_POINT)
        current_q = self._q_points[q_idx].q_point
        self._update_test_state(current_q, 'NEXT_POINT')
        self._check_abort()

        next_idx = q_idx + 1
        if next_idx < len(self._q_points):
            logger.info("Test #%d: %s -> %s", self._test_id, current_q,
                        self._q_points[next_idx].q_point)
        else:
            logger.info("Test #%d: %s was last Q-point", self._test_id, current_q)

    def _state_complete(self):
        """Stop pump, close valves, finalize test."""
        self._set_state(TestState.COMPLETE)

        from testing.services import complete_test, generate_certificate_number
        from controller.tower_light import LightPattern

        self._pid.disable()
        self._vfd.stop()
        self._valves.close_all()

        complete_test(self._test)
        self._test.refresh_from_db()

        if self._test.overall_pass:
            generate_certificate_number(self._test)
            self._tower.set_pattern(LightPattern.TEST_PASS)
            logger.info("Test #%d COMPLETE: PASS, cert=%s",
                        self._test_id, self._test.certificate_number)
        else:
            self._tower.set_pattern(LightPattern.TEST_FAIL)
            logger.info("Test #%d COMPLETE: FAIL", self._test_id)

        self._record_sensor_reading('', trigger='event', event_label='test_complete')

    def _state_emergency_stop(self, reason: str = ''):
        """Abort everything safely."""
        self._set_state(TestState.EMERGENCY_STOP)

        from testing.services import abort_test
        from controller.tower_light import LightPattern

        logger.critical("Test #%d EMERGENCY_STOP: %s", self._test_id, reason)

        try:
            if self._pid:
                self._pid.disable()
        except Exception:
            pass

        try:
            if self._vfd:
                self._vfd.emergency_stop()
        except Exception:
            pass

        try:
            if self._valves:
                self._valves.close_all()
        except Exception:
            pass

        try:
            if self._tower:
                self._tower.set_pattern(LightPattern.ESTOP)
        except Exception:
            pass

        try:
            if self._test:
                abort_test(self._test, reason=reason)
        except Exception:
            logger.exception("Failed to abort test in DB")

    # ==================================================================
    #  DUT reading helpers
    # ==================================================================

    def _read_dut(self, reading_type: str, q: QPointParams):
        """Read DUT totalizer — RS485 auto or manual wait."""
        from controller.dut_interface import DUTMode

        if self._dut.mode == DUTMode.RS485:
            if reading_type == 'before':
                result = self._retry(lambda: self._dut.read_before(), "DUT before")
            else:
                result = self._retry(lambda: self._dut.read_after(), "DUT after")
            if result is None:
                raise AbortError(f"DUT {reading_type} reading failed for {q.q_point}")
        else:
            self._request_manual_dut(q.q_point, reading_type)

    def _request_manual_dut(self, q_point: str, reading_type: str):
        """Block until operator enters a manual DUT reading."""
        req = ManualDUTRequest(
            test_id=self._test_id,
            q_point=q_point,
            reading_type=reading_type,
        )
        self._manual_dut_event.clear()

        for cb in self._manual_dut_callbacks:
            try:
                cb(req)
            except Exception:
                logger.exception("Manual DUT callback error")

        logger.info("Test #%d waiting for manual DUT %s for %s",
                    self._test_id, reading_type, q_point)

        deadline = time.time() + MANUAL_DUT_TIMEOUT_S
        while not self._manual_dut_event.is_set():
            self._check_abort()
            remaining = deadline - time.time()
            if remaining <= 0:
                raise AbortError(f"Manual DUT {reading_type} timeout for {q_point}")
            self._manual_dut_event.wait(timeout=min(ABORT_CHECK_INTERVAL_S, remaining))

        self._check_abort()

    # ==================================================================
    #  Helpers
    # ==================================================================

    def _set_state(self, state: TestState):
        with self._lock:
            self._state = state

    def _check_abort(self):
        with self._lock:
            if self._abort_requested:
                raise AbortError(self._abort_reason)

    def _update_test_state(self, q_point: str, state: str):
        from testing.services import update_test_state
        update_test_state(self._test, q_point, state)

    def _update_test_state_safe(self, q_point: str, state: str):
        self._db_safe(self._update_test_state, q_point, state)

    def _db_safe(self, func, *args, **kwargs):
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()

    def _record_sensor_reading(self, q_point: str, trigger: str = 'periodic',
                                event_label: str = ''):
        try:
            close_old_connections()
            from testing.services import record_sensor_reading
            snap = self._sensor_mgr.latest
            active_lane = self._valves.active_lane or ''
            diverter = self._valves.diverter_position
            record_sensor_reading(
                test=self._test, snapshot=snap, q_point=q_point,
                trigger=trigger, event_label=event_label,
                diverter=diverter, active_lane=active_lane,
            )
            self._last_sensor_record = time.time()
        except Exception:
            logger.debug("Failed to record sensor reading", exc_info=True)

    def _record_sensor_reading_safe(self, q_point: str, **kwargs):
        self._db_safe(self._record_sensor_reading, q_point, **kwargs)

    def _maybe_record_sensor(self, q_point: str):
        if time.time() - self._last_sensor_record >= SENSOR_RECORD_INTERVAL_S:
            self._db_safe(self._record_sensor_reading, q_point)

    def _retry(self, func, label: str, max_retries: int = MAX_RETRIES):
        for attempt in range(1, max_retries + 1):
            self._check_abort()
            try:
                result = func()
                if result is not None and result is not False:
                    return result
                if attempt < max_retries:
                    logger.warning("%s attempt %d/%d failed, retrying...",
                                   label, attempt, max_retries)
                    time.sleep(RETRY_DELAY_S)
            except AbortError:
                raise
            except Exception as e:
                if attempt < max_retries:
                    logger.warning("%s attempt %d/%d error: %s, retrying...",
                                   label, attempt, max_retries, e)
                    time.sleep(RETRY_DELAY_S)
                else:
                    logger.error("%s failed after %d attempts: %s", label, max_retries, e)
        return None

    def _on_safety_alarm(self, alarm):
        from controller.safety_monitor import AlarmSeverity
        if alarm.severity == AlarmSeverity.EMERGENCY:
            self.abort(f"Safety alarm: {alarm.message}")

    def _cleanup(self):
        if self._safety:
            try:
                self._safety._callbacks.remove(self._on_safety_alarm)
            except (ValueError, AttributeError):
                pass
        logger.info("Test #%d state machine finished (state=%s)",
                    self._test_id, self._state.value)


# ---------------------------------------------------------------------------
#  Module-level active test tracking
# ---------------------------------------------------------------------------

_active_machine: TestStateMachine | None = None
_active_lock = threading.Lock()


def get_active_machine() -> TestStateMachine | None:
    """Get the currently running test state machine, if any."""
    with _active_lock:
        if _active_machine and _active_machine.is_running:
            return _active_machine
        return None


def start_test_machine(test_id: int) -> TestStateMachine:
    """Create and start a test state machine. Only one can run at a time."""
    global _active_machine
    with _active_lock:
        if _active_machine and _active_machine.is_running:
            raise RuntimeError(
                f"Test #{_active_machine.test_id} is already running"
            )
        _active_machine = TestStateMachine(test_id)
        _active_machine.start()
        return _active_machine


def abort_active_test(reason: str = '') -> bool:
    """Abort the currently active test. Returns True if there was one."""
    with _active_lock:
        if _active_machine and _active_machine.is_running:
            _active_machine.abort(reason)
            return True
        return False
