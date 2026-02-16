from django.urls import path
from bench_ui import views

app_name = 'bench_ui'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('test-control/', views.test_control, name='test_control'),
    path('test-wizard/', views.test_wizard, name='test_wizard'),
    path('results/<int:test_id>/', views.test_results, name='test_results'),
    path('history/', views.test_history, name='test_history'),
    path('setup/', views.setup_page, name='setup'),
    path('test-control/<int:test_id>/', views.test_control_live, name='test_control_live'),
    path('lock/', views.lock_screen, name='lock_screen'),
    path('unlock/', views.unlock, name='unlock'),
    # System diagnostics tab
    path('system/', views.system_status, name='system_status'),
    path('system/api/status/', views.system_api_status, name='system_api_status'),
    path('system/api/command/', views.system_api_command, name='system_api_command'),
    # Emergency Stop
    path('emergency-stop/', views.emergency_stop, name='emergency_stop'),
    # Settings
    path('settings/', views.settings_page, name='settings'),
    path('settings/save/', views.settings_general_save, name='settings_general_save'),
    # Test Execution API (T-402)
    path('api/test/start/<int:test_id>/', views.api_test_start, name='api_test_start'),
    path('api/test/abort/', views.api_test_abort, name='api_test_abort'),
    path('api/test/status/', views.api_test_status, name='api_test_status'),
    path('api/test/dut-prompt/', views.api_dut_prompt, name='api_dut_prompt'),
    path('api/test/dut-submit/', views.api_dut_submit, name='api_dut_submit'),
]
