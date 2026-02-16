"""WebSocket URL routing for bench_ui."""

from django.urls import path

from bench_ui.consumers import TestConsumer

websocket_urlpatterns = [
    path('ws/test/<int:test_id>/', TestConsumer.as_asgi()),
]
