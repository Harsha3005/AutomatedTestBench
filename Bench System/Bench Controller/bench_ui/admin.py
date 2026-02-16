from django.contrib import admin

from bench_ui.models import BenchSettings, SensorReading, DUTManualEntry


@admin.register(BenchSettings)
class BenchSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'theme', 'auto_lock_timeout', 'buzzer_enabled')

    def has_add_permission(self, request):
        return not BenchSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ('test', 'timestamp', 'q_point', 'trigger', 'flow_rate_lph', 'weight_kg')
    list_filter = ('trigger', 'q_point', 'diverter')
    readonly_fields = ('test', 'timestamp', 'q_point', 'trigger', 'event_label',
                       'flow_rate_lph', 'em_totalizer_l', 'weight_kg',
                       'pressure_upstream_bar', 'pressure_downstream_bar',
                       'water_temp_c', 'vfd_freq_hz', 'vfd_current_a',
                       'dut_totalizer_l', 'diverter', 'active_lane')


@admin.register(DUTManualEntry)
class DUTManualEntryAdmin(admin.ModelAdmin):
    list_display = ('test', 'q_point', 'before_value_l', 'after_value_l', 'volume_l')
    list_filter = ('q_point',)
    readonly_fields = ('volume_l', 'created_at')
