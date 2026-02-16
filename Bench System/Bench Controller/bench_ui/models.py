from django.conf import settings
from django.db import models


class BenchSettings(models.Model):
    """Singleton model for persisting bench HMI preferences."""

    THEME_CHOICES = [
        ('dark', 'Dark'),
        ('light', 'Light'),
    ]
    DATETIME_FORMAT_CHOICES = [
        ('24h', '24-hour (14:30:00)'),
        ('12h', '12-hour (2:30 PM)'),
    ]

    theme = models.CharField(
        max_length=10, choices=THEME_CHOICES, default='dark',
    )
    auto_lock_timeout = models.PositiveIntegerField(
        default=300,
        help_text='Auto-lock timeout in seconds (0 = disabled)',
    )
    buzzer_enabled = models.BooleanField(default=True)
    datetime_format = models.CharField(
        max_length=10, choices=DATETIME_FORMAT_CHOICES, default='24h',
    )
    display_brightness = models.PositiveIntegerField(
        default=100,
        help_text='Display brightness 0-100 (placeholder for HW integration)',
    )
    bench_id = models.CharField(max_length=50, default='IIITB-BENCH-001', blank=True)
    software_version = models.CharField(max_length=20, default='1.0.0', editable=False)

    class Meta:
        verbose_name = 'Bench Settings'
        verbose_name_plural = 'Bench Settings'

    def __str__(self):
        return 'Bench Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ---------------------------------------------------------------------------
#  SensorReading — time-series sensor data during test execution
# ---------------------------------------------------------------------------

class SensorReading(models.Model):
    """Time-series sensor snapshot recorded during a test (~1-2s interval)."""

    TRIGGER_CHOICES = [
        ('periodic', 'Periodic'),
        ('event', 'Event'),
    ]

    test = models.ForeignKey(
        'testing.Test', on_delete=models.CASCADE, related_name='sensor_readings',
    )
    timestamp = models.DateTimeField()
    q_point = models.CharField(max_length=5, blank=True)
    trigger = models.CharField(max_length=10, choices=TRIGGER_CHOICES, default='periodic')
    event_label = models.CharField(max_length=50, blank=True)

    # Flow
    flow_rate_lph = models.FloatField(default=0.0)
    em_totalizer_l = models.FloatField(default=0.0)

    # Scale
    weight_kg = models.FloatField(default=0.0)

    # Pressure
    pressure_upstream_bar = models.FloatField(default=0.0)
    pressure_downstream_bar = models.FloatField(default=0.0)

    # Temperature
    water_temp_c = models.FloatField(default=0.0)

    # VFD
    vfd_freq_hz = models.FloatField(default=0.0)
    vfd_current_a = models.FloatField(default=0.0)

    # DUT
    dut_totalizer_l = models.FloatField(null=True, blank=True)

    # State context
    diverter = models.CharField(max_length=10, default='BYPASS')
    active_lane = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['test', 'timestamp']),
            models.Index(fields=['test', 'q_point']),
        ]

    def __str__(self):
        label = f"Q{self.q_point}" if self.q_point else "---"
        return f"SensorReading {label} @ {self.timestamp:%H:%M:%S}"


# ---------------------------------------------------------------------------
#  DUTManualEntry — audit trail for operator-entered DUT readings
# ---------------------------------------------------------------------------

class DUTManualEntry(models.Model):
    """Audit trail for manually entered DUT totalizer readings."""

    test = models.ForeignKey(
        'testing.Test', on_delete=models.CASCADE, related_name='manual_entries',
    )
    q_point = models.CharField(max_length=5)

    # Before reading
    before_value_l = models.FloatField()
    before_entered_at = models.DateTimeField()
    before_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    # After reading (filled later)
    after_value_l = models.FloatField(null=True, blank=True)
    after_entered_at = models.DateTimeField(null=True, blank=True)
    after_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    # Computed
    volume_l = models.FloatField(null=True, blank=True)

    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('test', 'q_point')
        ordering = ['q_point']
        verbose_name = 'DUT Manual Entry'
        verbose_name_plural = 'DUT Manual Entries'

    def __str__(self):
        vol = f"{self.volume_l:.3f} L" if self.volume_l is not None else "pending"
        return f"DUT {self.q_point}: {vol}"

    def save(self, *args, **kwargs):
        # Auto-calculate volume when both readings present
        if self.before_value_l is not None and self.after_value_l is not None:
            self.volume_l = round(self.after_value_l - self.before_value_l, 4)
        super().save(*args, **kwargs)
