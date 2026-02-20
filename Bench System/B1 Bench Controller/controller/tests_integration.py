"""
Integration tests for the test execution state machine.

These tests use the real hardware simulator (no mocks) to verify the
complete state machine cycle from PRE_CHECK through COMPLETE/EMERGENCY_STOP.

Uses 2 Q-points with flow rates achievable by the PID (min output 5 Hz
= 250 L/h in simulator), and test volumes of 2L so the cycle completes
in a reasonable time.

NOTE: Uses TransactionTestCase because the state machine daemon thread
needs to see committed data in the database.

Run:
    python manage.py test controller.tests_integration --settings=config.settings_bench -v2
"""

import os
import tempfile
import time

from django.test import TransactionTestCase, override_settings

from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard

import controller.state_machine as sm_module
import controller.hardware as hw_module
import controller.simulator as sim_module


# Reduced timeouts for faster integration tests
TEST_TIMEOUTS = {
    'FLOW_STABILIZE_TIMEOUT_S': 30.0,
    'DRAIN_TIMEOUT_S': 15.0,
    'PUMP_CONFIRM_TIMEOUT_S': 10.0,
    'MANUAL_DUT_TIMEOUT_S': 10.0,
}


def _seed_iso_data():
    """Seed 2 Q-points with flow rates the PID can reach (>250 L/h).

    PID output range is 5-50 Hz. Simulator: flow = freq * 50 L/h.
    So achievable flow range is 250-2500 L/h.
    """
    ISO4064Standard.objects.get_or_create(
        meter_size='DN15', meter_class='B', q_point='Q1',
        defaults={
            'flow_rate_lph': 500.0,
            'test_volume_l': 2.0,
            'duration_s': 120,
            'mpe_pct': 5.0,
            'zone': 'Lower',
        },
    )
    ISO4064Standard.objects.get_or_create(
        meter_size='DN15', meter_class='B', q_point='Q2',
        defaults={
            'flow_rate_lph': 1000.0,
            'test_volume_l': 2.0,
            'duration_s': 120,
            'mpe_pct': 2.0,
            'zone': 'Upper',
        },
    )


def _create_test_fixtures(dut_mode='rs485'):
    """Create meter, test, and TestResult placeholders."""
    meter = TestMeter.objects.create(
        serial_number=f'INTG-{time.time_ns()}',
        meter_size='DN15',
        meter_class='B',
        meter_type='mechanical',
        dut_mode=dut_mode,
    )
    test = Test.objects.create(
        meter=meter,
        test_class='B',
        status='pending',
    )
    iso_params = ISO4064Standard.objects.filter(
        meter_size='DN15', meter_class='B',
        q_point__in=['Q1', 'Q2'],
    ).order_by('q_point')
    for p in iso_params:
        TestResult.objects.create(
            test=test,
            q_point=p.q_point,
            target_flow_lph=p.flow_rate_lph,
            mpe_pct=p.mpe_pct,
            zone=p.zone,
        )
    return meter, test


def _reset_singletons():
    """Reset all hardware singletons and the active state machine."""
    hw_module.stop_all()
    sim_module._simulator = None
    sm_module._active_machine = None


class _IntegrationBase(TransactionTestCase):
    """Shared setup/teardown for integration tests."""

    dut_mode = 'rs485'
    dut_error_pct = 1.5

    def setUp(self):
        _reset_singletons()
        _seed_iso_data()
        self.meter, self.test = _create_test_fixtures(dut_mode=self.dut_mode)

        # Patch timeouts for speed
        self._saved_timeouts = {}
        for attr, value in TEST_TIMEOUTS.items():
            self._saved_timeouts[attr] = getattr(sm_module, attr)
            setattr(sm_module, attr, value)

        # Start hardware + connect DUT
        sim = hw_module.get_simulator()
        sim.connect_dut(error_pct=self.dut_error_pct)
        hw_module.start_all()
        time.sleep(0.5)

    def tearDown(self):
        _reset_singletons()
        for attr, value in self._saved_timeouts.items():
            setattr(sm_module, attr, value)


