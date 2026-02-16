from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('developer', 'Engineer'),
        ('manager', 'Faculty / Manager'),
        ('bench_tech', 'Bench Technician'),
        ('lab_tech', 'Lab Technician'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='lab_tech')
    full_name = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_bench_tech(self):
        return self.role == 'bench_tech'

    @property
    def is_developer(self):
        return self.role == 'developer'

    @property
    def is_lab_tech(self):
        return self.role == 'lab_tech'

    @property
    def can_actuate(self):
        """Can this user manually control field devices?"""
        return self.role in ('admin', 'developer', 'bench_tech')

    @property
    def can_configure_devices(self):
        """Can this user modify device group assignments?"""
        return self.role in ('admin', 'developer')
