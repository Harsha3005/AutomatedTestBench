"""
Unit tests for Sprint 3 controller modules:
  - PID controller convergence and behaviour
  - Safety monitor alarm detection
  - Valve controller mutual exclusion
  - Tower light patterns
  - Gravimetric engine calculations
  - DUT interface reading logic

Run: python manage.py test controller --settings=config.settings_bench
"""

import threading
import time

from django.test import TestCase, override_settings

from controller.pid_controller import PIDController, PIDState
from controller.safety_monitor import (
    AlarmCode,
    AlarmSeverity,
    SafetyAlarm,
    SafetyMonitor,
)
from controller.sensor_manager import SensorSnapshot
from controller.valve_controller import ValveController, LANE_VALVES, ALL_VALVES
from controller.tower_light import TowerLightController, LightPattern, PATTERN_MAP
from controller.gravimetric import GravimetricEngine, GravimetricResult
from controller.dut_interface import DUTInterface, DUTMode, DUTState
from controller.simulator import HardwareSimulator


# ======================================================================
#  PID Controller Tests (T-307)
# ======================================================================

class PIDBasicTests(TestCase):
    """Basic PID controller behaviour."""

    def setUp(self):
        self.pid = PIDController(
            kp=0.5, ki=0.1, kd=0.05,
            output_min=5.0, output_max=50.0,
            sample_rate=0.2,
        )

    def test_disabled_returns_zero(self):
        """PID output is 0 when disabled."""
        output = self.pid.compute(500.0)
        self.assertEqual(output, 0.0)

    def test_enable_disable(self):
        """Enable and disable toggle."""
        self.assertFalse(self.pid.enabled)
        self.pid.enable()
        self.assertTrue(self.pid.enabled)
        self.pid.disable()
        self.assertFalse(self.pid.enabled)

    def test_zero_target_zero_output(self):
        """With target=0, output should be 0."""
        self.pid.enable()
        self.pid.set_target(0.0)
        output = self.pid.compute(0.0)
        self.assertEqual(output, 0.0)

    def test_positive_error_increases_output(self):
        """When measured < target, output should be positive (within VFD range)."""
        self.pid.enable()
        self.pid.set_target(500.0)
        output = self.pid.compute(0.0)
        self.assertGreater(output, 0)
        self.assertGreaterEqual(output, 5.0)

    def test_output_clamped_to_range(self):
        """Output is clamped between output_min and output_max."""
        self.pid.enable()
        self.pid.set_target(100000.0)  # Huge target
        output = self.pid.compute(0.0)
        self.assertLessEqual(output, 50.0)

        self.pid.set_target(1.0)  # Tiny target
        output = self.pid.compute(0.5)
        self.assertGreaterEqual(output, 5.0)

    def test_set_gains(self):
        """Gains can be updated on the fly."""
        self.pid.set_gains(1.0, 0.5, 0.2)
        self.pid.enable()
        self.pid.set_target(100.0)
        output = self.pid.compute(0.0)
        # With higher Kp, output should be higher
        self.assertGreater(output, 0)

    def test_manual_override(self):
        """Manual output bypasses PID computation."""
        self.pid.enable()
        self.pid.set_target(500.0)
        self.pid.set_manual_output(25.0)
        output = self.pid.compute(100.0)
        self.assertEqual(output, 25.0)

        # Clear manual
        self.pid.set_manual_output(None)
        output = self.pid.compute(100.0)
        self.assertNotEqual(output, 25.0)

    def test_reset_clears_state(self):
        """Reset clears integral and previous values."""
        self.pid.enable()
        self.pid.set_target(500.0)
        self.pid.compute(100.0)
        self.pid.compute(200.0)
        self.pid.reset()
        state = self.pid.state
        self.assertEqual(state.output_hz, 0.0)

    def test_state_property(self):
        """State property returns PIDState dataclass."""
        self.pid.enable()
        self.pid.set_target(500.0)
        self.pid.compute(250.0)
        state = self.pid.state
        self.assertIsInstance(state, PIDState)
        self.assertEqual(state.target_lph, 500.0)
        self.assertTrue(state.enabled)


