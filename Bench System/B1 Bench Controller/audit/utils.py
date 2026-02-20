"""Audit logging utility."""
import logging

from audit.models import AuditEntry

logger = logging.getLogger(__name__)


def log_audit(user, action, target_type='', target_id=None,
              description='', ip_address=None, metadata=None):
    """Create an audit log entry.

    Args:
        user: CustomUser instance or None for system actions.
        action: One of AuditEntry.ACTION_CHOICES values.
        target_type: Type of target (test, meter, user, certificate, settings).
        target_id: Primary key of the target object.
        description: Human-readable description.
        ip_address: Client IP address.
        metadata: Additional JSON-serializable data.
    """
    try:
        AuditEntry.objects.create(
            user=user if user and hasattr(user, 'pk') else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            ip_address=ip_address,
            metadata=metadata or {},
        )
    except Exception:
        logger.debug("Failed to create audit entry", exc_info=True)
