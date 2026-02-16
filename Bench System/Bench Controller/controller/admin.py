from django.contrib import admin
from .models import DeviceGroup, FieldDevice


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'display_order')
    ordering = ('display_order',)


@admin.register(FieldDevice)
class FieldDeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'name', 'category', 'group', 'unit', 'is_active')
    list_filter = ('category', 'group', 'is_active')
    ordering = ('display_order', 'device_id')
