from django.urls import path

from meters import views

app_name = 'meters'

urlpatterns = [
    path('', views.meter_list, name='meter_list'),
    path('<int:pk>/', views.meter_detail, name='meter_detail'),
    path('create/', views.meter_create, name='meter_create'),
    path('<int:pk>/edit/', views.meter_edit, name='meter_edit'),
]
