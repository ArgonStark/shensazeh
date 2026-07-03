"""Audit-trail helpers.

Every financial mutation must call log_action() so who/when/what
(before & after) is recorded in finance.AuditLog.
"""

import datetime

from django.contrib.contenttypes.models import ContentType
from django.db.models.fields.files import FieldFile

from .models import AuditLog


def _serialize(value):
    if isinstance(value, FieldFile):
        return value.name or ''
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    return str(value)


def model_snapshot(instance, fields=None):
    """Dict of {field_name: json-safe value} for the instance's concrete fields."""
    data = {}
    for field in instance._meta.concrete_fields:
        if fields is not None and field.name not in fields:
            continue
        data[field.name] = _serialize(field.value_from_object(instance))
    return data


def diff_snapshots(before, after):
    """Only the keys whose values differ: {name: {'before': x, 'after': y}}."""
    changed = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed[key] = {'before': before.get(key), 'after': after.get(key)}
    return changed


def log_action(actor, action, instance, before=None, after=None):
    """Record a mutation. Pass snapshots from model_snapshot() where relevant:

    - create: after only
    - update/status: before + after (stores just the diff)
    - delete: before only
    """
    if action in ('update', 'status') and before is not None and after is not None:
        changes = diff_snapshots(before, after)
    elif action == 'create':
        changes = {'after': after or model_snapshot(instance)}
    elif action == 'delete':
        changes = {'before': before or model_snapshot(instance)}
    else:
        changes = {'before': before, 'after': after}

    return AuditLog.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        object_repr=str(instance)[:200],
        changes=changes,
    )
