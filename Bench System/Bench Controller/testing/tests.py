"""Unit tests for testing app — services and ISO 4064 calculations."""
from dataclasses import dataclass
from django.test import TestCase
from django.utils import timezone

from meters.models import TestMeter
from testing.models import Test, TestResult
from testing.iso4064 import water_density, calculate_error, check_pass
from testing.services import (
    MeasurementValidationError,
    validate_measurement_inputs,
    record_result,
    start_test,
    complete_test,
    abort_test,
    process_q_point_result,
    get_test_summary,
    QPointSummary,
    TestSummary,
)


# ---------------------------------------------------------------------------
#  Stub dataclasses to mimic controller types without importing them
# ---------------------------------------------------------------------------

@dataclass
class FakeGravimetricResult:
    success: bool = True
    net_weight_kg: float = 10.0
    tare_weight_kg: float = 0.5
    gross_weight_kg: float = 10.5
    temperature_c: float = 20.0
    density_kg_l: float = 0.99820
    volume_l: float = 10.018
    collect_time_s: float = 120.0
    avg_flow_lph: float = 300.0
    error_message: str = ''


@dataclass
class FakeDUTReading:
    before_l: float = 0.0
    after_l: float = 10.0
    volume_l: float = 10.0


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

class TestBaseSetup(TestCase):
    """Base class with common test fixtures."""

    def setUp(self):
        self.meter = TestMeter.objects.create(
            serial_number='TEST-001',
            meter_size='DN15',
            meter_class='B',
            meter_type='mechanical',
        )
        self.test = Test.objects.create(
            meter=self.meter,
            test_class='B',
            status='running',
            started_at=timezone.now(),
        )

    def _create_q_point_results(self, q_points=None):
        """Create empty TestResult rows for the given Q-points."""
        if q_points is None:
            q_points = [
                ('Q1', 15.0, 5.0, 'Lower'),
                ('Q2', 22.5, 5.0, 'Lower'),
                ('Q3', 30.0, 2.0, 'Lower'),
                ('Q4', 60.0, 2.0, 'Upper'),
                ('Q5', 120.0, 2.0, 'Upper'),
                ('Q6', 300.0, 2.0, 'Upper'),
                ('Q7', 750.0, 2.0, 'Upper'),
                ('Q8', 1500.0, 2.0, 'Upper'),
            ]
        for qp, flow, mpe, zone in q_points:
            TestResult.objects.create(
                test=self.test,
                q_point=qp,
                target_flow_lph=flow,
                mpe_pct=mpe,
                zone=zone,
            )


# ===========================================================================
#  Validation tests
# ===========================================================================

class TestValidation(TestCase):

    def test_valid_inputs_pass(self):
        """Valid inputs should not raise."""
        validate_measurement_inputs(10.0, 20.0, 9.95, 120)

    def test_zero_weight_raises(self):
        with self.assertRaises(MeasurementValidationError) as ctx:
            validate_measurement_inputs(0.0, 20.0, 10.0, 120)
        self.assertIn('positive', str(ctx.exception))

    def test_negative_weight_raises(self):
        with self.assertRaises(MeasurementValidationError):
            validate_measurement_inputs(-5.0, 20.0, 10.0, 120)

    def test_temperature_below_range_raises(self):
        with self.assertRaises(MeasurementValidationError) as ctx:
            validate_measurement_inputs(10.0, 0.5, 10.0, 120)
        self.assertIn('1-50°C', str(ctx.exception))

    def test_temperature_above_range_raises(self):
        with self.assertRaises(MeasurementValidationError):
            validate_measurement_inputs(10.0, 55.0, 10.0, 120)

    def test_negative_dut_volume_raises(self):
        with self.assertRaises(MeasurementValidationError) as ctx:
            validate_measurement_inputs(10.0, 20.0, -1.0, 120)
        self.assertIn('negative', str(ctx.exception))

    def test_zero_duration_raises(self):
        with self.assertRaises(MeasurementValidationError) as ctx:
            validate_measurement_inputs(10.0, 20.0, 10.0, 0)
        self.assertIn('positive', str(ctx.exception))

    def test_negative_duration_raises(self):
        with self.assertRaises(MeasurementValidationError):
            validate_measurement_inputs(10.0, 20.0, 10.0, -10)

    def test_none_duration_is_ok(self):
        """duration_s=None should not raise."""
        validate_measurement_inputs(10.0, 20.0, 10.0, None)

    def test_zero_dut_volume_is_ok(self):
        """DUT volume of exactly zero is acceptable (meter not spinning)."""
        validate_measurement_inputs(10.0, 20.0, 0.0, 120)


