"""Test lifecycle service functions.

Provides helper functions for test state transitions, result calculations,
and certificate generation. Used by both the test engine (controller app)
and the web views.
"""
from dataclasses import dataclass, field
from django.utils import timezone

from testing.models import Test, TestResult
from testing.iso4064 import water_density, calculate_error, check_pass


# ---------------------------------------------------------------------------
#  Exceptions
# ---------------------------------------------------------------------------

class MeasurementValidationError(Exception):
    """Raised when measurement inputs fail validation."""
    pass


# ---------------------------------------------------------------------------
#  Validation
# ---------------------------------------------------------------------------

def validate_measurement_inputs(
    ref_weight_kg: float,
    temperature_c: float,
    dut_volume_l: float,
    duration_s: float | int | None,
) -> None:
    """Validate measurement inputs before calculation.

    Raises MeasurementValidationError with a descriptive message
    if any input is out of acceptable range.
    """
    if ref_weight_kg <= 0:
        raise MeasurementValidationError(
            f"Reference weight must be positive, got {ref_weight_kg} kg"
        )
    if not (1.0 <= temperature_c <= 50.0):
        raise MeasurementValidationError(
            f"Water temperature must be 1-50°C, got {temperature_c}°C"
        )
    if dut_volume_l < 0:
        raise MeasurementValidationError(
            f"DUT volume cannot be negative, got {dut_volume_l} L"
        )
    if duration_s is not None and duration_s <= 0:
        raise MeasurementValidationError(
            f"Duration must be positive, got {duration_s} s"
        )


# ---------------------------------------------------------------------------
#  Test lifecycle
# ---------------------------------------------------------------------------

def start_test(test: Test) -> None:
    """Transition test from pending to running."""
    test.status = 'running'
    test.started_at = timezone.now()
    test.current_q_point = 'Q1'
    test.current_state = 'PRE_CHECK'
    test.save()


def update_test_state(test: Test, q_point: str, state: str) -> None:
    """Update the current Q-point and state for live monitoring."""
    test.current_q_point = q_point
    test.current_state = state
    test.save(update_fields=['current_q_point', 'current_state'])


def record_result(
    test: Test,
    q_point: str,
    ref_weight_kg: float,
    temperature_c: float,
    dut_volume_l: float,
    pressure_up_bar: float = None,
    pressure_dn_bar: float = None,
    duration_s: int = None,
) -> TestResult:
    """Calculate and store a single Q-point result.

    Validates inputs, calculates reference volume via density correction,
    computes error percentage, and populates actual_flow_lph.

    Raises:
        MeasurementValidationError: If inputs are out of range.
    """
    validate_measurement_inputs(ref_weight_kg, temperature_c, dut_volume_l, duration_s)

    density = water_density(temperature_c)
    ref_volume = ref_weight_kg / density
    error_pct = calculate_error(ref_volume, dut_volume_l)

    # Calculate actual flow rate: volume / time → L/h
    actual_flow_lph = None
    if duration_s and duration_s > 0:
        actual_flow_lph = round((ref_volume / duration_s) * 3600, 2)

    result = TestResult.objects.get(test=test, q_point=q_point)
    result.ref_volume_l = round(ref_volume, 4)
    result.dut_volume_l = round(dut_volume_l, 4)
    result.error_pct = round(error_pct, 3)
    result.passed = check_pass(error_pct, result.mpe_pct)
    result.actual_flow_lph = actual_flow_lph
    result.pressure_up_bar = pressure_up_bar
    result.pressure_dn_bar = pressure_dn_bar
    result.temperature_c = temperature_c
    result.duration_s = duration_s
    result.weight_kg = round(ref_weight_kg, 4)
    result.save()
    return result


def complete_test(test: Test) -> None:
    """Finalize a test after all Q-points are done."""
    results = test.results.all()
    all_passed = all(r.passed for r in results if r.passed is not None)
    test.status = 'completed'
    test.overall_pass = all_passed
    test.completed_at = timezone.now()
    test.current_state = 'COMPLETE'
    test.save()


def abort_test(test: Test, reason: str = '') -> None:
    """Abort a running test."""
    test.status = 'aborted'
    test.completed_at = timezone.now()
    test.current_state = 'EMERGENCY_STOP'
    test.notes = f"Aborted: {reason}" if reason else "Aborted"
    test.save()


