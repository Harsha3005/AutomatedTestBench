from django.conf import settings


def deployment_context(request):
    """Inject deployment-specific template variables."""
    deployment = getattr(settings, 'DEPLOYMENT_TYPE', 'lab')
    return {
        'DEPLOYMENT_TYPE': deployment,
        'base_template': f'base_{deployment}.html',
        'is_bench': deployment == 'bench',
        'is_lab': deployment == 'lab',
    }
