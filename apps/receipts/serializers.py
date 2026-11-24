from rest_framework import serializers

from .models import Receipt


class ReceiptListSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    generated_by_name = serializers.CharField(source="generated_by.full_name", read_only=True)
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = [
            "id",
            "receipt_number",
            "receipt_type",
            "order",
            "order_reference",
            "payment",
            "amount",
            "generated_by",
            "generated_by_name",
            "generated_at",
        ]
        read_only_fields = fields

    def get_amount(self, obj):
        payment = (obj.data or {}).get("payment")
        return payment["amount"] if payment else (obj.data or {}).get("total_amount")


class ReceiptSerializer(ReceiptListSerializer):
    """Includes the frozen receipt content, used by the browser/thermal print view."""

    class Meta(ReceiptListSerializer.Meta):
        fields = ReceiptListSerializer.Meta.fields + ["data"]
        read_only_fields = fields
