from django.db import models


class DeviceGroup(models.Model):
    """Configurable grouping for field devices (e.g., Main Line, Return Line)."""
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200, blank=True)
    color = models.CharField(max_length=7, default='#4CAF50')
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class FieldDevice(models.Model):
    """Registered field device (sensor, actuator, indicator) on the test bench."""
    CATEGORY_CHOICES = [
        ('valve', 'Valve'),
        ('sensor_pressure', 'Pressure Sensor'),
        ('sensor_temperature', 'Temperature Sensor'),
        ('sensor_flow', 'Flow Sensor'),
        ('sensor_level', 'Level Sensor'),
        ('sensor_weight', 'Weight Sensor'),
        ('sensor_humidity', 'Humidity Sensor'),
        ('sensor_environmental', 'Environmental Sensor'),
        ('pump', 'Pump / VFD'),
        ('indicator', 'Indicator'),
        ('communication', 'Communication'),
        ('meter', 'Meter Under Test'),
    ]
    device_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    group = models.ForeignKey(
        DeviceGroup, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devices',
    )
    unit = models.CharField(max_length=20, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'device_id']

    def __str__(self):
        return f"{self.device_id} — {self.name}"