def generate_certificate_number(test: Test) -> str:
    """Generate a certificate number for a passed test."""
    date_str = timezone.now().strftime('%Y%m%d')
    count = Test.objects.filter(
        certificate_number__startswith=f'IIITB-{date_str}',
    ).count() + 1
    cert_number = f'IIITB-{date_str}-{count:04d}'
    test.certificate_number = cert_number
    test.save(update_fields=['certificate_number'])
    return cert_number


# ---------------------------------------------------------------------------
#  State machine orchestrator — process_q_point_result
# ---------------------------------------------------------------------------

def process_q_point_result(
    test: Test,
    q_point: str,
    gravimetric_result,
    dut_reading,
    pressure_up_bar: float = None,
    pressure_dn_bar: float = None,
) -> TestResult:
    """High-level entry point for recording a Q-point measurement.

    Called by the state machine (T-401) after gravimetric collection
    and DUT reading are both complete.

    Args:
        test: The active Test instance.
        q_point: Q-point label (Q1-Q8).
        gravimetric_result: controller.gravimetric.GravimetricResult dataclass.
        dut_reading: controller.dut_interface.DUTReading dataclass.
        pressure_up_bar: Upstream pressure at time of measurement.
        pressure_dn_bar: Downstream pressure at time of measurement.

    Returns:
        The updated TestResult.

    Raises:
        MeasurementValidationError: If gravimetric measurement failed or
            inputs are out of range.
    """
    if not gravimetric_result.success:
        raise MeasurementValidationError(
            f"Gravimetric measurement failed: {gravimetric_result.error_message}"
        )

    return record_result(
        test=test,
        q_point=q_point,
        ref_weight_kg=gravimetric_result.net_weight_kg,
        temperature_c=gravimetric_result.temperature_c,
        dut_volume_l=dut_reading.volume_l,
        pressure_up_bar=pressure_up_bar,
        pressure_dn_bar=pressure_dn_bar,
        duration_s=int(gravimetric_result.collect_time_s) if gravimetric_result.collect_time_s else None,
    )


# ---------------------------------------------------------------------------
#  Test summary — for UI, reports, certificate, LoRa transmission
# ---------------------------------------------------------------------------

@dataclass
class QPointSummary:
    """Summary of a single Q-point result for UI display."""
    q_point: str = ''
    zone: str = ''
    target_flow_lph: float = 0.0
    actual_flow_lph: float | None = None
    ref_volume_l: float | None = None
    dut_volume_l: float | None = None
    error_pct: float | None = None
    mpe_pct: float = 0.0
    passed: bool | None = None
    temperature_c: float | None = None
    weight_kg: float | None = None


@dataclass
class TestSummary:
    """Overall test summary with per-zone verdicts and statistics."""
    test_id: int = 0
    meter_serial: str = ''
    meter_size: str = ''
    test_class: str = ''
    status: str = ''
    overall_pass: bool | None = None
    started_at: str = ''
    completed_at: str = ''
    certificate_number: str = ''

    # Per-zone verdicts
    lower_zone_pass: bool | None = None
    upper_zone_pass: bool | None = None

    # Error statistics
    min_error_pct: float | None = None
    max_error_pct: float | None = None
    avg_error_pct: float | None = None

    # Counts
    total_points: int = 0
    completed_points: int = 0
    passed_points: int = 0
    failed_points: int = 0

    # Per-point details
    q_points: list = field(default_factory=list)