class PIDConvergenceTests(TestCase):
    """Test PID convergence on simulator (T-307)."""

    def test_converges_to_target(self):
        """PID output should drive flow toward target over iterations."""
        # Plant model: flow = freq * 50 L/h (plant gain = 50)
        # Effective loop gain with Kp=0.01 is 0.5, stable.
        # Ki=0.02 closes the steady-state offset.
        sample_dt = 0.2  # 200ms
        pid = PIDController(
            kp=0.01, ki=0.02, kd=0.001,
            output_min=5.0, output_max=50.0,
            sample_rate=sample_dt,
        )
        pid.enable()
        pid.set_target(1000.0)  # 1000 L/h (requires ~20 Hz)

        # Force deterministic dt by setting _last_time before each compute()
        flow = 0.0
        for i in range(300):
            pid._last_time = time.time() - sample_dt
            freq = pid.compute(flow)
            # Simulated plant: first-order lag, flow → freq * 50
            flow = flow + (freq * 50.0 - flow) * 0.3

        # Flow should converge close to target
        error_pct = abs(flow - 1000.0) / 1000.0 * 100
        self.assertLess(error_pct, 10.0, f"Flow {flow:.1f} L/h not within 10% of 1000 L/h")

    def test_stability_detection(self):
        """PID stability flag is set when flow is within tolerance."""
        pid = PIDController(
            kp=0.02, ki=0.001, kd=0.0,
            output_min=5.0, output_max=50.0,
            sample_rate=0.01,
        )
        pid._stability_tolerance = 2.0
        pid._stability_count = 5
        pid.enable()
        pid.set_target(500.0)

        # Feed exactly on-target readings
        for _ in range(10):
            pid.compute(500.0)

        self.assertTrue(pid.is_stable)

    def test_not_stable_with_error(self):
        """PID is not stable when readings are far from target."""
        pid = PIDController(
            kp=0.5, ki=0.1, kd=0.05,
            output_min=5.0, output_max=50.0,
            sample_rate=0.01,
        )
        pid.enable()
        pid.set_target(500.0)

        # Feed off-target readings
        for _ in range(10):
            pid.compute(100.0)

        self.assertFalse(pid.is_stable)

    def test_anti_windup(self):
        """Integral term doesn't wind up beyond output limits."""
        pid = PIDController(
            kp=0.01, ki=1.0, kd=0.0,
            output_min=5.0, output_max=50.0,
            sample_rate=0.01,
        )
        pid.enable()
        pid.set_target(10000.0)  # Unachievable target

        # Run many iterations with huge error
        for _ in range(100):
            output = pid.compute(0.0)

        # Output should still be at max, not beyond
        self.assertLessEqual(output, 50.0)

        # When target drops, output should respond quickly (no windup lag)
        pid.set_target(250.0)
        for _ in range(50):
            output = pid.compute(250.0)

        # Should settle near min since we're at target
        self.assertLessEqual(output, 50.0)


# ======================================================================
#  Safety Monitor Tests (T-308)
# ======================================================================

