"""
Dashboards (Admin + Cashier) and analytics (Admin only).

Definitions (FR-063, FR-072) - kept strictly separate:
  * order value     = total of orders REGISTERED in the period (cancelled excluded)
  * money received  = VALID payments RECORDED in the period (reversed payments and
                      payments on cancelled orders excluded)
  * outstanding     = balance remaining on active orders right now
Nothing here is called "profit": operating costs are not recorded.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, DecimalField, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.business.models import BusinessSettings
from apps.common.fields import ZERO
from apps.common.permissions import IsAdmin
from apps.customers.models import Customer
from apps.orders.models import CollectionApproval, Order, OrderItem, OrderStatus
from apps.orders.serializers import OrderListSerializer
from apps.payments.models import Payment, PaymentMethod, PaymentState
from apps.payments.serializers import PaymentSerializer

from .periods import iter_buckets, bucket_start, resolve_group, resolve_period

MONEY_OUTPUT = DecimalField(max_digits=16, decimal_places=2)


def money_sum(field, **filter_kwargs):
    condition = Q(**filter_kwargs) if filter_kwargs else None
    return Coalesce(Sum(field, filter=condition), Value(ZERO), output_field=MONEY_OUTPUT)


def m(value):
    """Money as a string with 2 decimals (consistent with serializers)."""
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def active_orders():
    return Order.objects.active()


def counted_payments():
    return Payment.objects.counted()


def _currency():
    business = BusinessSettings.load()
    return {"currency": business.currency, "currency_decimals": business.currency_decimals}


# --------------------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------------------
class DashboardSummaryView(APIView):
    """
    Cashier: today's operational figures.
    Admin: any period (?period=today|yesterday|last_7_days|last_30_days|this_month|last_month|custom&start=&end=).
    """

    def get(self, request):
        user = request.user
        period = resolve_period(request.query_params if user.is_admin else {}, default="today")
        start, end = period.bounds
        today = timezone.localdate()
        business = BusinessSettings.load()

        orders = active_orders().filter(created_at__gte=start, created_at__lt=end)
        order_stats = orders.aggregate(count=Count("id"), value=money_sum("total_amount"))
        payments = counted_payments().filter(received_at__gte=start, received_at__lt=end)
        payment_stats = payments.aggregate(count=Count("id"), total=money_sum("amount"))
        outstanding = active_orders().filter(balance__gt=0).aggregate(count=Count("id"), total=money_sum("balance"))

        data = {
            **period.as_dict(),
            **_currency(),
            "orders_count": order_stats["count"],
            "order_value": m(order_stats["value"]),
            "money_received": m(payment_stats["total"]),
            "payments_count": payment_stats["count"],
            "outstanding_balance": m(outstanding["total"]),
            "outstanding_orders_count": outstanding["count"],
            "ready_for_pickup_count": Order.objects.filter(status=OrderStatus.READY).count(),
            "upcoming_pickups_count": Order.objects.upcoming(business.upcoming_pickup_days, today).count(),
            "overdue_pickups_count": Order.objects.overdue(today).count(),
            "pending_collection_approvals": Order.objects.open()
            .filter(collection_approval=CollectionApproval.PENDING)
            .count(),
            "recent_orders": OrderListSerializer(
                Order.objects.select_related("customer", "created_by").order_by("-created_at")[:8], many=True
            ).data,
            "recent_payments": PaymentSerializer(
                Payment.objects.select_related("order", "order__customer", "received_by", "reversed_by").order_by(
                    "-received_at"
                )[:8],
                many=True,
            ).data,
        }

        if user.is_admin:
            data["cashier_activity"] = _cashier_rows(start, end)
        else:
            mine = orders.filter(created_by=user).aggregate(count=Count("id"), value=money_sum("total_amount"))
            my_payments = payments.filter(received_by=user).aggregate(count=Count("id"), total=money_sum("amount"))
            data["my_orders_count"] = mine["count"]
            data["my_order_value"] = m(mine["value"])
            data["my_money_received"] = m(my_payments["total"])
            data["my_payments_count"] = my_payments["count"]
        return Response(data)


class _PickupListBase(generics.ListAPIView):
    serializer_class = OrderListSerializer

    def base_queryset(self):
        return Order.objects.select_related("customer", "created_by").order_by("pickup_date", "created_at")


class UpcomingPickupsView(_PickupListBase):
    """Open orders due today or within ?days= (default from settings), chronological."""

    def get_queryset(self):
        try:
            days = int(self.request.query_params.get("days", BusinessSettings.load().upcoming_pickup_days))
        except ValueError:
            days = BusinessSettings.load().upcoming_pickup_days
        days = max(0, min(days, 90))
        return self.base_queryset().filter(pk__in=Order.objects.upcoming(days).values("pk"))


class OverduePickupsView(_PickupListBase):
    """Expected pickup date has passed but not collected or cancelled (FR-065)."""

    def get_queryset(self):
        return self.base_queryset().filter(pk__in=Order.objects.overdue().values("pk"))


# --------------------------------------------------------------------------------------
# Analytics (Admin only)
# --------------------------------------------------------------------------------------
def _daily(queryset, date_field, value_field):
    rows = (
        queryset.annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(total=money_sum(value_field), count=Count("id"))
    )
    return {row["day"]: row for row in rows}


def _series(period, group, sources):
    """sources: {name: (daily_rows, 'total'|'count', is_money)} -> list of buckets."""
    buckets = {b: defaultdict(lambda: Decimal(0)) for b in iter_buckets(period, group)}
    for name, (rows, key, _) in sources.items():
        for day, row in rows.items():
            if day is None:
                continue
            bucket = bucket_start(day, group)
            if bucket in buckets:
                buckets[bucket][name] += Decimal(row[key])
    series = []
    for bucket, values in buckets.items():
        entry = {"date": bucket.isoformat()}
        for name, (_, _, is_money) in sources.items():
            entry[name] = m(values[name]) if is_money else int(values[name])
        series.append(entry)
    return series


class RevenueAnalyticsView(APIView):
    """Money received vs order value over time (FR-066, FR-071)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        period = resolve_period(request.query_params, default="last_30_days")
        group = resolve_group(request.query_params, period)
        start, end = period.bounds
        payments = counted_payments().filter(received_at__gte=start, received_at__lt=end)
        orders = active_orders().filter(created_at__gte=start, created_at__lt=end)
        payment_rows = _daily(payments, "received_at", "amount")
        order_rows = _daily(orders, "created_at", "total_amount")
        totals_orders = orders.aggregate(count=Count("id"), value=money_sum("total_amount"))
        return Response(
            {
                **period.as_dict(),
                **_currency(),
                "group_by": group,
                "totals": {
                    "money_received": m(payments.aggregate(t=money_sum("amount"))["t"]),
                    "order_value": m(totals_orders["value"]),
                    "orders_count": totals_orders["count"],
                },
                "series": _series(
                    period,
                    group,
                    {
                        "money_received": (payment_rows, "total", True),
                        "order_value": (order_rows, "total", True),
                        "orders_count": (order_rows, "count", False),
                    },
                ),
            }
        )


