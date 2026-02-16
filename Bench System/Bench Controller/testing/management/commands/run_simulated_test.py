"""
Run a full simulated ISO 4064 test cycle using the hardware simulator.

Demonstrates the complete end-to-end flow:
  seed ISO data → create meter/test → start hardware → run state machine →
  report results → stop hardware

Usage:
    python manage.py run_simulated_test
    python manage.py run_simulated_test --meter-size DN20 --meter-class B
    python manage.py run_simulated_test --timeout 300 --dut-error 2.0
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard
from testing.services import get_test_summary


class Command(BaseCommand):
    help = 'Run a full simulated ISO 4064 test cycle'

    def add_arguments(self, parser):
        parser.add_argument(
            '--meter-size', default='DN15',
            help='Meter size (DN15, DN20, DN25). Default: DN15',
        )
        parser.add_argument(
            '--meter-class', default='B',
            help='Meter class (A, B, C, R80, R100, R160, R200). Default: B',
        )
        parser.add_argument(
            '--timeout', type=int, default=600,
            help='Max wait time in seconds. Default: 600',
        )
        parser.add_argument(
            '--dut-error', type=float, default=1.5,
            help='Simulated DUT error %%. Default: 1.5',
        )

    def handle(self, *args, **options):
        meter_size = options['meter_size']
        meter_class = options['meter_class']
        timeout = options['timeout']
        dut_error = options['dut_error']

        self.stdout.write(self.style.NOTICE(
            f"\n{'='*60}\n"
            f"  Simulated ISO 4064 Test Cycle\n"
            f"  Meter: {meter_size} Class {meter_class}\n"
            f"  DUT error: {dut_error}%\n"
            f"  Timeout: {timeout}s\n"
            f"{'='*60}\n"
        ))

        # Step 1: Ensure ISO data is seeded
        self.stdout.write("Step 1: Seeding ISO 4064 data...")
        call_command('seed_iso4064', verbosity=0)

        iso_count = ISO4064Standard.objects.filter(
            meter_size=meter_size, meter_class=meter_class,
        ).count()
        if iso_count == 0:
            self.stdout.write(self.style.ERROR(
                f"No ISO data for {meter_size} / {meter_class}. Aborting."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"  {iso_count} Q-points available for {meter_size} {meter_class}"
        ))

        # Step 2: Create meter and test
        self.stdout.write("Step 2: Creating meter and test records...")
        meter, _ = TestMeter.objects.get_or_create(
            serial_number=f'SIM-{meter_size}-{meter_class}-001',
            defaults={
                'meter_size': meter_size,
                'meter_class': meter_class,
                'meter_type': 'mechanical',
                'dut_mode': 'rs485',
            },
        )

        test = Test.objects.create(
            meter=meter,
            test_class=meter_class,
            status='pending',
            source='bench',
        )

        # Create TestResult placeholders
        iso_params = ISO4064Standard.objects.filter(
            meter_size=meter_size, meter_class=meter_class,
        ).order_by('q_point')
        for p in iso_params:
            TestResult.objects.create(
                test=test,
                q_point=p.q_point,
                target_flow_lph=p.flow_rate_lph,
                mpe_pct=p.mpe_pct,
                zone=p.zone,
            )

        self.stdout.write(self.style.SUCCESS(
            f"  Test #{test.pk}, meter {meter.serial_number}"
        ))

        # Step 3: Start hardware
        self.stdout.write("Step 3: Starting hardware (simulator)...")
        from controller.hardware import start_all, stop_all, get_simulator

        sim = get_simulator()
        sim.connect_dut(error_pct=dut_error)
        start_all()
        time.sleep(0.5)  # Let first sensor poll complete

        self.stdout.write(self.style.SUCCESS("  Hardware started"))

        # Step 4: Run state machine
        self.stdout.write("Step 4: Starting state machine...")
        from controller.state_machine import start_test_machine

        try:
            sm = start_test_machine(test.pk)
            self.stdout.write(self.style.SUCCESS(
                f"  State machine started (state={sm.state.value})"
            ))

            # Poll state
            self.stdout.write("Step 5: Monitoring test execution...\n")
            start_time = time.time()
            last_state = ''
            last_q = ''

            while sm.is_running and (time.time() - start_time) < timeout:
                state = sm.state.value
                q_point = sm.current_q_point
                if state != last_state or q_point != last_q:
                    elapsed = time.time() - start_time
                    self.stdout.write(
                        f"  [{elapsed:6.1f}s] {q_point:>3s} / {state}"
                    )
                    last_state = state
                    last_q = q_point
                time.sleep(1.0)

            # Final state
            elapsed = time.time() - start_time
            self.stdout.write(f"\n  Finished in {elapsed:.1f}s (state={sm.state.value})")

        finally:
            # Step 6: Stop hardware
            self.stdout.write("\nStep 6: Stopping hardware...")
            stop_all()
            self.stdout.write(self.style.SUCCESS("  Hardware stopped"))

        # Step 7: Report results
        self.stdout.write("\nStep 7: Test Results\n" + "-" * 60)
        test.refresh_from_db()

        summary = get_test_summary(test)
        self.stdout.write(f"  Status: {summary.status}")
        self.stdout.write(f"  Overall: {'PASS' if summary.overall_pass else 'FAIL'}")
        if summary.certificate_number:
            self.stdout.write(f"  Certificate: {summary.certificate_number}")

        self.stdout.write(f"\n  {'Q-Pt':<5} {'Zone':<6} {'Target':>8} {'Actual':>8} "
                          f"{'Error%':>8} {'MPE%':>6} {'Result':>7}")
        self.stdout.write(f"  {'----':<5} {'----':<6} {'------':>8} {'------':>8} "
                          f"{'------':>8} {'----':>6} {'------':>7}")

        for qp in summary.q_points:
            actual = f"{qp.actual_flow_lph:.1f}" if qp.actual_flow_lph else "  --"
            error = f"{qp.error_pct:.3f}" if qp.error_pct is not None else "  --"
            result = "PASS" if qp.passed else ("FAIL" if qp.passed is False else "PEND")
            self.stdout.write(
                f"  {qp.q_point:<5} {qp.zone:<6} {qp.target_flow_lph:>8.1f} "
                f"{actual:>8} {error:>8} {qp.mpe_pct:>6.1f} {result:>7}"
            )

        self.stdout.write(f"\n  Points: {summary.passed_points} passed, "
                          f"{summary.failed_points} failed, "
                          f"{summary.total_points - summary.completed_points} pending")
        if summary.avg_error_pct is not None:
            self.stdout.write(f"  Error range: {summary.min_error_pct:.3f}% "
                              f"to {summary.max_error_pct:.3f}% "
                              f"(avg {summary.avg_error_pct:.3f}%)")

        self.stdout.write("\n" + "=" * 60)
        if summary.overall_pass:
            self.stdout.write(self.style.SUCCESS("  TEST PASSED"))
        elif summary.status == 'aborted':
            self.stdout.write(self.style.ERROR("  TEST ABORTED"))
        else:
            self.stdout.write(self.style.ERROR("  TEST FAILED"))
        self.stdout.write("=" * 60 + "\n")