# ===========================================================================
#  record_result tests
# ===========================================================================

class TestRecordResult(TestBaseSetup):

    def setUp(self):
        super().setUp()
        self._create_q_point_results()

    def test_basic_record_result(self):
        """record_result calculates error%, ref_volume, and passes correctly."""
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.0,
            duration_s=120,
        )
        self.assertIsNotNone(result.ref_volume_l)
        self.assertIsNotNone(result.error_pct)
        self.assertIsNotNone(result.passed)
        # At 20°C density=0.99820, ref_vol ≈ 10.018 L
        self.assertAlmostEqual(result.ref_volume_l, 10.018, places=2)
        # DUT=10.0, ref≈10.018 → error ≈ -0.18% (within 2% MPE)
        self.assertTrue(result.passed)

    def test_actual_flow_lph_calculated(self):
        """actual_flow_lph should be (ref_volume / duration_s) * 3600."""
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.0,
            duration_s=120,
        )
        # ref_vol ≈ 10.018, 10.018/120*3600 ≈ 300.54
        self.assertIsNotNone(result.actual_flow_lph)
        self.assertAlmostEqual(result.actual_flow_lph, 300.54, places=0)

    def test_actual_flow_lph_none_without_duration(self):
        """actual_flow_lph should be None when duration_s not provided."""
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.0,
        )
        self.assertIsNone(result.actual_flow_lph)

    def test_failed_result(self):
        """A large error should cause the result to fail."""
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=12.0,  # ~20% error, way beyond 2% MPE
            duration_s=120,
        )
        self.assertFalse(result.passed)

    def test_validation_called(self):
        """record_result should raise on invalid inputs."""
        with self.assertRaises(MeasurementValidationError):
            record_result(
                self.test, 'Q6',
                ref_weight_kg=0.0,
                temperature_c=20.0,
                dut_volume_l=10.0,
            )

    def test_pressures_stored(self):
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.0,
            pressure_up_bar=3.5,
            pressure_dn_bar=2.8,
        )
        self.assertEqual(result.pressure_up_bar, 3.5)
        self.assertEqual(result.pressure_dn_bar, 2.8)

    def test_weight_stored(self):
        result = record_result(
            self.test, 'Q6',
            ref_weight_kg=10.123456,
            temperature_c=20.0,
            dut_volume_l=10.0,
        )
        self.assertEqual(result.weight_kg, 10.1235)  # Rounded to 4dp


# ===========================================================================
#  process_q_point_result tests
# ===========================================================================

class TestProcessQPointResult(TestBaseSetup):

    def setUp(self):
        super().setUp()
        self._create_q_point_results()

    def test_success_path(self):
        """process_q_point_result should delegate to record_result."""
        grav = FakeGravimetricResult(
            success=True,
            net_weight_kg=10.0,
            temperature_c=20.0,
            collect_time_s=120.0,
        )
        dut = FakeDUTReading(volume_l=10.0)

        result = process_q_point_result(
            self.test, 'Q6', grav, dut,
            pressure_up_bar=3.0, pressure_dn_bar=2.5,
        )
        self.assertIsNotNone(result.error_pct)
        self.assertIsNotNone(result.passed)
        self.assertEqual(result.pressure_up_bar, 3.0)

    def test_failed_gravimetric_raises(self):
        """process_q_point_result should raise if gravimetric failed."""
        grav = FakeGravimetricResult(
            success=False,
            error_message='Scale timeout',
        )
        dut = FakeDUTReading(volume_l=10.0)

        with self.assertRaises(MeasurementValidationError) as ctx:
            process_q_point_result(self.test, 'Q6', grav, dut)
        self.assertIn('Scale timeout', str(ctx.exception))

    def test_zero_collect_time_gives_none_duration(self):
        """If collect_time_s is 0, duration_s should be None (not 0)."""
        grav = FakeGravimetricResult(
            success=True,
            net_weight_kg=10.0,
            temperature_c=20.0,
            collect_time_s=0.0,
        )
        dut = FakeDUTReading(volume_l=10.0)

        result = process_q_point_result(self.test, 'Q6', grav, dut)
        self.assertIsNone(result.actual_flow_lph)


