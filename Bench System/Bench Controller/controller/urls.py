from django.urls import path
from controller import views

app_name = 'controller'

urlpatterns = [
    path('config/', views.device_config, name='device_config'),
    path('config/save/', views.device_config_save, name='device_config_save'),
    path('config/group/save/', views.group_save, name='group_save'),
    path('config/group/<int:group_id>/delete/', views.group_delete, name='group_delete'),
    path('config/device/save/', views.device_save, name='device_save'),
    path('config/device/<int:pk>/delete/', views.device_delete, name='device_delete'),
    path('config/device/<int:pk>/toggle/', views.device_toggle_active, name='device_toggle_active'),
]