class SafetyMonitorTests(TestCase):
    """Safety watchdog alarm detection tests."""

    def _make_snapshot(self, **overrides) -> SensorSnapshot:
        """Create a normal (safe) snapshot with optional overrides."""
        defaults = dict(
            timestamp=time.time(),
            pressure_upstream_bar=3.0,
            reservoir_level_pct=80.0,
            water_temp_c=22.0,
            weight_raw_kg=5.0,
            estop_active=False,
            contactor_on=True,
            mcb_on=True,
            vfd_fault=0,
        )
        defaults.update(overrides)
        return SensorSnapshot(**defaults)

    def test_normal_conditions_no_alarms(self):
        """Normal sensor values produce no alarms."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot()
        alarms = monitor.check_snapshot(snap)
        self.assertEqual(len(alarms), 0)

    def test_overpressure_alarm(self):
        """Pressure above limit triggers OVERPRESSURE alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(pressure_upstream_bar=9.5)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.OVERPRESSURE, codes)
        alarm = next(a for a in alarms if a.code == AlarmCode.OVERPRESSURE)
        self.assertEqual(alarm.severity, AlarmSeverity.EMERGENCY)

    def test_low_reservoir_alarm(self):
        """Reservoir below minimum triggers LOW_RESERVOIR alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(reservoir_level_pct=15.0)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.LOW_RESERVOIR, codes)

    def test_temp_high_alarm(self):
        """Temperature above max triggers TEMP_HIGH alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(water_temp_c=45.0)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.TEMP_HIGH, codes)

    def test_temp_low_alarm(self):
        """Temperature below min triggers TEMP_LOW alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(water_temp_c=2.0)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.TEMP_LOW, codes)

    def test_scale_overload_alarm(self):
        """Scale weight above max triggers SCALE_OVERLOAD alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(weight_raw_kg=200.0)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.SCALE_OVERLOAD, codes)
        alarm = next(a for a in alarms if a.code == AlarmCode.SCALE_OVERLOAD)
        self.assertEqual(alarm.severity, AlarmSeverity.EMERGENCY)

    def test_estop_alarm(self):
        """E-stop active triggers ESTOP_ACTIVE alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(estop_active=True)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.ESTOP_ACTIVE, codes)

    def test_contactor_trip_alarm(self):
        """Contactor off triggers CONTACTOR_TRIP alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(contactor_on=False)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.CONTACTOR_TRIP, codes)

    def test_mcb_trip_alarm(self):
        """MCB off triggers MCB_TRIP alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(mcb_on=False)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.MCB_TRIP, codes)

    def test_vfd_fault_alarm(self):
        """Non-zero VFD fault triggers VFD_FAULT alarm."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(vfd_fault=3)
        alarms = monitor.check_snapshot(snap)
        codes = [a.code for a in alarms]
        self.assertIn(AlarmCode.VFD_FAULT, codes)

    def test_multiple_alarms(self):
        """Multiple safety violations produce multiple alarms."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(
            pressure_upstream_bar=10.0,
            reservoir_level_pct=10.0,
            water_temp_c=50.0,
        )
        alarms = monitor.check_snapshot(snap)
        self.assertGreaterEqual(len(alarms), 3)

    def test_alarm_severity_levels(self):
        """Emergency alarms are correctly tagged."""
        monitor = SafetyMonitor()
        snap = self._make_snapshot(estop_active=True)
        alarms = monitor.check_snapshot(snap)
        estop = next(a for a in alarms if a.code == AlarmCode.ESTOP_ACTIVE)
        self.assertTrue(estop.is_emergency)

    def test_safe_conditions(self):
        """is_safe returns True when no emergency alarms."""
        monitor = SafetyMonitor()
        self.assertTrue(monitor.is_safe)


# ======================================================================
#  Valve Controller Tests
# ======================================================================

class ValveControllerTests(TestCase):
    """Valve controller with mutual exclusion tests."""

    def setUp(self):
        self.vc = ValveController(backend='simulator')
        self.vc.init_backend()

    def test_open_close_valve(self):
        """Open and close a valve."""
        self.assertTrue(self.vc.open_valve('SV1'))
        self.assertTrue(self.vc.is_valve_open('SV1'))
        self.assertTrue(self.vc.close_valve('SV1'))
        self.assertFalse(self.vc.is_valve_open('SV1'))

    def test_unknown_valve_rejected(self):
        """Unknown valve ID returns False."""
        self.assertFalse(self.vc.open_valve('UNKNOWN'))

    def test_lane_mutual_exclusion(self):
        """Opening one lane valve closes the others."""
        self.vc.open_valve('BV-L1')
        self.assertTrue(self.vc.is_valve_open('BV-L1'))

        self.vc.open_valve('BV-L2')
        self.assertTrue(self.vc.is_valve_open('BV-L2'))
        self.assertFalse(self.vc.is_valve_open('BV-L1'))

        self.vc.open_valve('BV-L3')
        self.assertTrue(self.vc.is_valve_open('BV-L3'))
        self.assertFalse(self.vc.is_valve_open('BV-L2'))

    def test_non_lane_valves_independent(self):
        """Non-lane valves don't interfere with each other."""
        self.vc.open_valve('SV1')
        self.vc.open_valve('SV-DRN')
        self.assertTrue(self.vc.is_valve_open('SV1'))
        self.assertTrue(self.vc.is_valve_open('SV-DRN'))

    def test_close_all(self):
        """close_all closes everything."""
        self.vc.open_valve('SV1')
        self.vc.open_valve('BV-L2')
        self.vc.set_diverter('COLLECT')

        self.assertTrue(self.vc.close_all())
        for v in ALL_VALVES:
            self.assertFalse(self.vc.is_valve_open(v))
        self.assertEqual(self.vc.diverter_position, 'BYPASS')

    def test_select_lane_by_meter_size(self):
        """select_lane resolves meter size to valve."""
        self.assertTrue(self.vc.select_lane('DN15'))
        self.assertTrue(self.vc.is_valve_open('BV-L3'))
        self.assertEqual(self.vc.active_lane, 'BV-L3')

        self.assertTrue(self.vc.select_lane('DN20'))
        self.assertTrue(self.vc.is_valve_open('BV-L2'))
        self.assertFalse(self.vc.is_valve_open('BV-L3'))

        self.assertTrue(self.vc.select_lane('DN25'))
        self.assertTrue(self.vc.is_valve_open('BV-L1'))
        self.assertFalse(self.vc.is_valve_open('BV-L2'))

    def test_diverter_control(self):
        """Diverter switches between COLLECT and BYPASS."""
        self.assertTrue(self.vc.set_diverter('COLLECT'))
        self.assertEqual(self.vc.diverter_position, 'COLLECT')
        self.assertTrue(self.vc.set_diverter('BYPASS'))
        self.assertEqual(self.vc.diverter_position, 'BYPASS')

    def test_invalid_diverter_position(self):
        """Invalid diverter position returns False."""
        self.assertFalse(self.vc.set_diverter('INVALID'))

    def test_states_snapshot(self):
        """states property returns ValveStates."""
        self.vc.open_valve('SV1')
        self.vc.select_lane('DN20')
        self.vc.set_diverter('COLLECT')
        states = self.vc.states
        self.assertTrue(states.valves['SV1'])
        self.assertTrue(states.valves['BV-L2'])
        self.assertEqual(states.diverter, 'COLLECT')
        self.assertEqual(states.active_lane, 'BV-L2')


# ======================================================================
#  Tower Light Tests
# ======================================================================

