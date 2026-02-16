from django.test import TestCase

from accounts.models import CustomUser
from audit.models import AuditEntry
from audit.utils import log_audit


class AuditUtilsTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='auditor', password='test123', role='admin',
        )

    def test_log_audit_creates_entry(self):
        log_audit(self.user, 'login', description='User logged in')
        self.assertEqual(AuditEntry.objects.count(), 1)
        entry = AuditEntry.objects.first()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, 'login')
        self.assertEqual(entry.description, 'User logged in')

    def test_log_audit_without_user(self):
        log_audit(None, 'create', 'test', 42, 'System created test')
        entry = AuditEntry.objects.first()
        self.assertIsNone(entry.user)
        self.assertEqual(entry.target_type, 'test')
        self.assertEqual(entry.target_id, 42)

    def test_audit_entry_str(self):
        log_audit(self.user, 'approve', 'test')
        entry = AuditEntry.objects.first()
        self.assertIn('auditor', str(entry))
        self.assertIn('approve', str(entry))

    def test_log_audit_with_metadata(self):
        log_audit(self.user, 'export', metadata={'format': 'csv', 'count': 100})
        entry = AuditEntry.objects.first()
        self.assertEqual(entry.metadata['format'], 'csv')
        self.assertEqual(entry.metadata['count'], 100)

    def test_log_audit_with_ip(self):
        log_audit(self.user, 'login', ip_address='192.168.1.100')
        entry = AuditEntry.objects.first()
        self.assertEqual(entry.ip_address, '192.168.1.100')
