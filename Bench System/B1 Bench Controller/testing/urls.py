from django.urls import path

from testing import views

app_name = 'testing'

urlpatterns = [
    path('', views.test_list, name='test_list'),
    path('<int:pk>/', views.test_detail, name='test_detail'),
    path('create/', views.test_create, name='test_create'),
    path('<int:pk>/approve/', views.test_approve, name='test_approve'),
    path('<int:pk>/certificate/', views.download_certificate, name='download_certificate'),
    path('<int:pk>/status/', views.test_results_api, name='test_results_api'),
]