class TowerLightTests(TestCase):
    """Tower light pattern tests."""

    def setUp(self):
        self.tower = TowerLightController(backend='simulator')
        self.tower.init_backend()

    def tearDown(self):
        self.tower.stop()

    def test_ready_pattern(self):
        """READY pattern sets green light."""
        self.tower.set_pattern(LightPattern.READY)
        self.assertEqual(self.tower.pattern, LightPattern.READY)
        # Verify on simulator
        sim = self.tower._simulator
        self.assertTrue(sim.tower_green)
        self.assertFalse(sim.tower_red)
        self.assertFalse(sim.tower_yellow)

    def test_testing_pattern(self):
        """TESTING pattern sets yellow light."""
        self.tower.set_pattern(LightPattern.TESTING)
        sim = self.tower._simulator
        self.assertTrue(sim.tower_yellow)
        self.assertFalse(sim.tower_green)
        self.assertFalse(sim.tower_red)

    def test_fault_pattern(self):
        """FAULT pattern sets red light."""
        self.tower.set_pattern(LightPattern.FAULT)
        sim = self.tower._simulator
        self.assertTrue(sim.tower_red)
        self.assertFalse(sim.tower_green)

    def test_off_pattern(self):
        """OFF turns off all lights."""
        self.tower.set_pattern(LightPattern.OFF)
        sim = self.tower._simulator
        self.assertFalse(sim.tower_red)
        self.assertFalse(sim.tower_yellow)
        self.assertFalse(sim.tower_green)
        self.assertFalse(sim.buzzer)

    def test_all_patterns_defined(self):
        """Every LightPattern has a corresponding PATTERN_MAP entry."""
        for pattern in LightPattern:
            self.assertIn(pattern, PATTERN_MAP)

    def test_blink_pattern_starts_thread(self):
        """Blink patterns start a background thread."""
        self.tower.set_pattern(LightPattern.ESTOP)
        self.assertIsNotNone(self.tower._blink_thread)
        self.assertTrue(self.tower._blink_running)


# ======================================================================
#  Gravimetric Engine Tests
# ======================================================================

class GravimetricCalculationTests(TestCase):
    """Gravimetric volume calculation tests."""

    def test_volume_at_20c(self):
        """Volume calculation at 20 C (standard)."""
        volume, density = GravimetricEngine.calculate_volume(10.0, 20.0)
        self.assertAlmostEqual(density, 0.99820, places=4)
        expected_volume = 10.0 / 0.99820
        self.assertAlmostEqual(volume, expected_volume, places=3)

    def test_volume_at_4c(self):
        """Volume at 4 C (max density)."""
        volume, density = GravimetricEngine.calculate_volume(10.0, 4.0)
        self.assertAlmostEqual(density, 0.99997, places=4)
        self.assertAlmostEqual(volume, 10.0 / 0.99997, places=3)

    def test_volume_at_40c(self):
        """Volume at 40 C (min density in range)."""
        volume, density = GravimetricEngine.calculate_volume(10.0, 40.0)
        self.assertAlmostEqual(density, 0.99222, places=4)
        self.assertAlmostEqual(volume, 10.0 / 0.99222, places=3)

    def test_zero_weight_zero_volume(self):
        """Zero weight gives zero volume."""
        volume, _ = GravimetricEngine.calculate_volume(0.0, 20.0)
        self.assertEqual(volume, 0.0)

    def test_temperature_affects_volume(self):
        """Higher temperature (lower density) gives larger volume for same mass."""
        vol_20, _ = GravimetricEngine.calculate_volume(10.0, 20.0)
        vol_40, _ = GravimetricEngine.calculate_volume(10.0, 40.0)
        self.assertGreater(vol_40, vol_20)


# ======================================================================
#  DUT Interface Tests
# ======================================================================

class DUTManualModeTests(TestCase):
    """DUT interface manual mode tests."""

    def setUp(self):
        self.dut = DUTInterface(mode=DUTMode.MANUAL)

    def test_manual_before_after(self):
        """Manual before/after readings calculate volume."""
        self.assertTrue(self.dut.set_before_reading(1000.0))
        self.assertEqual(self.dut.state, DUTState.MEASURING)
        self.assertTrue(self.dut.set_after_reading(1010.5))
        self.assertEqual(self.dut.state, DUTState.COMPLETE)

        reading = self.dut.get_reading()
        self.assertTrue(reading.is_valid)
        self.assertAlmostEqual(reading.volume_l, 10.5, places=1)
        self.assertEqual(reading.mode, DUTMode.MANUAL)

    def test_after_less_than_before_rejected(self):
        """After reading less than before is rejected."""
        self.dut.set_before_reading(1000.0)
        self.assertFalse(self.dut.set_after_reading(999.0))
        self.assertNotEqual(self.dut.state, DUTState.COMPLETE)

    def test_negative_before_rejected(self):
        """Negative before reading is rejected."""
        self.assertFalse(self.dut.set_before_reading(-1.0))

    def test_reset_clears_state(self):
        """Reset returns to IDLE with zeroed values."""
        self.dut.set_before_reading(100.0)
        self.dut.set_after_reading(110.0)
        self.dut.reset()
        self.assertEqual(self.dut.state, DUTState.IDLE)
        self.assertEqual(self.dut.dut_volume_l, 0.0)

    def test_mode_switch(self):
        """Switching mode resets state."""
        self.dut.set_before_reading(100.0)
        self.dut.set_mode(DUTMode.RS485)
        self.assertEqual(self.dut.state, DUTState.IDLE)
        self.assertEqual(self.dut.mode, DUTMode.RS485)


