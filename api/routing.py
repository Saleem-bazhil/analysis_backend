"""WebSocket URL routing."""

from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/sync/', consumers.WorkspaceSyncConsumer.as_asgi()),
]
