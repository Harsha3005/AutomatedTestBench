"""Unit tests for bench_ui app — models + API endpoints."""
import json
from unittest.mock import patch, MagicMock

from django.db import IntegrityError
from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser
from meters.models import TestMeter
from testing.models import Test
from bench_ui.models import SensorReading, DUTManualEntry


class BenchModelTestBase(TestCase):
    """Base class with test fixtures for bench_ui model tests."""

    def setUp(self):
        self.meter = TestMeter.objects.create(
            serial_number='BENCH-TEST-001',
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


# ===========================================================================
#  SensorReading tests
# ===========================================================================

class TestSensorReading(BenchModelTestBase):

    def test_create_periodic_reading(self):
        """Create a basic periodic sensor reading."""
        sr = SensorReading.objects.create(
            test=self.test,
            timestamp=timezone.now(),
            q_point='Q3',
            trigger='periodic',
            flow_rate_lph=150.5,
            em_totalizer_l=45.2,
            weight_kg=3.21,
            pressure_upstream_bar=3.5,
            pressure_downstream_bar=2.8,
            water_temp_c=22.1,
            vfd_freq_hz=25.0,
            vfd_current_a=4.2,
            diverter='COLLECT',
            active_lane='BV-L2',
        )
        self.assertEqual(sr.q_point, 'Q3')
        self.assertEqual(sr.trigger, 'periodic')
        self.assertAlmostEqual(sr.flow_rate_lph, 150.5)

    def test_str_representation(self):
        sr = SensorReading.objects.create(
            test=self.test,
            timestamp=timezone.now(),
            q_point='Q5',
            trigger='periodic',
        )
        self.assertIn('Q5', str(sr))

    def test_ordering_by_timestamp(self):
        """Readings should be ordered by timestamp ascending."""
        now = timezone.now()
        sr2 = SensorReading.objects.create(
            test=self.test,
            timestamp=now + timezone.timedelta(seconds=2),
            q_point='Q1',
        )
        sr1 = SensorReading.objects.create(
            test=self.test,
            timestamp=now,
            q_point='Q1',
        )
        readings = list(SensorReading.objects.filter(test=self.test))
        self.assertEqual(readings[0].pk, sr1.pk)
        self.assertEqual(readings[1].pk, sr2.pk)

    def test_event_trigger(self):
        """Event-triggered reading with label."""
        sr = SensorReading.objects.create(
            test=self.test,
            timestamp=timezone.now(),
            q_point='Q2',
            trigger='event',
            event_label='TARE',
        )
        self.assertEqual(sr.trigger, 'event')
        self.assertEqual(sr.event_label, 'TARE')

    def test_dut_totalizer_nullable(self):
        """dut_totalizer_l can be null (DUT not connected)."""
        sr = SensorReading.objects.create(
            test=self.test,
            timestamp=timezone.now(),
            dut_totalizer_l=None,
        )
        self.assertIsNone(sr.dut_totalizer_l)

    def test_cascade_delete(self):
        """Deleting the test should delete all sensor readings."""
        SensorReading.objects.create(
            test=self.test, timestamp=timezone.now(),
        )
        SensorReading.objects.create(
            test=self.test, timestamp=timezone.now(),
        )
        self.assertEqual(SensorReading.objects.filter(test=self.test).count(), 2)
        self.test.delete()
        self.assertEqual(SensorReading.objects.count(), 0)


# ===========================================================================
#  DUTManualEntry tests
# ===========================================================================

class TestDUTManualEntry(BenchModelTestBase):

    def test_create_entry(self):
        """Create a manual entry with before reading only."""
        entry = DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q1',
            before_value_l=100.0,
            before_entered_at=timezone.now(),
        )
        self.assertEqual(entry.q_point, 'Q1')
        self.assertEqual(entry.before_value_l, 100.0)
        self.assertIsNone(entry.volume_l)

    def test_auto_volume_calculation(self):
        """volume_l auto-calculated when both readings present."""
        entry = DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q3',
            before_value_l=100.0,
            before_entered_at=timezone.now(),
            after_value_l=110.5,
            after_entered_at=timezone.now(),
        )
        self.assertAlmostEqual(entry.volume_l, 10.5, places=4)

    def test_volume_update_on_save(self):
        """Adding after_value later recalculates volume."""
        entry = DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q2',
            before_value_l=200.0,
            before_entered_at=timezone.now(),
        )
        self.assertIsNone(entry.volume_l)

        entry.after_value_l = 215.3
        entry.after_entered_at = timezone.now()
        entry.save()
        self.assertAlmostEqual(entry.volume_l, 15.3, places=4)

    def test_unique_together(self):
        """Cannot have two entries for same test + q_point."""
        DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q1',
            before_value_l=100.0,
            before_entered_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            DUTManualEntry.objects.create(
                test=self.test,
                q_point='Q1',
                before_value_l=200.0,
                before_entered_at=timezone.now(),
            )

    def test_str_pending(self):
        """String representation for incomplete entry."""
        entry = DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q4',
            before_value_l=50.0,
            before_entered_at=timezone.now(),
        )
        self.assertIn('pending', str(entry))

    def test_str_completed(self):
        """String representation for completed entry with volume."""
        entry = DUTManualEntry.objects.create(
            test=self.test,
            q_point='Q5',
            before_value_l=50.0,
            before_entered_at=timezone.now(),
            after_value_l=60.123,
            after_entered_at=timezone.now(),
        )
        self.assertIn('10.123', str(entry))