class ServiceAnalyticsView(APIView):
    """Popular items/categories and Normal vs Express (FR-067, FR-068)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        period = resolve_period(request.query_params, default="last_30_days")
        start, end = period.bounds
        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 50))
        except ValueError:
            limit = 10
        items = OrderItem.objects.filter(
            order__created_at__gte=start, order__created_at__lt=end
        ).exclude(order__status=OrderStatus.CANCELLED)

        top_items = (
            items.values("service_item_id")
            .annotate(
                name=Max("item_name_snapshot"),
                category=Max("category_name_snapshot"),
                quantity=Sum("quantity"),
                orders=Count("order", distinct=True),
                value=money_sum("subtotal"),
            )
            .order_by("-quantity", "-value")[:limit]
        )
        top_categories = (
            items.values("category_id")
            .annotate(
                name=Max("category_name_snapshot"),
                quantity=Sum("quantity"),
                orders=Count("order", distinct=True),
                value=money_sum("subtotal"),
            )
            .order_by("-quantity", "-value")[:limit]
        )
        by_type = {
            row["service_type"]: row
            for row in items.values("service_type").annotate(
                quantity=Sum("quantity"), orders=Count("order", distinct=True), value=money_sum("subtotal")
            )
        }
        return Response(
            {
                **period.as_dict(),
                **_currency(),
                "top_items": [
                    {
                        "service_item": str(r["service_item_id"]) if r["service_item_id"] else None,
                        "name": r["name"],
                        "category": r["category"],
                        "quantity": r["quantity"],
                        "orders": r["orders"],
                        "value": m(r["value"]),
                    }
                    for r in top_items
                ],
                "top_categories": [
                    {
                        "category": str(r["category_id"]) if r["category_id"] else None,
                        "name": r["name"],
                        "quantity": r["quantity"],
                        "orders": r["orders"],
                        "value": m(r["value"]),
                    }
                    for r in top_categories
                ],
                "service_types": [
                    {
                        "service_type": key,
                        "quantity": by_type.get(key, {}).get("quantity") or 0,
                        "orders": by_type.get(key, {}).get("orders") or 0,
                        "value": m(by_type.get(key, {}).get("value") or 0),
                    }
                    for key in ("NORMAL", "EXPRESS")
                ],
            }
        )


def _cashier_rows(start, end):
    User = get_user_model()
    order_rows = {
        r["created_by"]: r
        for r in active_orders()
        .filter(created_at__gte=start, created_at__lt=end)
        .values("created_by")
        .annotate(count=Count("id"), value=money_sum("total_amount"))
    }
    payment_rows = {
        r["received_by"]: r
        for r in counted_payments()
        .filter(received_at__gte=start, received_at__lt=end)
        .values("received_by")
        .annotate(count=Count("id"), total=money_sum("amount"))
    }
    rows = []
    for user in User.objects.filter(Q(pk__in=list(order_rows)) | Q(pk__in=list(payment_rows)) | Q(is_active=True)):
        o = order_rows.get(user.pk, {})
        p = payment_rows.get(user.pk, {})
        count = o.get("count", 0)
        value = Decimal(o.get("value") or 0)
        rows.append(
            {
                "user": str(user.pk),
                "name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "orders_count": count,
                "orders_value": m(value),
                "average_order_value": m(value / count if count else 0),
                "payments_count": p.get("count", 0),
                "payments_total": m(p.get("total") or 0),
            }
        )
    rows.sort(key=lambda r: (-r["orders_count"], r["name"]))
    return rows


class CashierAnalyticsView(APIView):
    """Orders and payments per user (FR-069)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        period = resolve_period(request.query_params, default="last_30_days")
        start, end = period.bounds
        return Response({**period.as_dict(), **_currency(), "results": _cashier_rows(start, end)})


