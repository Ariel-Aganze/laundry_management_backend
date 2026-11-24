from rest_framework import serializers

from apps.common.exceptions import ConflictError
from apps.common.phone import normalize_phone

from .models import Customer


class CustomerMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "full_name", "phone_number", "preferred_language"]


class CustomerSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    orders_count = serializers.SerializerMethodField()
    total_order_value = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()
    allow_duplicate = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Admin only: register even if another customer already uses this phone number.",
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "full_name",
            "phone_number",
            "preferred_language",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "orders_count",
            "total_order_value",
            "amount_paid",
            "outstanding_balance",
            "allow_duplicate",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    # Annotated values (see CustomerViewSet.get_queryset); absent right after creation.
    def get_orders_count(self, obj):
        return getattr(obj, "orders_count", 0)

    def get_total_order_value(self, obj):
        return str(getattr(obj, "total_order_value", "0.00"))

    def get_amount_paid(self, obj):
        return str(getattr(obj, "total_amount_paid", "0.00"))

    def get_outstanding_balance(self, obj):
        return str(getattr(obj, "outstanding_balance", "0.00"))

    def validate_full_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter the customer's full name.", code="required")
        return value

    def validate_phone_number(self, value):
        return normalize_phone(value)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_admin = bool(user and getattr(user, "is_admin", False))
        allow_duplicate = attrs.pop("allow_duplicate", False)

        phone = attrs.get("phone_number")
        phone_changed = phone is not None and (self.instance is None or phone != self.instance.phone_number)

        if self.instance is not None and phone_changed and not is_admin:
            raise serializers.ValidationError(
                {"phone_number": ["Only an administrator can change a customer's phone number."]},
                code="admin_required",
            )

        if phone_changed:
            duplicates = Customer.objects.filter(phone_number=phone)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            existing = duplicates.first()
            if existing and not (allow_duplicate and is_admin):
                raise ConflictError(
                    "A customer with this phone number already exists.",
                    code="duplicate_phone",
                    extra={"existing_customer": CustomerMiniSerializer(existing).data},
                )
        return attrs
