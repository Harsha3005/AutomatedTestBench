from django.urls import path

from lab_ui import views

app_name = 'lab_ui'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/lora-status/', views.lora_status_api, name='lora_status_api'),
    path('api/lora-history/', views.lora_history_api, name='lora_history_api'),
    path('monitor/<int:test_id>/', views.live_monitor, name='live_monitor'),
    path('monitor/data/<int:test_id>/', views.monitor_data_api, name='monitor_data'),
    path('test/new/', views.test_wizard, name='test_wizard'),
    path('certificates/', views.certificates, name='certificates'),
    path('settings/', views.lab_settings, name='settings'),
    path('audit/', views.audit_log, name='audit_log'),
    path('audit/export/', views.audit_export, name='audit_export'),
    path('tests/export/', views.test_export_csv, name='test_export_csv'),
]
