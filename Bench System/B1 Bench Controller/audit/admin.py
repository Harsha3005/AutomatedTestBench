from django.contrib import admin

from audit.models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'target_type', 'target_id', 'description')
    list_filter = ('action', 'target_type', 'timestamp')
    search_fields = ('description', 'user__username')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)