class CustomerAnalyticsView(APIView):
    """FR-070: totals, new customers over time, returning, most frequent, average spending."""

    permission_classes = [IsAdmin]

    def get(self, request):
        period = resolve_period(request.query_params, default="last_30_days")
        group = resolve_group(request.query_params, period)
        start, end = period.bounds

        new_customers = Customer.objects.filter(created_at__gte=start, created_at__lt=end)
        new_rows = {
            r["day"]: r
            for r in new_customers.annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))
        }

        customer_stats = Customer.objects.annotate(
            orders_count=Count("orders", filter=~Q(orders__status=OrderStatus.CANCELLED)),
            spent=money_sum("orders__total_amount", orders__status__in=[
                s for s in OrderStatus.values if s != OrderStatus.CANCELLED
            ]),
        )
        with_orders = customer_stats.filter(orders_count__gt=0)
        totals = active_orders().aggregate(
            customers=Count("customer", distinct=True), spent=money_sum("total_amount")
        )

        # Customers who ordered in the period and had already ordered before it.
        period_customers = active_orders().filter(created_at__gte=start, created_at__lt=end).values("customer")
        returning_in_period = (
            active_orders()
            .filter(customer__in=period_customers, created_at__lt=start)
            .values("customer")
            .distinct()
            .count()
        )
        top = with_orders.order_by("-orders_count", "-spent")[:10]

        return Response(
            {
                **period.as_dict(),
                **_currency(),
                "group_by": group,
                "total_customers": Customer.objects.count(),
                "customers_with_orders": totals["customers"],
                "new_customers": new_customers.count(),
                "returning_customers": with_orders.filter(orders_count__gte=2).count(),
                "returning_customers_in_period": returning_in_period,
                "average_spending": m(totals["spent"] / totals["customers"] if totals["customers"] else 0),
                "new_customers_series": _series(period, group, {"count": (new_rows, "count", False)}),
                "top_customers": [
                    {
                        "id": str(c.pk),
                        "full_name": c.full_name,
                        "phone_number": c.phone_number,
                        "orders_count": c.orders_count,
                        "total_spent": m(c.spent),
                    }
                    for c in top
                ],
            }
        )


class PaymentAnalyticsView(APIView):
    """Received payments by method, reversals and outstanding balances by age (FR-071)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        period = resolve_period(request.query_params, default="last_30_days")
        start, end = period.bounds
        today = timezone.localdate()
        payments = counted_payments().filter(received_at__gte=start, received_at__lt=end)
        by_method = {
            r["payment_method"]: r
            for r in payments.values("payment_method").annotate(count=Count("id"), total=money_sum("amount"))
        }
        reversed_stats = Payment.objects.filter(
            status=PaymentState.REVERSED, reversed_at__gte=start, reversed_at__lt=end
        ).aggregate(count=Count("id"), total=money_sum("amount"))

        outstanding = active_orders().filter(balance__gt=0)
        ages = [
            ("0_7_days", today - timedelta(days=7), None),
            ("8_30_days", today - timedelta(days=30), today - timedelta(days=8)),
            ("over_30_days", None, today - timedelta(days=31)),
        ]
        aging = []
        for key, oldest, newest in ages:
            qs = outstanding
            if oldest:
                qs = qs.filter(drop_off_date__gte=oldest)
            if newest:
                qs = qs.filter(drop_off_date__lte=newest)
            stats = qs.aggregate(count=Count("id"), total=money_sum("balance"))
            aging.append({"bucket": key, "orders": stats["count"], "balance": m(stats["total"])})

        totals = outstanding.aggregate(count=Count("id"), total=money_sum("balance"), oldest=Min("drop_off_date"))
        return Response(
            {
                **period.as_dict(),
                **_currency(),
                "money_received": m(payments.aggregate(t=money_sum("amount"))["t"]),
                "payments_count": payments.count(),
                "by_method": [
                    {
                        "payment_method": method,
                        "count": by_method.get(method, {}).get("count", 0),
                        "total": m(by_method.get(method, {}).get("total") or 0),
                    }
                    for method in PaymentMethod.values
                ],
                "reversed": {"count": reversed_stats["count"], "total": m(reversed_stats["total"])},
                "outstanding": {
                    "orders": totals["count"],
                    "balance": m(totals["total"]),
                    "oldest_drop_off_date": totals["oldest"].isoformat() if totals["oldest"] else None,
                    "aging": aging,
                },
            }
        )
