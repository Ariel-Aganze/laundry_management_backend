import django_filters
from rest_framework import serializers, viewsets

from apps.common.permissions import IsAdmin

from .models import AuditAction, AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default=None)
    user_role = serializers.CharField(source="user.role", read_only=True, default=None)
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_name",
            "user_role",
            "action",
            "action_label",
            "entity_type",
            "entity_id",
            "description",
            "old_values",
            "new_values",
            "ip_address",
            "created_at",
        ]


class AuditLogFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter(field_name="user_id")
    action = django_filters.MultipleChoiceFilter(choices=AuditAction.choices)
    entity_type = django_filters.CharFilter(field_name="entity_type", lookup_expr="iexact")
    entity_id = django_filters.CharFilter(field_name="entity_id")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    search = django_filters.CharFilter(field_name="description", lookup_expr="icontains")

    class Meta:
        model = AuditLog
        fields = []


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Complete activity log - Admin only, read-only."""

    queryset = AuditLog.objects.select_related("user")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_class = AuditLogFilter
    ordering_fields = ["created_at", "action"]
    ordering = ["-created_at"]
