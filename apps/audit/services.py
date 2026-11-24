import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import FieldFile

from apps.common.utils import get_client_ip

from .models import AuditLog


def _json_safe(data):
    if data is None:
        return None
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def snapshot(instance, fields):
    """Serialisable dict of `fields` (FKs stored as their id)."""
    data = {}
    for name in fields:
        field = instance._meta.get_field(name)
        value = getattr(instance, field.attname)
        if isinstance(value, FieldFile):
            value = value.name or None
        data[name] = value
    return _json_safe(data)


def diff(old, new):
    """Return (old_changed, new_changed) containing only keys whose value changed."""
    old = old or {}
    new = new or {}
    keys = [k for k in new.keys() | old.keys() if old.get(k) != new.get(k)]
    return {k: old.get(k) for k in keys}, {k: new.get(k) for k in keys}


def log_activity(
    action,
    *,
    request=None,
    user=None,
    entity=None,
    entity_type="",
    entity_id="",
    description="",
    old_values=None,
    new_values=None,
):
    if user is None and request is not None:
        request_user = getattr(request, "user", None)
        if request_user is not None and request_user.is_authenticated:
            user = request_user
    if entity is not None:
        entity_type = entity_type or entity.__class__.__name__
        entity_id = entity_id or str(entity.pk)

    return AuditLog.objects.create(
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        description=description,
        old_values=_json_safe(old_values),
        new_values=_json_safe(new_values),
        ip_address=get_client_ip(request),
    )
