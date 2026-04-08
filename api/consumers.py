"""
WebSocket consumers for real-time data synchronization.

Clients connect via: ws://<host>/ws/sync/?token=<jwt>&session_id=<id>

Events flow:
1. Client connects -> joins workspace group, presence broadcast
2. Any model change (via Django signals) -> broadcast to group
3. Client can push workspace state updates and activity events over WS
"""

import json
import logging
import time

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

WORKSPACE_GROUP = 'workspace_sync'
PRESENCE_CACHE_KEY = 'ws:presence'
PRESENCE_TTL = 60  # seconds — auto-expire stale entries


class WorkspaceSyncConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles real-time workspace synchronization with presence tracking.
    Presence is stored in Redis (via cache) so it survives restarts.
    """

    async def connect(self):
        self.user = self.scope.get('user', AnonymousUser())

        if isinstance(self.user, AnonymousUser) or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Extract session_id from query string
        qs = parse_qs(self.scope.get('query_string', b'').decode())
        self.session_id = (qs.get('session_id') or [''])[0]

        # Join workspace group
        await self.channel_layer.group_add(WORKSPACE_GROUP, self.channel_name)
        await self.accept()

        # Register presence
        await self._set_presence('viewing')

        logger.info(f"WS connected: {self.user.username} (session={self.session_id})")

        # Broadcast updated presence to all clients
        await self._broadcast_presence()

    async def disconnect(self, close_code):
        # Remove presence
        await self._remove_presence()

        await self.channel_layer.group_discard(WORKSPACE_GROUP, self.channel_name)

        username = getattr(self.user, 'username', 'anonymous')
        logger.info(f"WS disconnected: {username} (code={close_code})")

        # Broadcast updated presence
        await self._broadcast_presence()

    async def receive_json(self, content, **kwargs):
        """Handle messages from the client."""
        msg_type = content.get('type')
        session_id = content.get('session_id', self.session_id)

        if msg_type == 'workspace_update':
            payload = content.get('payload', {})
            await self._save_workspace(payload)
            await self.channel_layer.group_send(
                WORKSPACE_GROUP,
                {
                    'type': 'workspace.updated',
                    'payload': payload,
                    'source': self.user.username,
                    'session_id': session_id,
                },
            )

        elif msg_type == 'user_activity':
            payload = content.get('payload', {})
            # Update presence action
            await self._set_presence(payload.get('action', 'viewing'))

            await self.channel_layer.group_send(
                WORKSPACE_GROUP,
                {
                    'type': 'user.activity',
                    'payload': payload,
                    'source': self.user.username,
                    'session_id': session_id,
                },
            )

        elif msg_type == 'ping':
            # Refresh presence TTL on heartbeat
            await self._set_presence()
            await self.send_json({'type': 'pong'})

    # ── Group event handlers ──

    async def workspace_updated(self, event):
        await self.send_json({
            'type': 'workspace_updated',
            'payload': event['payload'],
            'source': event.get('source', ''),
            'session_id': event.get('session_id', ''),
        })

    async def record_changed(self, event):
        await self.send_json({
            'type': 'record_changed',
            'action': event['action'],
            'model': event['model'],
            'payload': event.get('payload', {}),
            'source': event.get('source', ''),
        })

    async def user_activity(self, event):
        await self.send_json({
            'type': 'user_activity',
            'payload': event['payload'],
            'source': event.get('source', ''),
            'session_id': event.get('session_id', ''),
        })

    async def presence_broadcast(self, event):
        await self.send_json({
            'type': 'presence_update',
            'payload': event['payload'],
        })

    # ── Presence via Channel Layer (Redis-backed) ──

    async def _set_presence(self, action=None):
        """Store this session's presence. Uses channel layer's Redis if available."""
        try:
            presence = await self._get_all_presence()
            entry = presence.get(self.session_id, {})
            presence[self.session_id] = {
                'username': self.user.username,
                'session_id': self.session_id,
                'action': action or entry.get('action', 'viewing'),
                'ts': time.time(),
            }
            # Prune stale entries (older than TTL)
            cutoff = time.time() - PRESENCE_TTL
            presence = {k: v for k, v in presence.items() if v.get('ts', 0) > cutoff}
            await self._store_presence(presence)
        except Exception as e:
            logger.warning(f"Presence set failed: {e}")

    async def _remove_presence(self):
        """Remove this session from presence."""
        try:
            presence = await self._get_all_presence()
            presence.pop(self.session_id, None)
            await self._store_presence(presence)
        except Exception as e:
            logger.warning(f"Presence remove failed: {e}")

    async def _get_all_presence(self) -> dict:
        """Read presence dict from Redis via channel layer."""
        try:
            # Use channel layer's Redis connection directly if available
            redis_url = getattr(settings, 'REDIS_URL', '')
            if redis_url:
                return await self._redis_get_presence()
            else:
                # Fallback: in-memory on the consumer class
                if not hasattr(WorkspaceSyncConsumer, '_mem_presence'):
                    WorkspaceSyncConsumer._mem_presence = {}
                return WorkspaceSyncConsumer._mem_presence
        except Exception:
            return {}

    async def _store_presence(self, data: dict):
        redis_url = getattr(settings, 'REDIS_URL', '')
        if redis_url:
            await self._redis_set_presence(data)
        else:
            WorkspaceSyncConsumer._mem_presence = data

    @database_sync_to_async
    def _redis_get_presence(self):
        """Sync Redis read (wrapped for async)."""
        from django.core.cache import cache
        return cache.get(PRESENCE_CACHE_KEY) or {}

    @database_sync_to_async
    def _redis_set_presence(self, data):
        """Sync Redis write (wrapped for async)."""
        from django.core.cache import cache
        cache.set(PRESENCE_CACHE_KEY, data, PRESENCE_TTL)

    async def _broadcast_presence(self):
        """Send the current connected-users list to all clients."""
        try:
            presence = await self._get_all_presence()
            users = [
                {
                    'username': info['username'],
                    'session_id': info['session_id'],
                    'action': info.get('action', 'viewing'),
                }
                for info in presence.values()
            ]
            await self.channel_layer.group_send(
                WORKSPACE_GROUP,
                {
                    'type': 'presence.broadcast',
                    'payload': {'users': users},
                },
            )
        except Exception as e:
            logger.warning(f"Presence broadcast failed: {e}")

    @database_sync_to_async
    def _save_workspace(self, state):
        from .models import WorkspaceState
        obj = WorkspaceState.objects.first()
        if obj:
            new_state = dict(obj.state) if isinstance(obj.state, dict) else {}
            new_state.update(state)
            obj.state = new_state
            obj.save()
        else:
            WorkspaceState.objects.create(state=state)