# ===========================================================================
#  Test Execution API tests (T-402)
# ===========================================================================

class APITestBase(TestCase):
    """Base class with authenticated client for API tests."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='tech1', password='pass123', role='bench_tech',
        )
        self.meter = TestMeter.objects.create(
            serial_number='API-TEST-001',
            meter_size='DN15', meter_class='B', meter_type='mechanical',
        )
        self.test_obj = Test.objects.create(
            meter=self.meter, test_class='B', status='pending',
        )
        self.client = Client()
        self.client.login(username='tech1', password='pass123')


SM = 'controller.state_machine'


class TestAPITestStart(APITestBase):

    @patch(f'{SM}.get_active_machine', return_value=None)
    @patch(f'{SM}.start_test_machine')
    def test_start_ok(self, mock_start, mock_active):
        mock_sm = MagicMock()
        mock_sm.state.value = 'PRE_CHECK'
        mock_start.return_value = mock_sm
        resp = self.client.post(f'/bench/api/test/start/{self.test_obj.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['test_id'], self.test_obj.pk)

    @patch(f'{SM}.get_active_machine')
    def test_start_already_running(self, mock_active):
        mock_sm = MagicMock()
        mock_sm.test_id = 99
        mock_active.return_value = mock_sm
        resp = self.client.post(f'/bench/api/test/start/{self.test_obj.pk}/')
        self.assertEqual(resp.status_code, 409)

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_start_invalid_status(self, mock_active):
        self.test_obj.status = 'completed'
        self.test_obj.save()
        resp = self.client.post(f'/bench/api/test/start/{self.test_obj.pk}/')
        self.assertEqual(resp.status_code, 400)

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_start_not_found(self, mock_active):
        resp = self.client.post('/bench/api/test/start/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_start_requires_auth(self):
        self.client.logout()
        resp = self.client.post(f'/bench/api/test/start/{self.test_obj.pk}/')
        self.assertEqual(resp.status_code, 302)  # redirect to login

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_start_requires_role(self, mock_active):
        CustomUser.objects.create_user(
            username='labtech', password='pass123', role='lab_tech',
        )
        self.client.login(username='labtech', password='pass123')
        resp = self.client.post(f'/bench/api/test/start/{self.test_obj.pk}/')
        self.assertEqual(resp.status_code, 403)


class TestAPITestAbort(APITestBase):

    @patch(f'{SM}.abort_active_test', return_value=True)
    def test_abort_ok(self, mock_abort):
        resp = self.client.post(
            '/bench/api/test/abort/',
            data=json.dumps({'reason': 'test'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])

    @patch(f'{SM}.abort_active_test', return_value=False)
    def test_abort_no_active(self, mock_abort):
        resp = self.client.post('/bench/api/test/abort/')
        self.assertEqual(resp.status_code, 404)


class TestAPITestStatus(APITestBase):

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_status_idle(self, mock_active):
        resp = self.client.get('/bench/api/test/status/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['active'])
        self.assertEqual(data['state'], 'IDLE')

    @patch(f'{SM}.get_active_machine')
    def test_status_running(self, mock_active):
        mock_sm = MagicMock()
        mock_sm.state.value = 'FLOW_STABILIZE'
        mock_sm.test_id = 42
        mock_sm.current_q_point = 'Q3'
        mock_active.return_value = mock_sm
        resp = self.client.get('/bench/api/test/status/')
        data = resp.json()
        self.assertTrue(data['active'])
        self.assertEqual(data['state'], 'FLOW_STABILIZE')
        self.assertEqual(data['q_point'], 'Q3')


class TestAPIDUTPrompt(APITestBase):

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_no_pending(self, mock_active):
        resp = self.client.get('/bench/api/test/dut-prompt/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['pending'])


class TestAPIDUTSubmit(APITestBase):

    @patch(f'{SM}.get_active_machine')
    def test_submit_ok(self, mock_active):
        mock_sm = MagicMock()
        mock_sm.submit_manual_dut_reading.return_value = True
        mock_active.return_value = mock_sm
        resp = self.client.post(
            '/bench/api/test/dut-submit/',
            data=json.dumps({'reading_type': 'before', 'value': 100.0}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])

    @patch(f'{SM}.get_active_machine')
    def test_submit_bad_type(self, mock_active):
        mock_active.return_value = MagicMock()
        resp = self.client.post(
            '/bench/api/test/dut-submit/',
            data=json.dumps({'reading_type': 'invalid', 'value': 10.0}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f'{SM}.get_active_machine', return_value=None)
    def test_submit_no_active(self, mock_active):
        resp = self.client.post(
            '/bench/api/test/dut-submit/',
            data=json.dumps({'reading_type': 'before', 'value': 10.0}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)


class TestEmergencyStopAPI(APITestBase):

    @patch(f'{SM}.abort_active_test')
    def test_emergency_stop_calls_abort(self, mock_abort):
        mock_abort.return_value = True
        resp = self.client.post('/bench/emergency-stop/')
        mock_abort.assert_called_once()
        self.assertEqual(resp.status_code, 302)  # redirects to dashboard


# ===========================================================================
#  WebSocket Consumer tests (T-604)
# ===========================================================================

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from bench_ui.consumers import TestConsumer
from bench_ui.routing import websocket_urlpatterns
from testing.models import TestResult, ISO4064Standard


class TestConsumerTests(TestCase):
    """Tests for the WebSocket TestConsumer."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='wstech', password='test123', role='bench_tech',
        )
        self.meter = TestMeter.objects.create(
            serial_number='WS-TEST-001',
            meter_size='DN15',
            meter_class='R160',
            meter_type='mechanical',
            dut_mode='manual',
        )
        self.test_obj = Test.objects.create(
            meter=self.meter,
            test_class='R160',
            source='bench',
            status='pending',
            initiated_by=self.user,
        )
        for i in range(1, 9):
            ISO4064Standard.objects.get_or_create(
                meter_size='DN15', meter_class='R160', q_point=f'Q{i}',
                defaults={
                    'flow_rate_lph': 100 * i,
                    'test_volume_l': 5.0,
                    'duration_s': 120,
                    'mpe_pct': 5.0 if i <= 2 else 2.0,
                    'zone': 'Lower' if i <= 2 else 'Upper',
                },
            )
            TestResult.objects.create(
                test=self.test_obj,
                q_point=f'Q{i}',
                target_flow_lph=100 * i,
                mpe_pct=5.0 if i <= 2 else 2.0,
                zone='Lower' if i <= 2 else 'Upper',
            )

    def _build_communicator(self):
        application = URLRouter(websocket_urlpatterns)
        return WebsocketCommunicator(
            application,
            f'/ws/test/{self.test_obj.pk}/',
        )

    async def test_consumer_connect_accept(self):
        """Consumer should accept WebSocket connection."""
        communicator = self._build_communicator()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_consumer_receives_test_data(self):
        """Consumer should send test data after connection."""
        communicator = self._build_communicator()
        await communicator.connect()
        response = await communicator.receive_json_from(timeout=3)
        self.assertEqual(response['type'], 'test_data')
        self.assertEqual(response['test_id'], self.test_obj.pk)
        self.assertEqual(response['status'], 'pending')
        self.assertIn('flow_rate', response)
        self.assertIn('results', response)
        self.assertEqual(len(response['results']), 8)
        self.assertIn('dut_prompt', response)
        await communicator.disconnect()

    async def test_consumer_result_fields(self):
        """Each Q-point result should have required fields."""
        communicator = self._build_communicator()
        await communicator.connect()
        response = await communicator.receive_json_from(timeout=3)
        r = response['results'][0]
        self.assertIn('q_point', r)
        self.assertIn('target_flow_lph', r)
        self.assertIn('error_pct', r)
        self.assertIn('passed', r)
        await communicator.disconnect()

    async def test_consumer_disconnect_cleanup(self):
        """Consumer should clean up on disconnect without errors."""
        communicator = self._build_communicator()
        await communicator.connect()
        await communicator.receive_json_from(timeout=3)
        await communicator.disconnect()
