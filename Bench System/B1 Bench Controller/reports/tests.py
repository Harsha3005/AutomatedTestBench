"""Tests for the reports app — error curve and PDF certificate generation."""

import os
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard
from testing.services import get_test_summary, generate_certificate_number
from reports.error_curve import generate_error_curve_image
from reports.generator import generate_certificate_pdf, save_certificate


User = get_user_model()


class ReportTestBase(TestCase):
    """Shared setup: user, meter, test with 8 Q-point results."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='tech', password='testpass', role='lab_tech',
        )
        cls.meter = TestMeter.objects.create(
            serial_number='RPT-001',
            meter_size='DN15',
            meter_class='B',
            manufacturer='TestCo',
            model_name='TM-100',
            meter_type='mechanical',
            registered_by=cls.user,
        )

        # ISO 4064 standards for DN15 Class B
        q_specs = [
            ('Q1', 'Lower', 15.0,  5.0, 1200, 5.0),
            ('Q2', 'Lower', 22.5,  5.0, 800,  5.0),
            ('Q3', 'Lower', 30.0,  5.0, 600,  5.0),
            ('Q4', 'Upper', 60.0,  10.0, 600,  2.0),
            ('Q5', 'Upper', 120.0, 10.0, 300,  2.0),
            ('Q6', 'Upper', 750.0, 50.0, 240,  2.0),
            ('Q7', 'Upper', 1500.0, 100.0, 240, 2.0),
            ('Q8', 'Upper', 3000.0, 200.0, 240, 2.0),
        ]
        for qp, zone, flow, vol, dur, mpe in q_specs:
            ISO4064Standard.objects.create(
                meter_size='DN15', meter_class='B', q_point=qp,
                flow_rate_lph=flow, test_volume_l=vol,
                duration_s=dur, mpe_pct=mpe, zone=zone,
            )

        from django.utils import timezone
        cls.test = Test.objects.create(
            meter=cls.meter,
            test_class='B',
            status='completed',
            overall_pass=True,
            initiated_by=cls.user,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        # Populate results with realistic data
        results_data = [
            ('Q1', 'Lower', 15.0, 5.0, 4.98, 5.02, 0.803, 5.0, True, 20.5, 4.98),
            ('Q2', 'Lower', 22.5, 5.0, 4.99, 5.01, 0.401, 5.0, True, 20.5, 4.99),
            ('Q3', 'Lower', 30.0, 5.0, 5.00, 5.02, 0.400, 5.0, True, 20.5, 5.00),
            ('Q4', 'Upper', 60.0, 10.0, 9.99, 10.01, 0.200, 2.0, True, 20.5, 9.99),
            ('Q5', 'Upper', 120.0, 10.0, 10.00, 10.01, 0.100, 2.0, True, 20.5, 10.00),
            ('Q6', 'Upper', 750.0, 50.0, 49.98, 50.01, 0.060, 2.0, True, 20.5, 49.98),
            ('Q7', 'Upper', 1500.0, 100.0, 99.99, 100.05, 0.060, 2.0, True, 20.5, 99.99),
            ('Q8', 'Upper', 3000.0, 200.0, 200.00, 200.10, 0.050, 2.0, True, 20.5, 200.00),
        ]
        for qp, zone, flow, actual, ref, dut, err, mpe, passed, temp, wt in results_data:
            TestResult.objects.create(
                test=cls.test, q_point=qp, target_flow_lph=flow,
                actual_flow_lph=actual, ref_volume_l=ref, dut_volume_l=dut,
                error_pct=err, mpe_pct=mpe, passed=passed, zone=zone,
                temperature_c=temp, weight_kg=wt,
            )


class TestErrorCurve(ReportTestBase):
    """Tests for reports/error_curve.py."""

    def test_returns_valid_png_bytes(self):
        summary = get_test_summary(self.test)
        result = generate_error_curve_image(summary)
        self.assertIsInstance(result, bytes)
        self.assertTrue(result.startswith(b'\x89PNG'), "Should produce valid PNG")
        self.assertGreater(len(result), 1000, "PNG should have substantial content")

    def test_handles_empty_q_points(self):
        """Error curve with no completed Q-points should still return PNG."""
        summary = get_test_summary(self.test)
        summary.q_points = []
        result = generate_error_curve_image(summary)
        self.assertTrue(result.startswith(b'\x89PNG'))

    def test_handles_partial_results(self):
        """Error curve with some null error_pct values."""
        summary = get_test_summary(self.test)
        summary.q_points[0].error_pct = None
        summary.q_points[0].passed = None
        result = generate_error_curve_image(summary)
        self.assertTrue(result.startswith(b'\x89PNG'))

    def test_custom_dimensions(self):
        summary = get_test_summary(self.test)
        result = generate_error_curve_image(summary, width=5.0, height=2.5, dpi=72)
        self.assertTrue(result.startswith(b'\x89PNG'))


class TestPDFGenerator(ReportTestBase):
    """Tests for reports/generator.py."""

    def test_returns_valid_pdf_bytes(self):
        result = generate_certificate_pdf(self.test)
        self.assertIsInstance(result, bytes)
        self.assertTrue(result.startswith(b'%PDF'), "Should produce valid PDF")
        self.assertGreater(len(result), 5000, "PDF should have substantial content")

    def test_pdf_with_certificate_number(self):
        generate_certificate_number(self.test)
        self.test.refresh_from_db()
        result = generate_certificate_pdf(self.test)
        self.assertTrue(result.startswith(b'%PDF'))

    def test_pdf_with_failed_test(self):
        self.test.overall_pass = False
        self.test.save()
        # Mark Q1 as failed
        r = self.test.results.get(q_point='Q1')
        r.error_pct = 6.5
        r.passed = False
        r.save()
        result = generate_certificate_pdf(self.test)
        self.assertTrue(result.startswith(b'%PDF'))


class TestSaveCertificate(ReportTestBase):
    """Tests for save_certificate()."""

    def test_saves_pdf_file_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=tmpdir):
                generate_certificate_number(self.test)
                self.test.refresh_from_db()
                rel_path = save_certificate(self.test)
                self.test.refresh_from_db()

                self.assertTrue(rel_path.startswith('certificates/'))
                self.assertEqual(self.test.certificate_pdf, rel_path)

                full_path = os.path.join(tmpdir, rel_path)
                self.assertTrue(os.path.isfile(full_path))

                with open(full_path, 'rb') as f:
                    self.assertTrue(f.read(4) == b'%PDF')


class TestDownloadCertificateView(ReportTestBase):
    """Tests for the download_certificate view."""

    def test_download_returns_404_without_certificate(self):
        self.client.login(username='tech', password='testpass')
        resp = self.client.get(f'/tests/{self.test.pk}/certificate/')
        self.assertEqual(resp.status_code, 404)

    def test_download_returns_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=tmpdir):
                generate_certificate_number(self.test)
                self.test.refresh_from_db()
                save_certificate(self.test)

                self.client.login(username='tech', password='testpass')
                resp = self.client.get(f'/tests/{self.test.pk}/certificate/')
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp['Content-Type'], 'application/pdf')
