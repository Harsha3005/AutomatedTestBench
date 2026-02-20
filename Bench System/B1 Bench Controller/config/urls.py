from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('meters/', include('meters.urls')),
    path('tests/', include('testing.urls')),
    # lab_ui is always in INSTALLED_APPS (shared) — include unconditionally
    path('lab/', include('lab_ui.urls')),
]

_deployment = getattr(settings, 'DEPLOYMENT_TYPE', '')

# bench_ui + controller are only in bench INSTALLED_APPS
if _deployment == 'bench':
    urlpatterns += [
        path('bench/', include('bench_ui.urls')),
        path('system/', include('controller.urls')),
        path('', lambda request: redirect('bench_ui:dashboard')),
    ]
elif _deployment == 'lab':
    urlpatterns += [
        path('', lambda request: redirect('lab_ui:dashboard')),
    ]
else:
    urlpatterns += [
        path('', lambda request: redirect('testing:test_list')),
    ]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
