from django.contrib import admin
from testing.models import ISO4064Standard, Test, TestResult


@admin.register(ISO4064Standard)
class ISO4064StandardAdmin(admin.ModelAdmin):
    list_display = ('meter_size', 'meter_class', 'q_point', 'flow_rate_lph',
                    'test_volume_l', 'duration_s', 'mpe_pct', 'zone')
    list_filter = ('meter_size', 'meter_class', 'zone')
    ordering = ('meter_size', 'meter_class', 'q_point')


class TestResultInline(admin.TabularInline):
    model = TestResult
    extra = 0
    readonly_fields = ('q_point',)


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('pk', 'meter', 'test_class', 'status', 'overall_pass',
                    'initiated_by', 'created_at')
    list_filter = ('status', 'test_class', 'approval_status', 'source')
    inlines = [TestResultInline]
