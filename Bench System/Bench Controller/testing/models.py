from django.conf import settings
from django.db import models

# Shared class choices — used by ISO4064Standard, Test, and referenced by TestMeter
TEST_CLASS_CHOICES = [
    ('A', 'Class A'),
    ('B', 'Class B'),
    ('C', 'Class C'),
    ('R80', 'R80'),
    ('R100', 'R100'),
    ('R160', 'R160'),
    ('R200', 'R200'),
]


class ISO4064Standard(models.Model):
    """ISO 4064 Q-point parameters for each meter size and class."""
    meter_size = models.CharField(max_length=10)
    meter_class = models.CharField(max_length=10, choices=TEST_CLASS_CHOICES)
    q_point = models.CharField(max_length=5)  # Q1-Q8
    flow_rate_lph = models.FloatField()        # Target flow rate (L/h)
    test_volume_l = models.FloatField()        # Target collection volume (L)
    duration_s = models.IntegerField()         # Estimated duration (seconds)
    mpe_pct = models.FloatField()              # Max Permissible Error %
    zone = models.CharField(max_length=10)     # Lower / Upper

    class Meta:
        unique_together = ('meter_size', 'meter_class', 'q_point')
        ordering = ['meter_size', 'meter_class', 'q_point']

    def __str__(self):
        return f"{self.meter_size} {self.meter_class} {self.q_point} ({self.flow_rate_lph} L/h)"


class Test(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('acknowledged', 'Acknowledged'),
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted'),
    ]
    APPROVAL_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    SOURCE_CHOICES = [
        ('bench', 'Bench'),
        ('lab', 'Lab'),
    ]

    meter = models.ForeignKey('meters.TestMeter', on_delete=models.CASCADE)
    test_class = models.CharField(
        max_length=10, choices=TEST_CLASS_CHOICES, default='B',
        help_text='Metrological class this test was run against',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='pending')
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='initiated_tests'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_tests'
    )
    approval_comment = models.TextField(blank=True)
    overall_pass = models.BooleanField(null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    certificate_number = models.CharField(max_length=50, blank=True)
    certificate_pdf = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='bench')
    current_q_point = models.CharField(max_length=5, blank=True)
    current_state = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Test #{self.pk} - {self.meter.serial_number} ({self.get_status_display()})"

    @property
    def passed_count(self):
        return self.results.filter(passed=True).count()

    @property
    def failed_count(self):
        return self.results.filter(passed=False).count()

    @property
    def total_points(self):
        return self.results.count()


class TestResult(models.Model):
    """Result for a single Q-point within a test."""
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='results')
    q_point = models.CharField(max_length=5)
    target_flow_lph = models.FloatField()
    actual_flow_lph = models.FloatField(null=True, blank=True)
    ref_volume_l = models.FloatField(null=True, blank=True)
    dut_volume_l = models.FloatField(null=True, blank=True)
    error_pct = models.FloatField(null=True, blank=True)
    mpe_pct = models.FloatField()
    passed = models.BooleanField(null=True)
    pressure_up_bar = models.FloatField(null=True, blank=True)
    pressure_dn_bar = models.FloatField(null=True, blank=True)
    temperature_c = models.FloatField(null=True, blank=True)
    duration_s = models.IntegerField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    zone = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ('test', 'q_point')
        ordering = ['q_point']

    def __str__(self):
        status = "PASS" if self.passed else ("FAIL" if self.passed is False else "PENDING")
        return f"{self.q_point}: {status} ({self.error_pct}%)" if self.error_pct else f"{self.q_point}: {status}"
