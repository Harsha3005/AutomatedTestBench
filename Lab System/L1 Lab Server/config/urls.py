from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('meters/', include('meters.urls')),
    path('tests/', include('testing.urls')),
    # Root redirects to test list (main workflow page)
    path('', lambda request: redirect('testing:test_list')),
]