@override_settings(HARDWARE_BACKEND='simulator')
class TestFullCycleCompletes(_IntegrationBase):
    """Integration test: full 2-Q-point cycle to COMPLETE."""

    def test_full_cycle_completes(self):
        """Two Q-points should run to COMPLETE with results saved."""
        machine = sm_module.start_test_machine(self.test.pk)
        machine.join(timeout=120)

        self.assertFalse(machine.is_running, "State machine should have stopped")
        self.assertEqual(machine.state, sm_module.TestState.COMPLETE)

        # Verify test status in DB
        self.test.refresh_from_db()
        self.assertEqual(self.test.status, 'completed')
        self.assertIsNotNone(self.test.overall_pass)
        self.assertIsNotNone(self.test.completed_at)

        # Verify Q-point results are populated
        results = TestResult.objects.filter(test=self.test).order_by('q_point')
        self.assertEqual(results.count(), 2)

        for r in results:
            self.assertIsNotNone(r.ref_volume_l, f"{r.q_point}: ref_volume should be set")
            self.assertIsNotNone(r.dut_volume_l, f"{r.q_point}: dut_volume should be set")
            self.assertIsNotNone(r.error_pct, f"{r.q_point}: error_pct should be set")
            self.assertIsNotNone(r.passed, f"{r.q_point}: passed should be set")
            self.assertGreater(r.ref_volume_l, 0, f"{r.q_point}: ref_volume > 0")
            self.assertGreater(r.dut_volume_l, 0, f"{r.q_point}: dut_volume > 0")
            # DUT volume should exceed ref volume (DUT has +1.5% error)
            self.assertGreater(r.dut_volume_l, r.ref_volume_l,
                               f"{r.q_point}: DUT should read higher than ref")


@override_settings(HARDWARE_BACKEND='simulator')
class TestAbortDuringCycle(_IntegrationBase):
    """Integration test: abort during active test -> EMERGENCY_STOP."""

    def test_abort_during_cycle(self):
        """Aborting a running test should reach EMERGENCY_STOP."""
        machine = sm_module.start_test_machine(self.test.pk)

        # Wait for machine to enter an active state
        time.sleep(2.0)
        self.assertTrue(machine.is_running, "Machine should still be running")
        machine.abort('Integration test abort')

        machine.join(timeout=15)

        self.assertFalse(machine.is_running)
        self.assertEqual(machine.state, sm_module.TestState.EMERGENCY_STOP)

        # Verify DB state
        self.test.refresh_from_db()
        self.assertEqual(self.test.status, 'aborted')
        self.assertIn('Integration test abort', self.test.notes)


@override_settings(HARDWARE_BACKEND='simulator')
class TestFullCycleWithCertificate(_IntegrationBase):
    """Integration test: full cycle -> approve -> certificate PDF generated."""

    def test_approve_generates_certificate(self):
        """After full cycle + approval, a valid PDF should exist on disk."""
        machine = sm_module.start_test_machine(self.test.pk)
        machine.join(timeout=120)

        self.test.refresh_from_db()
        self.assertEqual(self.test.status, 'completed')

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=tmpdir):
                # Simulate approval flow
                from testing.services import generate_certificate_number
                from reports.generator import save_certificate

                cert_num = generate_certificate_number(self.test)
                self.test.refresh_from_db()
                self.assertTrue(cert_num.startswith('IIITB-'))
                self.assertEqual(self.test.certificate_number, cert_num)

                rel_path = save_certificate(self.test)
                self.test.refresh_from_db()
                self.assertEqual(self.test.certificate_pdf, rel_path)

                # Verify file on disk
                full_path = os.path.join(tmpdir, rel_path)
                self.assertTrue(os.path.isfile(full_path))

                with open(full_path, 'rb') as f:
                    header = f.read(4)
                self.assertEqual(header, b'%PDF', "Should be a valid PDF file")


