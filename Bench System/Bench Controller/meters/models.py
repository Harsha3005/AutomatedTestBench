from django.conf import settings
from django.db import models


class TestMeter(models.Model):
    SIZE_CHOICES = [('DN15', 'DN15'), ('DN20', 'DN20'), ('DN25', 'DN25')]
    CLASS_CHOICES = [
        ('A', 'Class A'),
        ('B', 'Class B'),
        ('C', 'Class C'),
        ('R80', 'R80'),
        ('R100', 'R100'),
        ('R160', 'R160'),
        ('R200', 'R200'),
    ]
    TYPE_CHOICES = [
        ('mechanical', 'Mechanical'),
        ('ultrasonic', 'Ultrasonic'),
        ('electromagnetic', 'Electromagnetic'),
    ]
    DUT_MODE_CHOICES = [
        ('rs485', 'RS485 Modbus'),
        ('manual', 'Manual Entry'),
    ]

    serial_number = models.CharField(max_length=50, unique=True)
    meter_size = models.CharField(max_length=10, choices=SIZE_CHOICES)
    meter_class = models.CharField(max_length=10, choices=CLASS_CHOICES, default='B')
    manufacturer = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    meter_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    dut_mode = models.CharField(max_length=10, choices=DUT_MODE_CHOICES, default='manual')
    modbus_address = models.IntegerField(default=20)
    modbus_baud = models.IntegerField(default=9600)
    register_totalizer = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.serial_number} ({self.meter_size})"

    @property
    def test_count(self):
        return self.test_set.count()

    @property
    def last_tested(self):
        last = self.test_set.filter(status='completed').order_by('-completed_at').first()
        return last.completed_at if last else None
