"""
Django signals that broadcast model changes over WebSocket.

When any tracked model is created/updated/deleted, we push an event
through the Channels layer so all connected clients receive it instantly.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .consumers import WORKSPACE_GROUP

logger = logging.getLogger(__name__)


def _broadcast(action, model_name, payload, source='system'):
    """Send a record_changed event to the workspace group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            WORKSPACE_GROUP,
            {
                'type': 'record.changed',
                'action': action,
                'model': model_name,
                'payload': payload,
                'source': source,
            },
        )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")


def _serialize_workspace(instance):
    return {
        'id': instance.pk,
        'updated_at': str(instance.updated_at),
        'state': instance.state,
    }


def _serialize_uploaded_file(instance):
    return {
        'id': instance.pk,
        'file_type': instance.file_type,
        'original_name': instance.original_name,
        'uploaded_by': instance.uploaded_by,
        'uploaded_at': str(instance.uploaded_at),
        'city': instance.city,
        'report_date': str(instance.report_date) if instance.report_date else None,
        'file_size': instance.file_size,
        'row_count': instance.row_count,
    }


def _serialize_record(instance):
    return {
        'id': instance.pk,
        'ticket_no': instance.ticket_no,
        'classification': instance.classification,
        'engineer': instance.engineer,
        'morning_status': instance.morning_status,
        'evening_status': instance.evening_status,
        'location': instance.location,
        'parts': instance.parts,
        'current_status_tat': instance.current_status_tat,
    }


# ── WorkspaceState signals ──

@receiver(post_save, sender='api.WorkspaceState')
def workspace_saved(sender, instance, created, **kwargs):
    action = 'create' if created else 'update'
    _broadcast(action, 'WorkspaceState', _serialize_workspace(instance))


# ── UploadedFile signals ──

@receiver(post_save, sender='api.UploadedFile')
def uploaded_file_saved(sender, instance, created, **kwargs):
    action = 'create' if created else 'update'
    _broadcast(action, 'UploadedFile', _serialize_uploaded_file(instance))


@receiver(post_delete, sender='api.UploadedFile')
def uploaded_file_deleted(sender, instance, **kwargs):
    _broadcast('delete', 'UploadedFile', {'id': instance.pk})


# ── CallPlanRecord signals ──

@receiver(post_save, sender='api.CallPlanRecord')
def record_saved(sender, instance, created, **kwargs):
    action = 'create' if created else 'update'
    _broadcast(action, 'CallPlanRecord', _serialize_record(instance))


@receiver(post_delete, sender='api.CallPlanRecord')
def record_deleted(sender, instance, **kwargs):
    _broadcast('delete', 'CallPlanRecord', {'id': instance.pk})