# ===========================================================================
#  get_test_summary tests
# ===========================================================================

class TestGetTestSummary(TestBaseSetup):

    def setUp(self):
        super().setUp()
        self._create_q_point_results()

    def test_empty_results(self):
        """Summary of test with no completed Q-points."""
        summary = get_test_summary(self.test)
        self.assertEqual(summary.total_points, 8)
        self.assertEqual(summary.completed_points, 0)
        self.assertIsNone(summary.min_error_pct)
        self.assertIsNone(summary.lower_zone_pass)
        self.assertIsNone(summary.upper_zone_pass)

    def test_all_passed(self):
        """Summary when all Q-points pass."""
        for qp in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']:
            record_result(
                self.test, qp,
                ref_weight_kg=10.0,
                temperature_c=20.0,
                dut_volume_l=10.0,
                duration_s=120,
            )

        summary = get_test_summary(self.test)
        self.assertEqual(summary.completed_points, 8)
        self.assertEqual(summary.passed_points, 8)
        self.assertEqual(summary.failed_points, 0)
        self.assertTrue(summary.lower_zone_pass)
        self.assertTrue(summary.upper_zone_pass)

    def test_mixed_results(self):
        """Summary when some pass and some fail."""
        # Q1-Q3 pass (Lower zone)
        for qp in ['Q1', 'Q2', 'Q3']:
            record_result(
                self.test, qp,
                ref_weight_kg=10.0,
                temperature_c=20.0,
                dut_volume_l=10.0,
                duration_s=120,
            )
        # Q4 fail (Upper zone) — huge DUT error
        record_result(
            self.test, 'Q4',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=15.0,  # ~50% error → FAIL
            duration_s=120,
        )

        summary = get_test_summary(self.test)
        self.assertEqual(summary.completed_points, 4)
        self.assertEqual(summary.passed_points, 3)
        self.assertEqual(summary.failed_points, 1)
        self.assertTrue(summary.lower_zone_pass)
        self.assertFalse(summary.upper_zone_pass)

    def test_error_statistics(self):
        """Summary should compute min/max/avg error correctly."""
        # Record two Q-points with known errors
        record_result(
            self.test, 'Q6',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.0,
            duration_s=120,
        )
        record_result(
            self.test, 'Q7',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=10.1,
            duration_s=120,
        )

        summary = get_test_summary(self.test)
        self.assertIsNotNone(summary.min_error_pct)
        self.assertIsNotNone(summary.max_error_pct)
        self.assertIsNotNone(summary.avg_error_pct)
        self.assertLessEqual(summary.min_error_pct, summary.max_error_pct)

    def test_summary_metadata(self):
        """Summary should include test/meter metadata."""
        summary = get_test_summary(self.test)
        self.assertEqual(summary.test_id, self.test.pk)
        self.assertEqual(summary.meter_serial, 'TEST-001')
        self.assertEqual(summary.meter_size, 'DN15')
        self.assertEqual(summary.test_class, 'B')
        self.assertEqual(summary.status, 'running')

    def test_q_points_list(self):
        """Summary should contain a QPointSummary for each Q-point."""
        summary = get_test_summary(self.test)
        self.assertEqual(len(summary.q_points), 8)
        self.assertIsInstance(summary.q_points[0], QPointSummary)
        self.assertEqual(summary.q_points[0].q_point, 'Q1')


# ===========================================================================
#  complete_test tests
# ===========================================================================

