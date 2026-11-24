from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common.fields import MoneyField
from apps.common.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSING = "PROCESSING", "Processing"
    READY = "READY", "Ready"
    COLLECTED = "COLLECTED", "Collected"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
    PAID = "PAID", "Paid"


class ServiceType(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    EXPRESS = "EXPRESS", "Express"


class CollectionApproval(models.TextChoices):
    """Admin approval for handing clothes over while a balance is still owed."""

    NONE = "NONE", "Not requested"
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


CLOSED_STATUSES = (OrderStatus.COLLECTED, OrderStatus.CANCELLED)


class OrderQuerySet(models.QuerySet):
    def active(self):
        """Orders that count as business (not cancelled)."""
        return self.exclude(status=OrderStatus.CANCELLED)

    def open(self):
        """Orders still waiting to be collected."""
        return self.exclude(status__in=CLOSED_STATUSES)

    def overdue(self, today=None):
        today = today or timezone.localdate()
        return self.open().filter(pickup_date__lt=today)

    def upcoming(self, days=3, today=None):
        today = today or timezone.localdate()
        return self.open().filter(pickup_date__gte=today, pickup_date__lte=today + timedelta(days=days))


class Order(TimeStampedModel):
    reference = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="orders")
    drop_off_date = models.DateField(default=timezone.localdate)
    pickup_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=12, choices=OrderStatus.choices, default=OrderStatus.RECEIVED, db_index=True
    )
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True
    )
    total_quantity = models.PositiveIntegerField(default=0)
    total_amount = MoneyField()
    amount_paid = MoneyField()
    balance = MoneyField()
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders_created"
    )
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders_collected",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders_cancelled",
    )
    cancellation_reason = models.TextField(blank=True)

    collection_approval = models.CharField(
        max_length=10, choices=CollectionApproval.choices, default=CollectionApproval.NONE, db_index=True
    )
    collection_request_note = models.TextField(blank=True)
    collection_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    collection_requested_at = models.DateTimeField(null=True, blank=True)
    collection_decision_note = models.TextField(blank=True)
    collection_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    collection_decided_at = models.DateTimeField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(pickup_date__gte=F("drop_off_date")), name="order_pickup_not_before_dropoff"
            ),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="order_total_gte_0"),
            models.CheckConstraint(condition=Q(amount_paid__gte=0), name="order_paid_gte_0"),
            models.CheckConstraint(condition=Q(balance__gte=0), name="order_balance_gte_0"),
        ]

    def __str__(self):
        return self.reference

    @property
    def is_open(self):
        return self.status not in CLOSED_STATUSES

    @property
    def is_overdue(self):
        return self.is_open and self.pickup_date < timezone.localdate()


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    service_item = models.ForeignKey(
        "catalog.ServiceItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    category = models.ForeignKey(
        "catalog.ServiceCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    # Snapshots: catalog records can be renamed or deactivated later.
    item_name_snapshot = models.CharField(max_length=100)
    category_name_snapshot = models.CharField(max_length=100)
    service_type = models.CharField(max_length=10, choices=ServiceType.choices, default=ServiceType.NORMAL)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = MoneyField()
    subtotal = MoneyField()
    condition_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="order_item_quantity_gt_0"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="order_item_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.item_name_snapshot} ({self.service_type})"