def get_test_summary(test: Test) -> TestSummary:
    """Build a structured test summary for UI / reports / LoRa.

    Returns a TestSummary dataclass with zone-level verdicts,
    error statistics, and per-point details.
    """
    results = list(test.results.all().order_by('q_point'))

    q_summaries = []
    errors = []
    lower_results = []
    upper_results = []

    for r in results:
        qs = QPointSummary(
            q_point=r.q_point,
            zone=r.zone,
            target_flow_lph=r.target_flow_lph,
            actual_flow_lph=r.actual_flow_lph,
            ref_volume_l=r.ref_volume_l,
            dut_volume_l=r.dut_volume_l,
            error_pct=r.error_pct,
            mpe_pct=r.mpe_pct,
            passed=r.passed,
            temperature_c=r.temperature_c,
            weight_kg=r.weight_kg,
        )
        q_summaries.append(qs)

        if r.error_pct is not None:
            errors.append(r.error_pct)

        if r.zone == 'Lower' and r.passed is not None:
            lower_results.append(r.passed)
        elif r.zone == 'Upper' and r.passed is not None:
            upper_results.append(r.passed)

    completed = [r for r in results if r.passed is not None]

    summary = TestSummary(
        test_id=test.pk,
        meter_serial=test.meter.serial_number,
        meter_size=test.meter.meter_size,
        test_class=test.test_class,
        status=test.status,
        overall_pass=test.overall_pass,
        started_at=test.started_at.isoformat() if test.started_at else '',
        completed_at=test.completed_at.isoformat() if test.completed_at else '',
        certificate_number=test.certificate_number,
        lower_zone_pass=all(lower_results) if lower_results else None,
        upper_zone_pass=all(upper_results) if upper_results else None,
        min_error_pct=round(min(errors), 3) if errors else None,
        max_error_pct=round(max(errors), 3) if errors else None,
        avg_error_pct=round(sum(errors) / len(errors), 3) if errors else None,
        total_points=len(results),
        completed_points=len(completed),
        passed_points=sum(1 for r in completed if r.passed),
        failed_points=sum(1 for r in completed if not r.passed),
        q_points=q_summaries,
    )
    return summary


# ---------------------------------------------------------------------------
#  Sensor reading helper — creates bench_ui.SensorReading from SensorSnapshot
# ---------------------------------------------------------------------------

def record_sensor_reading(test: Test, snapshot, q_point: str = '',
                          trigger: str = 'periodic', event_label: str = '',
                          diverter: str = 'BYPASS', active_lane: str = ''):
    """Create a SensorReading from a SensorSnapshot.

    Lazy-imports the bench_ui model to avoid circular imports and
    to keep this service usable from both bench and lab contexts
    (on lab, bench_ui isn't installed, so this is a no-op).
    """
    try:
        from bench_ui.models import SensorReading
    except ImportError:
        return None

    return SensorReading.objects.create(
        test=test,
        timestamp=timezone.now(),
        q_point=q_point,
        trigger=trigger,
        event_label=event_label,
        flow_rate_lph=snapshot.flow_rate_lph,
        em_totalizer_l=snapshot.em_totalizer_l,
        weight_kg=snapshot.weight_kg,
        pressure_upstream_bar=snapshot.pressure_upstream_bar,
        pressure_downstream_bar=snapshot.pressure_downstream_bar,
        water_temp_c=snapshot.water_temp_c,
        vfd_freq_hz=snapshot.vfd_freq_hz,
        vfd_current_a=snapshot.vfd_current_a,
        dut_totalizer_l=snapshot.dut_totalizer_l,
        diverter=diverter,
        active_lane=active_lane,
    )


# ---------------------------------------------------------------------------
#  Manual DUT entry — persists operator readings to bench_ui.DUTManualEntry
# ---------------------------------------------------------------------------

def record_manual_dut_entry(test: Test, q_point: str, reading_type: str,
                            value: float, entered_by=None):
    """Create or update a DUTManualEntry for a manual DUT reading.

    Args:
        test: The active Test instance.
        q_point: Q-point label (Q1-Q8).
        reading_type: 'before' or 'after'.
        value: Totalizer reading in litres.
        entered_by: User who entered the reading (optional).

    Returns:
        The DUTManualEntry instance, or None on lab deployment.
    """
    try:
        from bench_ui.models import DUTManualEntry
    except ImportError:
        return None

    now = timezone.now()

    if reading_type == 'before':
        entry, _ = DUTManualEntry.objects.update_or_create(
            test=test,
            q_point=q_point,
            defaults={
                'before_value_l': value,
                'before_entered_at': now,
                'before_entered_by': entered_by,
            },
        )
        return entry

    elif reading_type == 'after':
        try:
            entry = DUTManualEntry.objects.get(test=test, q_point=q_point)
        except DUTManualEntry.DoesNotExist:
            entry = DUTManualEntry(
                test=test,
                q_point=q_point,
                before_value_l=0.0,
                before_entered_at=now,
            )
        entry.after_value_l = value
        entry.after_entered_at = now
        entry.after_entered_by = entered_by
        entry.save()  # triggers volume auto-calc in model save()
        return entry

    return None
