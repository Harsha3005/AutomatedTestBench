from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard


@override_settings(DEPLOYMENT_TYPE='lab')
class LabDashboardTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.client.login(username='labadmin', password='test123')

    def test_dashboard_loads(self):
        resp = self.client.get(reverse('lab_ui:dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_stats(self):
        meter = TestMeter.objects.create(
            serial_number='TST-001', meter_size='DN15', meter_class='B',
        )
        Test.objects.create(meter=meter, initiated_by=self.admin, source='lab')
        resp = self.client.get(reverse('lab_ui:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'TST-001')

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('lab_ui:dashboard'))
        self.assertEqual(resp.status_code, 302)


@override_settings(DEPLOYMENT_TYPE='lab')
class LabTestWizardTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.meter = TestMeter.objects.create(
            serial_number='WIZ-001', meter_size='DN15', meter_class='B',
        )
        ISO4064Standard.objects.create(
            meter_size='DN15', meter_class='B', q_point='Q1',
            flow_rate_lph=15.6, test_volume_l=5.0, mpe_pct=5.0,
            zone='low', duration_s=120,
        )
        self.client.login(username='labadmin', password='test123')

    def test_wizard_get(self):
        resp = self.client.get(reverse('lab_ui:test_wizard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'WIZ-001')

    def test_wizard_post_creates_test(self):
        resp = self.client.post(reverse('lab_ui:test_wizard'), {
            'meter_id': self.meter.pk,
            'test_class': 'B',
            'notes': 'Wizard test',
        })
        self.assertEqual(resp.status_code, 302)
        test = Test.objects.first()
        self.assertIsNotNone(test)
        self.assertEqual(test.source, 'lab')
        self.assertEqual(test.notes, 'Wizard test')
        self.assertEqual(test.results.count(), 1)

    def test_wizard_requires_role(self):
        tech = CustomUser.objects.create_user(
            username='viewer', password='test123', role='developer',
        )
        self.client.login(username='viewer', password='test123')
        resp = self.client.get(reverse('lab_ui:test_wizard'))
        self.assertEqual(resp.status_code, 403)


@override_settings(DEPLOYMENT_TYPE='lab')
class LabLiveMonitorTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.meter = TestMeter.objects.create(
            serial_number='MON-001', meter_size='DN15', meter_class='B',
        )
        self.client.login(username='labadmin', password='test123')

    def test_monitor_no_active_test(self):
        resp = self.client.get(reverse('lab_ui:live_monitor', args=[0]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No Active Test')

    def test_monitor_with_test(self):
        test = Test.objects.create(
            meter=self.meter, initiated_by=self.admin, status='running',
        )
        resp = self.client.get(reverse('lab_ui:live_monitor', args=[test.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'Test #{test.pk}')

    def test_monitor_redirect_active(self):
        test = Test.objects.create(
            meter=self.meter, initiated_by=self.admin, status='running',
        )
        resp = self.client.get(reverse('lab_ui:live_monitor', args=[0]))
        self.assertRedirects(resp, reverse('lab_ui:live_monitor', args=[test.pk]))

    def test_monitor_data_api(self):
        test = Test.objects.create(
            meter=self.meter, initiated_by=self.admin, status='running',
        )
        resp = self.client.get(reverse('lab_ui:monitor_data', args=[test.pk]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['test_id'], test.pk)
        self.assertEqual(data['status'], 'running')


@override_settings(DEPLOYMENT_TYPE='lab')
class LabCertificatesTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.client.login(username='labadmin', password='test123')

    def test_certificates_page_loads(self):
        resp = self.client.get(reverse('lab_ui:certificates'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Certificates')


@override_settings(DEPLOYMENT_TYPE='lab')
class LabAuditLogTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.client.login(username='labadmin', password='test123')

    def test_audit_log_loads(self):
        resp = self.client.get(reverse('lab_ui:audit_log'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Audit Log')

    def test_audit_log_requires_admin_or_manager(self):
        tech = CustomUser.objects.create_user(
            username='tech', password='test123', role='lab_tech',
        )
        self.client.login(username='tech', password='test123')
        resp = self.client.get(reverse('lab_ui:audit_log'))
        self.assertEqual(resp.status_code, 403)

    def test_audit_export(self):
        resp = self.client.get(reverse('lab_ui:audit_export'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')


@override_settings(DEPLOYMENT_TYPE='lab')
class LabSettingsTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.client.login(username='labadmin', password='test123')

    def test_settings_loads(self):
        resp = self.client.get(reverse('lab_ui:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Settings')

    def test_settings_requires_admin(self):
        mgr = CustomUser.objects.create_user(
            username='mgr', password='test123', role='manager',
        )
        self.client.login(username='mgr', password='test123')
        resp = self.client.get(reverse('lab_ui:settings'))
        self.assertEqual(resp.status_code, 403)


@override_settings(DEPLOYMENT_TYPE='lab')
class LabCSVExportTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='labadmin', password='test123', role='admin',
        )
        self.meter = TestMeter.objects.create(
            serial_number='EXP-001', meter_size='DN15', meter_class='B',
        )
        self.client.login(username='labadmin', password='test123')

    def test_test_export_csv(self):
        Test.objects.create(
            meter=self.meter, initiated_by=self.admin, source='lab',
        )
        resp = self.client.get(reverse('lab_ui:test_export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = b''.join(resp.streaming_content).decode()
        self.assertIn('EXP-001', content)
