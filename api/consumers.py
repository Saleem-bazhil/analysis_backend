"""
WebSocket consumers for real-time data synchronization.

Clients connect via: ws://<host>/ws/sync/?token=<jwt>

Events flow:
1. Client connects → joins "workspace" channel group
2. Any model change (via Django signals) → broadcast to group
3. Client can also push workspace state updates over WS
"""

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

# The single channel group all authenticated clients join
WORKSPACE_GROUP = 'workspace_sync'


class WorkspaceSyncConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles real-time workspace synchronization.

    Inbound messages (client → server):
        {
            "type": "workspace_update",
            "payload": { ...workspace state... }
        }

    Outbound messages (server → client):
        {
            "type": "workspace_updated",
            "payload": { ...workspace state... },
            "source": "username"
        }
        {
            "type": "record_changed",
            "action": "create" | "update" | "delete",
            "model": "CallPlanRecord" | "UploadedFile" | "WorkspaceState",
            "payload": { ...serialized data... },
            "source": "username"
        }
    """

    async def connect(self):
        self.user = self.scope.get('user', AnonymousUser())

        if isinstance(self.user, AnonymousUser) or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Join the workspace group
        await self.channel_layer.group_add(WORKSPACE_GROUP, self.channel_name)
        await self.accept()

        logger.info(f"WebSocket connected: {self.user.username}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(WORKSPACE_GROUP, self.channel_name)
        username = getattr(self.user, 'username', 'anonymous')
        logger.info(f"WebSocket disconnected: {username} (code={close_code})")

    async def receive_json(self, content, **kwargs):
        """Handle messages from the client."""
        msg_type = content.get('type')

        if msg_type == 'workspace_update':
            payload = content.get('payload', {})
            # Persist to DB
            await self._save_workspace(payload)
            # Broadcast to ALL clients (including sender for confirmation)
            await self.channel_layer.group_send(
                WORKSPACE_GROUP,
                {
                    'type': 'workspace.updated',
                    'payload': payload,
                    'source': self.user.username,
                },
            )

        elif msg_type == 'ping':
            await self.send_json({'type': 'pong'})

    # ── Group event handlers ──

    async def workspace_updated(self, event):
        """Relay workspace update to this client."""
        await self.send_json({
            'type': 'workspace_updated',
            'payload': event['payload'],
            'source': event.get('source', ''),
        })

    async def record_changed(self, event):
        """Relay model-change event to this client."""
        await self.send_json({
            'type': 'record_changed',
            'action': event['action'],
            'model': event['model'],
            'payload': event.get('payload', {}),
            'source': event.get('source', ''),
        })

    # ── DB helpers ──

    @database_sync_to_async
    def _save_workspace(self, state):
        from .models import WorkspaceState
        obj = WorkspaceState.objects.first()
        if obj:
            if not isinstance(obj.state, dict):
                obj.state = {}
            obj.state.update(state)
            obj.save()
        else:
            WorkspaceState.objects.create(state=state)