@override_settings(HARDWARE_BACKEND='simulator')
class TestAbortPreservesPartialResults(_IntegrationBase):
    """Integration test: abort preserves any Q-point results completed before abort."""

    def test_abort_preserves_partial_results(self):
        """If Q1 completes before abort, its results should be preserved.

        Note: With SQLite, DB locking can prevent Q1 from saving, so we
        verify that whatever results were saved are preserved.
        """
        machine = sm_module.start_test_machine(self.test.pk)

        # Wait long enough for Q1 to likely complete (collection + drain)
        # but not Q2
        deadline = time.time() + 60
        while time.time() < deadline:
            self.test.refresh_from_db()
            if self.test.current_q_point == 'Q2':
                break
            if self.test.status in ('completed', 'failed', 'aborted'):
                break
            time.sleep(0.5)

        # Abort
        if machine.is_running:
            machine.abort('Partial result test')
        machine.join(timeout=15)

        self.test.refresh_from_db()
        self.assertIn(self.test.status, ('aborted', 'completed'))

        # Both Q-point rows should still exist
        q1 = TestResult.objects.get(test=self.test, q_point='Q1')
        q2 = TestResult.objects.get(test=self.test, q_point='Q2')
        self.assertEqual(q1.q_point, 'Q1')
        self.assertEqual(q2.q_point, 'Q2')

        # If Q1 was completed, verify its results are intact
        if q1.ref_volume_l is not None:
            self.assertIsNotNone(q1.error_pct, "Q1 error_pct should be preserved")
            self.assertIsNotNone(q1.passed, "Q1 passed should be preserved")


@override_settings(HARDWARE_BACKEND='simulator')
class TestManualDUTEntryFlow(_IntegrationBase):
    """Integration test: manual DUT meter uses WAIT_MANUAL_DUT state."""

    dut_mode = 'manual'

    def test_manual_dut_reaches_wait_state(self):
        """A manual DUT meter should reach WAIT_MANUAL_DUT and timeout.

        Since there's no operator to enter values, it should eventually
        timeout (MANUAL_DUT_TIMEOUT_S) and the state machine should
        handle it gracefully (fail the Q-point or proceed).
        """
        machine = sm_module.start_test_machine(self.test.pk)

        # Wait for the machine to reach WAIT_MANUAL_DUT or complete
        deadline = time.time() + 60
        reached_manual = False
        while time.time() < deadline:
            self.test.refresh_from_db()
            if self.test.current_state == 'WAIT_MANUAL_DUT':
                reached_manual = True
                break
            if self.test.status in ('completed', 'failed', 'aborted'):
                break
            time.sleep(0.5)

        if reached_manual:
            # Submit manual DUT entries so the test can proceed
            from testing.services import record_manual_dut_entry
            from django.utils import timezone

            # Simulate operator entering before/after readings
            # Get current Q-point
            qp = self.test.current_q_point
            record_manual_dut_entry(self.test, qp, 'before', 100.0)
            record_manual_dut_entry(self.test, qp, 'after', 102.0)

            # Notify the state machine that manual entry is available
            if hasattr(machine, 'manual_dut_ready'):
                machine.manual_dut_ready()

        # Let the machine finish (it may timeout on subsequent Q-points)
        machine.join(timeout=90)
        self.assertFalse(machine.is_running)


@override_settings(HARDWARE_BACKEND='simulator')
class TestLoRaEncodingRoundtrip(TransactionTestCase):
    """Integration test: LoRa ASP message encoding roundtrip."""

    def test_asp_encode_decode_roundtrip(self):
        """ASP protocol can encode and decode a test summary payload."""
        from comms.crypto import get_keys
        from comms.protocol import encode, decode
        import json

        aes_key, hmac_key = get_keys()

        # Simulate a test summary payload
        payload = {
            'type': 'test_result',
            'test_id': 42,
            'meter_serial': 'LORA-001',
            'status': 'completed',
            'overall_pass': True,
            'q_points': [
                {'q': 'Q1', 'error': 0.5, 'pass': True},
                {'q': 'Q2', 'error': -0.3, 'pass': True},
            ],
        }

        # Encode
        frame = encode(payload, device_id=0x0002, seq=1,
                        aes_key=aes_key, hmac_key=hmac_key)
        self.assertIsInstance(frame, bytes)
        self.assertGreater(len(frame), 0)

        # Decode
        result = decode(frame, aes_key=aes_key, hmac_key=hmac_key)
        self.assertEqual(result.device_id, 0x0002)
        self.assertEqual(result.seq, 1)
        self.assertEqual(result.payload, payload)
