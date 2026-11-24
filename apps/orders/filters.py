import django_filters
from django.db.models import Q
from django.utils import timezone

from apps.common.phone import phone_search_fragment

from .models import CLOSED_STATUSES, CollectionApproval, Order, OrderStatus, PaymentStatus, ServiceType


def search_orders(queryset, term):
    """Search by reference, customer name or customer phone (FR-027)."""
    term = (term or "").strip()
    if not term:
        return queryset
    condition = Q(reference__icontains=term) | Q(customer__full_name__icontains=term)
    fragment = phone_search_fragment(term)
    if fragment:
        condition |= Q(customer__phone_number__icontains=fragment.lstrip("+"))
    return queryset.filter(condition)


class CommaChoiceFilter(django_filters.CharFilter):
    """?status=READY,PROCESSING"""

    def __init__(self, *args, choices=None, **kwargs):
        self.allowed = {value for value, _ in (choices or [])}
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            return qs
        values = [v.strip().upper() for v in value.split(",") if v.strip().upper() in self.allowed]
        if not values:
            return qs.none()
        return qs.filter(**{f"{self.field_name}__in": values})


class OrderFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    status = CommaChoiceFilter(field_name="status", choices=OrderStatus.choices)
    payment_status = CommaChoiceFilter(field_name="payment_status", choices=PaymentStatus.choices)
    collection_approval = CommaChoiceFilter(field_name="collection_approval", choices=CollectionApproval.choices)
    service_type = django_filters.ChoiceFilter(choices=ServiceType.choices, method="filter_service_type")
    created_by = django_filters.UUIDFilter(field_name="created_by_id")
    customer = django_filters.UUIDFilter(field_name="customer_id")
    drop_off_from = django_filters.DateFilter(field_name="drop_off_date", lookup_expr="gte")
    drop_off_to = django_filters.DateFilter(field_name="drop_off_date", lookup_expr="lte")
    pickup_from = django_filters.DateFilter(field_name="pickup_date", lookup_expr="gte")
    pickup_to = django_filters.DateFilter(field_name="pickup_date", lookup_expr="lte")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    has_balance = django_filters.BooleanFilter(method="filter_has_balance")
    open = django_filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Order
        fields = []

    def filter_search(self, qs, name, value):
        return search_orders(qs, value)

    def filter_service_type(self, qs, name, value):
        return qs.filter(items__service_type=value).distinct() if value else qs

    def filter_overdue(self, qs, name, value):
        if value is None:
            return qs
        overdue = Q(pickup_date__lt=timezone.localdate()) & ~Q(status__in=CLOSED_STATUSES)
        return qs.filter(overdue) if value else qs.exclude(overdue)

    def filter_has_balance(self, qs, name, value):
        if value is None:
            return qs
        return qs.filter(balance__gt=0) if value else qs.filter(balance=0)

    def filter_open(self, qs, name, value):
        if value is None:
            return qs
        return qs.exclude(status__in=CLOSED_STATUSES) if value else qs.filter(status__in=CLOSED_STATUSES)
