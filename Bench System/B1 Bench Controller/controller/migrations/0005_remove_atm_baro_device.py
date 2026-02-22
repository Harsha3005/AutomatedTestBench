"""Remove ATM-BARO device - barometric pressure not needed for ISO 4064."""

from django.db import migrations


def remove_atm_baro(apps, schema_editor):
    FieldDevice = apps.get_model('controller', 'FieldDevice')
    FieldDevice.objects.filter(device_id='ATM-BARO').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('controller', '0004_add_scale_power_device'),
    ]

    operations = [
        migrations.RunPython(remove_atm_baro, migrations.RunPython.noop),
    ]
