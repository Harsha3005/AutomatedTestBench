from django.conf import settings
from django.db import models


class AuditEntry(models.Model):
    """Tracks user actions for compliance and debugging."""
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('abort', 'Abort'),
        ('export', 'Export'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_entries',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=30, blank=True)
    target_id = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Audit entries'

    def __str__(self):
        user_str = self.user.username if self.user else 'system'
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {user_str}: {self.action} {self.target_type}"
