# Generated manually — IIITB Test Bench real hardware topology

from django.db import migrations


def update_topology(apps, schema_editor):
    DeviceGroup = apps.get_model('controller', 'DeviceGroup')
    FieldDevice = apps.get_model('controller', 'FieldDevice')

    # Wipe old seed
    FieldDevice.objects.all().delete()
    DeviceGroup.objects.all().delete()

    # --- Groups ---
    groups = {}
    group_data = [
        ('Reservoir', 'Water supply tank — level & temperature', '#2196F3', 1),
        ('Pump & Drive', 'Multistage pump + VFD', '#9C27B0', 2),
        ('Main Line', 'Primary measurement path: SV1 → PT-01 → DUT → PT-02 → FT-01', '#4CAF50', 3),
        ('Test Lanes', '3 lanes (1", 3/4", 1/2") with ball valves + rotameters', '#FF9800', 4),
        ('Collection', 'Collection tank on weighing scale + drain', '#00BCD4', 5),
        ('Bypass', 'Bypass line — flow rate control', '#FF5722', 6),
        ('Environment', 'Atmospheric temperature, humidity, barometric pressure', '#607D8B', 7),
        ('Indicators', 'Tower light, MCB, contactor', '#F44336', 8),
        ('Communications', 'LoRa, Modbus buses', '#795548', 9),
    ]
    for name, desc, color, order in group_data:
        g = DeviceGroup.objects.create(
            name=name, description=desc, color=color, display_order=order,
        )
        groups[name] = g

    # --- Devices ---
    # (device_id, name, category, group, unit, min, max, order)
    devices = [
        # Reservoir
        ('RES-LVL', 'Reservoir Level (Ultrasonic)', 'sensor_level', 'Reservoir', '%', 0, 100, 1),
        ('RES-TEMP', 'Reservoir Water Temp (Submersible)', 'sensor_temperature', 'Reservoir', '°C', 0, 50, 2),
        # Pump & Drive
        ('P-01', 'Multistage Vertical Pump + VFD', 'pump', 'Pump & Drive', 'Hz', 0, 50, 1),
        # Main Line (in flow order)
        ('SV1', 'Solenoid Valve — Inlet', 'valve', 'Main Line', '', None, None, 1),
        ('PT-01', 'Pressure Transmitter — Upstream', 'sensor_pressure', 'Main Line', 'bar', 0, 10, 2),
        ('DUT', 'Meter Under Test', 'meter', 'Main Line', '', None, None, 3),
        ('PT-02', 'Pressure Transmitter — Downstream', 'sensor_pressure', 'Main Line', 'bar', 0, 10, 4),
        ('FT-01', 'Electromagnetic Flow Meter — Reference', 'sensor_flow', 'Main Line', 'L/h', 0, 2500, 5),
        # Test Lanes
        ('BV-L1', 'Ball Valve — Lane 1 (1")', 'valve', 'Test Lanes', '', None, None, 1),
        ('BV-L2', 'Ball Valve — Lane 2 (3/4")', 'valve', 'Test Lanes', '', None, None, 2),
        ('BV-L3', 'Ball Valve — Lane 3 (1/2")', 'valve', 'Test Lanes', '', None, None, 3),
        # Collection
        ('WT-01', 'Weighing Scale', 'sensor_weight', 'Collection', 'kg', 0, 200, 1),
        ('SV-DRN', 'Solenoid Valve — Drain', 'valve', 'Collection', '', None, None, 2),
        # Bypass
        ('BV-BP', 'Ball Valve — Bypass', 'valve', 'Bypass', '', None, None, 1),
        # Environment
        ('ATM-TEMP', 'Atmospheric Temperature', 'sensor_environmental', 'Environment', '°C', -10, 60, 1),
        ('ATM-HUM', 'Atmospheric Humidity', 'sensor_humidity', 'Environment', '%', 0, 100, 2),
        ('ATM-BARO', 'Barometric Pressure', 'sensor_environmental', 'Environment', 'hPa', 900, 1100, 3),
        # Indicators
        ('TOWER', 'Tower Light', 'indicator', 'Indicators', '', None, None, 1),
        ('MCB', 'Main Circuit Breaker (4P)', 'indicator', 'Indicators', '', None, None, 2),
        ('CONT', 'Contactor', 'indicator', 'Indicators', '', None, None, 3),
        # Communications
        ('LORA', 'LoRa Link (SX1262)', 'communication', 'Communications', '', None, None, 1),
        ('BUS1', 'Modbus Bus 1 — Sensors', 'communication', 'Communications', '', None, None, 2),
        ('BUS2', 'Modbus Bus 2 — VFD', 'communication', 'Communications', '', None, None, 3),
    ]
    for dev_id, name, cat, grp_name, unit, mn, mx, order in devices:
        FieldDevice.objects.create(
            device_id=dev_id, name=name, category=cat,
            group=groups[grp_name], unit=unit,
            min_value=mn, max_value=mx,
            display_order=order,
        )


def revert(apps, schema_editor):
    """Revert to 0002 seed by wiping and letting 0002 re-seed on reverse migrate."""
    apps.get_model('controller', 'FieldDevice').objects.all().delete()
    apps.get_model('controller', 'DeviceGroup').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('controller', '0002_seed_default_devices'),
    ]

    operations = [
        migrations.RunPython(update_topology, revert),
    ]