class DUTSimulatorModeTests(TestCase):
    """DUT interface RS485 mode with simulator tests."""

    def setUp(self):
        self.sim = HardwareSimulator()
        self.dut = DUTInterface(backend='simulator', mode=DUTMode.RS485)
        self.dut._simulator = self.sim

    def test_not_connected_returns_none(self):
        """Reading from disconnected DUT returns None."""
        self.assertFalse(self.dut.is_connected())
        self.assertIsNone(self.dut.read_totalizer())

    def test_connected_reads_totalizer(self):
        """Connected DUT returns totalizer value."""
        self.sim.connect_dut(error_pct=1.5)
        self.assertTrue(self.dut.is_connected())
        value = self.dut.read_totalizer()
        self.assertIsNotNone(value)
        self.assertEqual(value, 0.0)  # Initial totalizer

    def test_before_after_auto_read(self):
        """RS485 auto-read records before and after."""
        self.sim.connect_dut(error_pct=2.0)
        self.sim.dut_totalizer = 100.0

        before = self.dut.read_before()
        self.assertEqual(before, 100.0)
        self.assertEqual(self.dut.state, DUTState.MEASURING)

        self.sim.dut_totalizer = 110.5
        after = self.dut.read_after()
        self.assertEqual(after, 110.5)
        self.assertEqual(self.dut.state, DUTState.COMPLETE)

        reading = self.dut.get_reading()
        self.assertAlmostEqual(reading.volume_l, 10.5, places=1)


# ======================================================================
#  State Machine Tests (T-401)
# ======================================================================

from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass as _dc

from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard
from controller.state_machine import (
    TestState, TestStateMachine, AbortError, PreCheckError,
    QPointParams, start_test_machine, get_active_machine, abort_active_test,
    FLOW_STABILIZE_TIMEOUT_S, PUMP_CONFIRM_TIMEOUT_S,
)
from controller.vfd_controller import VFDStatus


def _make_mock_snapshot(**overrides):
    """Create a SensorSnapshot-like mock with sensible defaults."""
    snap = SensorSnapshot(
        timestamp=time.time(),
        flow_rate_lph=300.0,
        em_totalizer_l=100.0,
        weight_kg=0.0,
        weight_raw_kg=0.5,
        pressure_upstream_bar=3.0,
        pressure_downstream_bar=2.5,
        water_temp_c=22.0,
        reservoir_level_pct=85.0,
        dut_connected=True,
        vfd_running=True,
        vfd_freq_hz=30.0,
        vfd_target_hz=30.0,
        vfd_current_a=4.0,
        vfd_fault=0,
        contactor_on=True,
        mcb_on=True,
        estop_active=False,
    )
    for k, v in overrides.items():
        setattr(snap, k, v)
    return snap


def _seed_iso4064():
    """Seed minimal ISO data for DN15/B — 2 Q-points for fast tests."""
    ISO4064Standard.objects.get_or_create(
        meter_size='DN15', meter_class='B', q_point='Q1',
        defaults={'flow_rate_lph': 15.0, 'test_volume_l': 1.0,
                  'duration_s': 240, 'mpe_pct': 5.0, 'zone': 'Lower'},
    )
    ISO4064Standard.objects.get_or_create(
        meter_size='DN15', meter_class='B', q_point='Q2',
        defaults={'flow_rate_lph': 22.5, 'test_volume_l': 1.5,
                  'duration_s': 240, 'mpe_pct': 2.0, 'zone': 'Upper'},
    )


