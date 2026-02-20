import django
from django.conf import settings


def deployment_context(request):
    """Inject deployment-specific template variables."""
    deployment = getattr(settings, 'DEPLOYMENT_TYPE', 'bench')
    ctx = {
        'DEPLOYMENT_TYPE': deployment,
        'base_template': f'base_{deployment}.html',
        'is_bench': deployment == 'bench',
        'is_lab': deployment == 'lab',
    }

    if deployment == 'bench':
        try:
            from testing.models import Test
            ctx['bench_has_active_test'] = Test.objects.filter(
                status__in=['running', 'queued', 'acknowledged']
            ).exists()
        except Exception:
            ctx['bench_has_active_test'] = False

        try:
            from bench_ui.models import BenchSettings
            ctx['bench_settings'] = BenchSettings.load()
        except Exception:
            ctx['bench_settings'] = None

        ctx['django_version'] = django.get_version()

    return ctx
