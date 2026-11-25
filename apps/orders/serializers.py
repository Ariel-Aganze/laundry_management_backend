from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import ServiceItem
from apps.customers.models import Customer
from apps.customers.serializers import CustomerMiniSerializer, CustomerSerializer
from apps.payments.serializers import InitialPaymentSerializer, PaymentSerializer
from apps.receipts.serializers import ReceiptListSerializer

from .models import Order, OrderItem, OrderStatus, ServiceType


# --------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "service_item",
            "category",
            "item_name_snapshot",
            "category_name_snapshot",
            "service_type",
            "quantity",
            "unit_price",
            "subtotal",
            "is_free",
            "condition_notes",
        ]
        read_only_fields = fields


class OrderListSerializer(serializers.ModelSerializer):
    customer = CustomerMiniSerializer(read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "reference",
            "customer",
            "status",
            "payment_status",
            "total_quantity",
            "total_amount",
            "amount_paid",
            "balance",
            "drop_off_date",
            "pickup_date",
            "is_overdue",
            "collection_approval",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    receipts = ReceiptListSerializer(many=True, read_only=True)
    whatsapp_logs = serializers.SerializerMethodField()
    activity = serializers.SerializerMethodField()
    collected_by_name = serializers.CharField(source="collected_by.full_name", read_only=True, default=None)
    cancelled_by_name = serializers.CharField(source="cancelled_by.full_name", read_only=True, default=None)
    collection_requested_by_name = serializers.CharField(
        source="collection_requested_by.full_name", read_only=True, default=None
    )
    collection_decided_by_name = serializers.CharField(
        source="collection_decided_by.full_name", read_only=True, default=None
    )

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + [
            "notes",
            "items",
            "payments",
            "receipts",
            "whatsapp_logs",
            "collected_at",
            "collected_by",
            "collected_by_name",
            "cancelled_at",
            "cancelled_by",
            "cancelled_by_name",
            "cancellation_reason",
            "collection_request_note",
            "collection_requested_by_name",
            "collection_requested_at",
            "collection_decision_note",
            "collection_decided_by_name",
            "collection_decided_at",
            "updated_at",
            "activity",
        ]
        read_only_fields = fields

    def get_whatsapp_logs(self, obj):
        from apps.messaging.serializers import WhatsAppMessageLogSerializer

        return WhatsAppMessageLogSerializer(obj.whatsapp_logs.select_related("initiated_by")[:20], many=True).data

    def get_activity(self, obj):
        """Order history from the audit log - Admin only (FR-076)."""
        request = self.context.get("request")
        if not (request and getattr(request.user, "is_admin", False)):
            return None
        from apps.audit.models import AuditLog
        from apps.audit.views import AuditLogSerializer

        logs = AuditLog.objects.filter(entity_type="Order", entity_id=str(obj.pk)).select_related("user")[:50]
        return AuditLogSerializer(logs, many=True).data


# --------------------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------------------
class OrderItemInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False, help_text="Existing item id (admin edits only)")
    service_item = serializers.PrimaryKeyRelatedField(queryset=ServiceItem.objects.select_related("category"))
    service_type = serializers.ChoiceField(choices=ServiceType.choices, default=ServiceType.NORMAL)
    quantity = serializers.IntegerField(min_value=1, max_value=10000)
    custom_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True,
        help_text="Required when service_type is CUSTOM; ignored otherwise.",
    )
    is_free = serializers.BooleanField(required=False, default=False, help_text="Offered service: counts 0.")
    condition_notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

    def validate(self, attrs):
        if attrs.get("service_type") == ServiceType.CUSTOM:
            if attrs.get("custom_price") is None:
                raise serializers.ValidationError(
                    {"custom_price": ["Enter the custom price for this item."]}, code="custom_price_required"
                )
        else:
            attrs.pop("custom_price", None)
        return attrs


class OrderCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)
    new_customer = CustomerSerializer(required=False)
    drop_off_date = serializers.DateField(required=False)
    pickup_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    items = OrderItemInputSerializer(many=True, allow_empty=False)
    payment = InitialPaymentSerializer(required=False, allow_null=True)

    def validate(self, attrs):
        has_customer = attrs.get("customer") is not None
        has_new = bool(attrs.get("new_customer"))
        if has_customer == has_new:
            raise serializers.ValidationError(
                {"customer": ["Select an existing customer or register a new one."]}, code="customer_required"
            )

        today = timezone.localdate()
        drop_off = attrs.get("drop_off_date") or today
        if drop_off > today:
            raise serializers.ValidationError(
                {"drop_off_date": ["The drop-off date cannot be in the future."]}, code="future_date"
            )
        if attrs["pickup_date"] < drop_off:
            raise serializers.ValidationError(
                {"pickup_date": ["The pickup date cannot be earlier than the drop-off date."]},
                code="pickup_before_dropoff",
            )
        attrs["drop_off_date"] = drop_off

        errors = {}
        for index, item in enumerate(attrs["items"]):
            if item.get("id"):
                errors[index] = {"id": ["Not allowed when creating an order."]}
            elif not item["service_item"].is_orderable:
                errors[index] = {"service_item": ["This service is no longer available."]}
        if errors:
            raise serializers.ValidationError(
                {"items": [errors.get(i, {}) for i in range(len(attrs["items"]))]}, code="inactive_service"
            )
        return attrs


class ItemNoteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    condition_notes = serializers.CharField(allow_blank=True, max_length=1000)


class OrderUpdateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)
    drop_off_date = serializers.DateField(required=False)
    pickup_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    items = OrderItemInputSerializer(many=True, allow_empty=False, required=False)
    item_notes = ItemNoteSerializer(many=True, required=False)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c for c in OrderStatus.choices if c[0] != OrderStatus.CANCELLED])
    approve_balance = serializers.BooleanField(
        required=False, default=False, help_text="Admin only: approve collection with an outstanding balance."
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class CollectionRequestSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class CollectionDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

