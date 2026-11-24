from decimal import Decimal

from rest_framework import serializers

from .models import Payment, PaymentMethod


class PaymentSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    customer_name = serializers.CharField(source="order.customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="order.customer.phone_number", read_only=True)
    method_display = serializers.CharField(read_only=True)
    received_by_name = serializers.CharField(source="received_by.full_name", read_only=True)
    reversed_by_name = serializers.CharField(source="reversed_by.full_name", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_reference",
            "customer_name",
            "customer_phone",
            "amount",
            "payment_method",
            "method_other",
            "method_display",
            "transaction_reference",
            "notes",
            "status",
            "received_at",
            "received_by",
            "received_by_name",
            "reversed_at",
            "reversed_by",
            "reversed_by_name",
            "reversal_reason",
        ]
        read_only_fields = fields


class PaymentInputSerializer(serializers.Serializer):
    """Payment fields shared by 'record payment' and 'create order'."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    method_other = serializers.CharField(required=False, allow_blank=True, max_length=50, default="")
    transaction_reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

    def validate(self, attrs):
        if attrs.get("payment_method") == PaymentMethod.OTHER and not attrs.get("method_other", "").strip():
            raise serializers.ValidationError(
                {"method_other": ["Specify the payment method."]}, code="method_other_required"
            )
        return attrs


class InitialPaymentSerializer(PaymentInputSerializer):
    """At order creation the customer may pay nothing (amount 0 = no payment)."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))


class RecordPaymentSerializer(PaymentInputSerializer):
    order = serializers.UUIDField()


class ReversePaymentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
