"""
ASGI config for the Water Meter Test Bench.

On bench side (settings_bench), uses Django Channels for WebSocket support.
On lab side (settings_lab), standard ASGI (no WebSocket needed).
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_bench')
django.setup()

from django.core.asgi import get_asgi_application

django_asgi = get_asgi_application()

try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from bench_ui.routing import websocket_urlpatterns

    application = ProtocolTypeRouter({
        'http': django_asgi,
        'websocket': AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns),
        ),
    })
except ImportError:
    # channels not installed (lab side) — fall back to plain ASGI
    application = django_asgi
