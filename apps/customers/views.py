from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from apps.audit.models import AuditAction
from apps.audit.services import diff, log_activity, snapshot
from apps.common.phone import phone_search_fragment

from .models import Customer
from .serializers import CustomerSerializer
from .services import CUSTOMER_AUDIT_FIELDS, create_customer


def _money_sum(field, condition):
    return Coalesce(
        Sum(field, filter=condition),
        Value(Decimal("0.00")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def search_customers(queryset, term, prefix=""):
    """Filter by name (contains) or phone (partial digits)."""
    term = (term or "").strip()
    if not term:
        return queryset
    condition = Q(**{f"{prefix}full_name__icontains": term})
    fragment = phone_search_fragment(term)
    if fragment:
        condition |= Q(**{f"{prefix}phone_number__icontains": fragment.lstrip("+")})
    return queryset.filter(condition)


class CustomerViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CustomerSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    ordering_fields = ["full_name", "created_at"]
    ordering = ["full_name"]
    filterset_fields = ["preferred_language"]

    def get_queryset(self):
        active = ~Q(orders__status="CANCELLED")
        qs = Customer.objects.select_related("created_by").annotate(
            orders_count=Count("orders", filter=active),
            total_order_value=_money_sum("orders__total_amount", active),
            total_amount_paid=_money_sum("orders__amount_paid", active),
            outstanding_balance=_money_sum("orders__balance", active),
        )
        return search_customers(qs, self.request.query_params.get("search"))

    def perform_create(self, serializer):
        serializer.instance = create_customer(
            data=serializer.validated_data, user=self.request.user, request=self.request
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, CUSTOMER_AUDIT_FIELDS)
        customer = serializer.save()
        old, new = diff(before, snapshot(customer, CUSTOMER_AUDIT_FIELDS))
        if new:
            log_activity(
                AuditAction.CUSTOMER_UPDATED,
                request=self.request,
                entity=customer,
                description=f"Updated customer {customer.full_name}.",
                old_values=old,
                new_values=new,
            )

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        from apps.orders.models import Order
        from apps.orders.serializers import OrderListSerializer

        customer = self.get_object()
        qs = (
            Order.objects.filter(customer=customer)
            .select_related("customer", "created_by")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        serializer = OrderListSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def payments(self, request, pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        customer = self.get_object()
        qs = (
            Payment.objects.filter(order__customer=customer)
            .select_related("order", "order__customer", "received_by", "reversed_by")
            .order_by("-received_at")
        )
        page = self.paginate_queryset(qs)
        serializer = PaymentSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)
