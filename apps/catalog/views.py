from django.db.models import Count, Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import diff, log_activity, snapshot
from apps.common.permissions import IsAdminOrReadOnly

from .models import ServiceCategory, ServiceItem
from .serializers import CatalogCategorySerializer, ServiceCategorySerializer, ServiceItemSerializer

CATEGORY_AUDIT_FIELDS = ["name", "description", "is_active", "display_order"]
ITEM_AUDIT_FIELDS = [
    "category",
    "name",
    "description",
    "normal_price",
    "express_price",
    "is_active",
    "display_order",
]
PRICE_FIELDS = {"normal_price", "express_price"}


def _wants_inactive(request):
    """Admins see everything (optionally filtered); cashiers only see active records."""
    return getattr(request.user, "is_admin", False)


class ServiceCategoryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["is_active"]
    ordering_fields = ["name", "display_order", "created_at"]
    pagination_class = None

    def get_queryset(self):
        qs = ServiceCategory.objects.annotate(
            items_count=Count("items"),
            active_items_count=Count("items", filter=Q(items__is_active=True)),
        )
        if not _wants_inactive(self.request):
            qs = qs.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def perform_create(self, serializer):
        category = serializer.save()
        log_activity(
            AuditAction.CATEGORY_CREATED,
            request=self.request,
            entity=category,
            description=f"Created category '{category.name}'.",
            new_values=snapshot(category, CATEGORY_AUDIT_FIELDS),
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, CATEGORY_AUDIT_FIELDS)
        category = serializer.save()
        old, new = diff(before, snapshot(category, CATEGORY_AUDIT_FIELDS))
        if new:
            log_activity(
                AuditAction.CATEGORY_UPDATED,
                request=self.request,
                entity=category,
                description=f"Updated category '{category.name}'.",
                old_values=old,
                new_values=new,
            )


class ServiceItemViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceItemSerializer
    permission_classes = [IsAdminOrReadOnly]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_fields = ["category", "is_active"]
    ordering_fields = ["name", "normal_price", "express_price", "display_order", "created_at"]

    def get_queryset(self):
        qs = ServiceItem.objects.select_related("category")
        if not _wants_inactive(self.request):
            qs = qs.filter(is_active=True, category__is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(category__name__icontains=search))
        return qs

    def perform_create(self, serializer):
        item = serializer.save()
        log_activity(
            AuditAction.SERVICE_CREATED,
            request=self.request,
            entity=item,
            description=f"Created service item '{item.name}' in '{item.category.name}'.",
            new_values=snapshot(item, ITEM_AUDIT_FIELDS),
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, ITEM_AUDIT_FIELDS)
        item = serializer.save()
        old, new = diff(before, snapshot(item, ITEM_AUDIT_FIELDS))
        if not new:
            return
        price_changed = bool(PRICE_FIELDS & new.keys())
        log_activity(
            AuditAction.PRICE_CHANGED if price_changed else AuditAction.SERVICE_UPDATED,
            request=self.request,
            entity=item,
            description=(
                f"Changed prices of '{item.name}'." if price_changed else f"Updated service item '{item.name}'."
            ),
            old_values=old,
            new_values=new,
        )

    def destroy(self, request, *args, **kwargs):
        """DELETE deactivates the item; history is never removed."""
        item = self.get_object()
        if item.is_active:
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
            log_activity(
                AuditAction.SERVICE_UPDATED,
                request=request,
                entity=item,
                description=f"Deactivated service item '{item.name}'.",
                old_values={"is_active": True},
                new_values={"is_active": False},
            )
        return Response(ServiceItemSerializer(item).data, status=status.HTTP_200_OK)


class CatalogView(APIView):
    """Active categories with their active items - one request for the New Order screen."""

    def get(self, request):
        categories = ServiceCategory.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "items",
                queryset=ServiceItem.objects.filter(is_active=True).order_by("display_order", "name"),
                to_attr="active_items",
            )
        )
        return Response(CatalogCategorySerializer(categories, many=True).data)