class TestCompleteTest(TestBaseSetup):

    def setUp(self):
        super().setUp()
        self._create_q_point_results()

    def test_all_pass_overall_pass(self):
        """complete_test sets overall_pass=True when all Q-points pass."""
        for qp in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']:
            record_result(
                self.test, qp,
                ref_weight_kg=10.0,
                temperature_c=20.0,
                dut_volume_l=10.0,
                duration_s=120,
            )
        complete_test(self.test)
        self.test.refresh_from_db()
        self.assertTrue(self.test.overall_pass)
        self.assertEqual(self.test.status, 'completed')

    def test_one_fail_overall_fail(self):
        """complete_test sets overall_pass=False when any Q-point fails."""
        for qp in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7']:
            record_result(
                self.test, qp,
                ref_weight_kg=10.0,
                temperature_c=20.0,
                dut_volume_l=10.0,
                duration_s=120,
            )
        # Q8 fails
        record_result(
            self.test, 'Q8',
            ref_weight_kg=10.0,
            temperature_c=20.0,
            dut_volume_l=15.0,
            duration_s=120,
        )
        complete_test(self.test)
        self.test.refresh_from_db()
        self.assertFalse(self.test.overall_pass)


# ===========================================================================
#  start_test / abort_test tests
# ===========================================================================

class TestLifecycle(TestBaseSetup):

    def test_start_test(self):
        pending_test = Test.objects.create(
            meter=self.meter, test_class='B', status='pending',
        )
        start_test(pending_test)
        pending_test.refresh_from_db()
        self.assertEqual(pending_test.status, 'running')
        self.assertEqual(pending_test.current_q_point, 'Q1')
        self.assertEqual(pending_test.current_state, 'PRE_CHECK')
        self.assertIsNotNone(pending_test.started_at)

    def test_abort_test(self):
        abort_test(self.test, reason='E-stop')
        self.test.refresh_from_db()
        self.assertEqual(self.test.status, 'aborted')
        self.assertIn('E-stop', self.test.notes)
        self.assertEqual(self.test.current_state, 'EMERGENCY_STOP')


# ===========================================================================
#  record_manual_dut_entry tests (T-404)
# ===========================================================================

class TestRecordManualDUTEntry(TestBaseSetup):

    def test_before_creates_entry(self):
        """Creating a 'before' entry stores the value and timestamp."""
        from testing.services import record_manual_dut_entry
        entry = record_manual_dut_entry(
            self.test, 'Q1', 'before', 100.0,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.q_point, 'Q1')
        self.assertEqual(entry.before_value_l, 100.0)
        self.assertIsNotNone(entry.before_entered_at)
        self.assertIsNone(entry.after_value_l)
        self.assertIsNone(entry.volume_l)

    def test_after_updates_and_calculates_volume(self):
        """Adding an 'after' entry updates and auto-calculates volume."""
        from testing.services import record_manual_dut_entry
        record_manual_dut_entry(self.test, 'Q2', 'before', 200.0)
        entry = record_manual_dut_entry(self.test, 'Q2', 'after', 215.3)
        self.assertIsNotNone(entry)
        self.assertAlmostEqual(entry.volume_l, 15.3, places=4)
        self.assertIsNotNone(entry.after_entered_at)

    def test_after_without_before_creates_both(self):
        """Calling 'after' without a prior 'before' creates a fallback entry."""
        from testing.services import record_manual_dut_entry
        entry = record_manual_dut_entry(self.test, 'Q3', 'after', 50.0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.before_value_l, 0.0)
        self.assertEqual(entry.after_value_l, 50.0)
        self.assertAlmostEqual(entry.volume_l, 50.0, places=4)

    def test_idempotent_before(self):
        """Calling 'before' twice updates the existing entry."""
        from testing.services import record_manual_dut_entry
        from bench_ui.models import DUTManualEntry
        record_manual_dut_entry(self.test, 'Q4', 'before', 100.0)
        record_manual_dut_entry(self.test, 'Q4', 'before', 150.0)
        entries = DUTManualEntry.objects.filter(test=self.test, q_point='Q4')
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().before_value_l, 150.0)