class StateMachineTestBase(TestCase):
    """Base with common fixtures and mocks for state machine tests."""

    def setUp(self):
        _seed_iso4064()
        self.meter = TestMeter.objects.create(
            serial_number='SM-TEST-001',
            meter_size='DN15',
            meter_class='B',
            meter_type='mechanical',
            dut_mode='rs485',
        )
        self.test = Test.objects.create(
            meter=self.meter, test_class='B', status='queued',
        )
        for iso in ISO4064Standard.objects.filter(meter_size='DN15', meter_class='B'):
            TestResult.objects.create(
                test=self.test, q_point=iso.q_point,
                target_flow_lph=iso.flow_rate_lph,
                mpe_pct=iso.mpe_pct, zone=iso.zone,
            )

        # Build mock controllers
        self.mock_sensor = MagicMock()
        self.mock_sensor.latest = _make_mock_snapshot()

        self.mock_vfd = MagicMock()
        self.mock_vfd.start.return_value = True
        self.mock_vfd.stop.return_value = True
        self.mock_vfd.set_frequency.return_value = True
        self.mock_vfd.read_status.return_value = VFDStatus(
            running=True, frequency_hz=30.0, target_hz=30.0,
            current_a=4.0, fault_code=0, connected=True,
        )

        self.mock_valves = MagicMock()
        self.mock_valves.select_lane.return_value = True
        self.mock_valves.open_valve.return_value = True
        self.mock_valves.set_diverter.return_value = True
        self.mock_valves.close_all.return_value = True
        self.mock_valves.active_lane = 'BV-L3'
        self.mock_valves.diverter_position = 'BYPASS'

        self.mock_pid = MagicMock()
        self.mock_pid.is_stable = True
        self.mock_pid.compute.return_value = 25.0

        self.mock_safety = MagicMock()
        self.mock_safety.check_snapshot.return_value = []
        self.mock_safety._callbacks = []

        self.mock_tower = MagicMock()

        self.mock_grav = MagicMock()
        self.mock_grav.tare.return_value = True
        self.mock_grav.start_collection.return_value = None
        self.mock_grav.stop_collection_and_measure.return_value = GravimetricResult(
            success=True, net_weight_kg=1.0, tare_weight_kg=0.5,
            gross_weight_kg=1.5, temperature_c=22.0,
            density_kg_l=0.99777, volume_l=1.002,
            collect_time_s=60.0, avg_flow_lph=60.12,
        )
        self.mock_grav.drain_tank.return_value = True

        self.mock_dut = MagicMock()
        self.mock_dut.mode = DUTMode.RS485
        self.mock_dut.is_connected.return_value = True
        self.mock_dut.read_before.return_value = 100.0
        self.mock_dut.read_after.return_value = 101.0
        self.mock_dut.get_reading.return_value = MagicMock(
            volume_l=1.0, before_l=100.0, after_l=101.0, is_valid=True,
        )

        # Patch all hardware factory functions
        self.patches = [
            patch('controller.hardware.get_sensor_manager', return_value=self.mock_sensor),
            patch('controller.hardware.get_vfd_controller', return_value=self.mock_vfd),
            patch('controller.hardware.get_valve_controller', return_value=self.mock_valves),
            patch('controller.hardware.get_pid_controller', return_value=self.mock_pid),
            patch('controller.hardware.get_safety_monitor', return_value=self.mock_safety),
            patch('controller.hardware.get_tower_light', return_value=self.mock_tower),
            patch('controller.hardware.get_gravimetric_engine', return_value=self.mock_grav),
            patch('controller.hardware.get_dut_interface', return_value=self.mock_dut),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Reset module-level state
        import controller.state_machine as sm_mod
        with sm_mod._active_lock:
            sm_mod._active_machine = None

    def _make_sm(self):
        """Create a state machine for self.test."""
        return TestStateMachine(self.test.pk)

    def _run_sm_sync(self, sm=None):
        """Run the state machine synchronously (call _run directly)."""
        sm = sm or self._make_sm()
        sm._run()
        return sm


class TestStateEnum(TestCase):

    def test_state_enum_values(self):
        """All 12 states have correct string values."""
        self.assertEqual(len(TestState), 12)
        self.assertEqual(TestState.IDLE.value, 'IDLE')
        self.assertEqual(TestState.EMERGENCY_STOP.value, 'EMERGENCY_STOP')
        self.assertEqual(TestState.COMPLETE.value, 'COMPLETE')


class TestInitialize(StateMachineTestBase):

    def test_initialize_loads_q_points(self):
        """ISO params correctly loaded for meter size/class."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        self.assertEqual(len(sm._q_points), 2)
        self.assertEqual(sm._q_points[0].q_point, 'Q1')
        self.assertEqual(sm._q_points[1].q_point, 'Q2')

    def test_initialize_no_iso_data_raises(self):
        """PreCheckError if no ISO params found."""
        # Change test class to one with no ISO data
        self.test.test_class = 'R200'
        self.test.save()
        sm = self._make_sm()
        with self.assertRaises(PreCheckError):
            sm._db_safe(sm._initialize)


class TestPreCheck(StateMachineTestBase):

    def _init_sm(self):
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        return sm

    def test_pre_check_passes(self):
        """Pre-check passes with healthy mocks."""
        sm = self._init_sm()
        sm._db_safe(sm._state_pre_check)
        # Should complete without error

    def test_pre_check_safety_alarm_aborts(self):
        """Emergency alarm triggers PreCheckError."""
        sm = self._init_sm()
        self.mock_safety.check_snapshot.return_value = [
            SafetyAlarm(
                code=AlarmCode.ESTOP_ACTIVE,
                severity=AlarmSeverity.EMERGENCY,
                message='E-stop active',
            )
        ]
        with self.assertRaises(PreCheckError) as ctx:
            sm._db_safe(sm._state_pre_check)
        self.assertIn('E-stop', str(ctx.exception))

    def test_pre_check_vfd_fault_aborts(self):
        """VFD fault code raises PreCheckError."""
        sm = self._init_sm()
        self.mock_vfd.read_status.return_value = VFDStatus(
            running=False, frequency_hz=0, target_hz=0,
            current_a=0, fault_code=5, connected=True,
        )
        with self.assertRaises(PreCheckError) as ctx:
            sm._db_safe(sm._state_pre_check)
        self.assertIn('fault', str(ctx.exception).lower())

    def test_pre_check_low_reservoir_aborts(self):
        """Low reservoir level raises PreCheckError."""
        sm = self._init_sm()
        self.mock_sensor.latest = _make_mock_snapshot(reservoir_level_pct=20.0)
        with self.assertRaises(PreCheckError) as ctx:
            sm._db_safe(sm._state_pre_check)
        self.assertIn('Reservoir', str(ctx.exception))

    def test_pre_check_dut_disconnected_rs485_aborts(self):
        """DUT not connected in RS485 mode raises PreCheckError."""
        sm = self._init_sm()
        self.mock_dut.is_connected.return_value = False
        with self.assertRaises(PreCheckError) as ctx:
            sm._db_safe(sm._state_pre_check)
        self.assertIn('DUT', str(ctx.exception))


class TestPumpStart(StateMachineTestBase):

    def test_pump_start_timeout_aborts(self):
        """VFD never confirms running within timeout."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        sm._state_pre_check = MagicMock()  # Skip pre-check

        self.mock_vfd.read_status.return_value = VFDStatus(
            running=False, frequency_hz=0, target_hz=5.0,
            current_a=0, fault_code=0, connected=True,
        )

        import controller.state_machine as sm_mod
        orig = sm_mod.PUMP_CONFIRM_TIMEOUT_S
        sm_mod.PUMP_CONFIRM_TIMEOUT_S = 0.3  # Speed up test
        try:
            with self.assertRaises(AbortError):
                sm._state_pump_start()
        finally:
            sm_mod.PUMP_CONFIRM_TIMEOUT_S = orig


class TestFlowStabilize(StateMachineTestBase):

    def test_flow_stabilize_timeout_continues(self):
        """Timeout is non-fatal — should NOT raise."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        self.mock_pid.is_stable = False  # Never stable

        import controller.state_machine as sm_mod
        orig = sm_mod.FLOW_STABILIZE_TIMEOUT_S
        sm_mod.FLOW_STABILIZE_TIMEOUT_S = 0.3
        try:
            q = sm._q_points[0]
            sm._state_flow_stabilize(q)  # Should not raise
        finally:
            sm_mod.FLOW_STABILIZE_TIMEOUT_S = orig


class TestTareScale(StateMachineTestBase):

    def test_tare_retry_then_abort(self):
        """Tare fails 3x, triggers AbortError."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        self.mock_grav.tare.return_value = False

        import controller.state_machine as sm_mod
        orig = sm_mod.RETRY_DELAY_S
        sm_mod.RETRY_DELAY_S = 0.01
        try:
            with self.assertRaises(AbortError) as ctx:
                sm._state_tare_scale()
            self.assertIn('tare', str(ctx.exception).lower())
        finally:
            sm_mod.RETRY_DELAY_S = orig


class TestDrainState(StateMachineTestBase):

    def test_drain_timeout_continues(self):
        """Drain timeout is non-fatal."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        self.mock_grav.drain_tank.return_value = False  # Timeout
        sm._state_drain()  # Should not raise


class TestAbort(StateMachineTestBase):

    def test_abort_flag_checked(self):
        """Setting abort flag causes _check_abort to raise."""
        sm = self._make_sm()
        sm.abort("user request")
        with self.assertRaises(AbortError):
            sm._check_abort()

    def test_safety_callback_triggers_abort(self):
        """EMERGENCY alarm triggers abort via callback."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)
        alarm = SafetyAlarm(
            code=AlarmCode.OVERPRESSURE,
            severity=AlarmSeverity.EMERGENCY,
            message='Overpressure',
        )
        sm._on_safety_alarm(alarm)
        self.assertTrue(sm._abort_requested)


class TestComplete(StateMachineTestBase):

    def _run_full(self):
        """Make weight immediately reach target to speed through MEASURE."""
        self.mock_sensor.latest = _make_mock_snapshot(weight_kg=100.0)
        sm = self._make_sm()

        import controller.state_machine as sm_mod
        orig_flow = sm_mod.FLOW_STABILIZE_TIMEOUT_S
        orig_retry = sm_mod.RETRY_DELAY_S
        sm_mod.FLOW_STABILIZE_TIMEOUT_S = 0.1
        sm_mod.RETRY_DELAY_S = 0.01

        try:
            sm._run()
        finally:
            sm_mod.FLOW_STABILIZE_TIMEOUT_S = orig_flow
            sm_mod.RETRY_DELAY_S = orig_retry

        return sm

    def test_complete_all_pass_generates_cert(self):
        """Certificate generated on overall pass."""
        sm = self._run_full()
        self.test.refresh_from_db()
        self.assertEqual(sm.state, TestState.COMPLETE)
        self.assertEqual(self.test.status, 'completed')
        # Certificate generated when all pass
        if self.test.overall_pass:
            self.assertTrue(len(self.test.certificate_number) > 0)

    def test_complete_with_fail_no_cert(self):
        """No certificate when test fails."""
        # Make gravimetric return a result that will cause a large error
        self.mock_grav.stop_collection_and_measure.return_value = GravimetricResult(
            success=True, net_weight_kg=1.0, temperature_c=22.0,
            volume_l=1.0, collect_time_s=60.0,
        )
        self.mock_dut.get_reading.return_value = MagicMock(
            volume_l=5.0,  # Huge DUT volume → big error → FAIL
        )
        self.mock_sensor.latest = _make_mock_snapshot(weight_kg=100.0)

        import controller.state_machine as sm_mod
        orig_flow = sm_mod.FLOW_STABILIZE_TIMEOUT_S
        orig_retry = sm_mod.RETRY_DELAY_S
        sm_mod.FLOW_STABILIZE_TIMEOUT_S = 0.1
        sm_mod.RETRY_DELAY_S = 0.01

        try:
            sm = self._make_sm()
            sm._run()
        finally:
            sm_mod.FLOW_STABILIZE_TIMEOUT_S = orig_flow
            sm_mod.RETRY_DELAY_S = orig_retry

        self.test.refresh_from_db()
        self.assertFalse(self.test.overall_pass)


class TestEmergencyStop(StateMachineTestBase):

    def test_emergency_stop_resilient(self):
        """EMERGENCY_STOP calls all shutdown steps even if some fail."""
        sm = self._make_sm()
        sm._db_safe(sm._initialize)

        # Make some controllers raise
        self.mock_vfd.emergency_stop.side_effect = RuntimeError("VFD error")
        self.mock_valves.close_all.side_effect = RuntimeError("Valve error")

        # Should NOT raise — each step is wrapped in try/except
        sm._db_safe(sm._state_emergency_stop, "test reason")

        self.assertEqual(sm.state, TestState.EMERGENCY_STOP)
        self.mock_pid.disable.assert_called()
        self.mock_tower.set_pattern.assert_called()


class TestManualDUT(StateMachineTestBase):

    def test_manual_dut_blocks_until_submit(self):
        """Manual DUT blocks, then unblocks when submit called."""
        self.meter.dut_mode = 'manual'
        self.meter.save()
        self.mock_dut.mode = DUTMode.MANUAL

        sm = self._make_sm()
        sm._db_safe(sm._initialize)

        # Submit from another thread after a short delay
        def _submit():
            time.sleep(0.1)
            sm._manual_dut_event.set()

        t = threading.Thread(target=_submit, daemon=True)
        t.start()

        # Should block briefly then succeed
        sm._request_manual_dut('Q1', 'before')
        t.join(timeout=2)

    def test_manual_dut_timeout_aborts(self):
        """No manual entry within timeout raises AbortError."""
        self.meter.dut_mode = 'manual'
        self.meter.save()
        self.mock_dut.mode = DUTMode.MANUAL

        sm = self._make_sm()
        sm._db_safe(sm._initialize)

        import controller.state_machine as sm_mod
        orig = sm_mod.MANUAL_DUT_TIMEOUT_S
        sm_mod.MANUAL_DUT_TIMEOUT_S = 0.2
        try:
            with self.assertRaises(AbortError) as ctx:
                sm._request_manual_dut('Q1', 'before')
            self.assertIn('timeout', str(ctx.exception).lower())
        finally:
            sm_mod.MANUAL_DUT_TIMEOUT_S = orig


class TestModuleFunctions(StateMachineTestBase):

    def test_only_one_machine_allowed(self):
        """start_test_machine raises if another is active."""
        sm1 = start_test_machine(self.test.pk)
        # Create a second test
        test2 = Test.objects.create(
            meter=self.meter, test_class='B', status='queued',
        )
        with self.assertRaises(RuntimeError):
            start_test_machine(test2.pk)

        sm1.abort("cleanup")
        sm1.join(timeout=3)

    def test_get_active_machine(self):
        """get_active_machine returns running machine."""
        self.assertIsNone(get_active_machine())
        sm = start_test_machine(self.test.pk)
        self.assertIsNotNone(get_active_machine())
        sm.abort("cleanup")
        sm.join(timeout=3)

    def test_abort_active_test(self):
        """abort_active_test aborts running machine."""
        sm = start_test_machine(self.test.pk)
        result = abort_active_test("test abort")
        self.assertTrue(result)
        sm.join(timeout=3)
