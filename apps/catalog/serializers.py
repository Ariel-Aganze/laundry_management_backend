from decimal import Decimal

from rest_framework import serializers

from .models import ServiceCategory, ServiceItem

PRICE_FIELD_KWARGS = {"max_digits": 14, "decimal_places": 2, "min_value": Decimal("0")}


def _unique_name(queryset, value, instance):
    qs = queryset.filter(name__iexact=value)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError("This name is already used.", code="unique")


class ServiceCategorySerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True, default=0)
    active_items_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ServiceCategory
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "display_order",
            "items_count",
            "active_items_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Name is required.", code="required")
        _unique_name(ServiceCategory.objects.all(), value, self.instance)
        return value


class ServiceItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_is_active = serializers.BooleanField(source="category.is_active", read_only=True)
    is_orderable = serializers.BooleanField(read_only=True)
    normal_price = serializers.DecimalField(**PRICE_FIELD_KWARGS)
    express_price = serializers.DecimalField(**PRICE_FIELD_KWARGS)

    class Meta:
        model = ServiceItem
        fields = [
            "id",
            "category",
            "category_name",
            "category_is_active",
            "name",
            "description",
            "normal_price",
            "express_price",
            "is_active",
            "is_orderable",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Name is required.", code="required")
        return value

    def validate(self, attrs):
        category = attrs.get("category") or getattr(self.instance, "category", None)
        name = attrs.get("name") or getattr(self.instance, "name", None)
        if category and name:
            try:
                _unique_name(ServiceItem.objects.filter(category=category), name, self.instance)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"name": exc.detail})
        return attrs


class CatalogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceItem
        fields = ["id", "name", "description", "normal_price", "express_price"]


class CatalogCategorySerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ["id", "name", "description", "items"]

    def get_items(self, obj):
        # `active_items` is prefetched by CatalogView.
        return CatalogItemSerializer(getattr(obj, "active_items", []), many=True).data
