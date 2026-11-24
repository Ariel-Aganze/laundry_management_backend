from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.fields import MONEY_KWARGS
from apps.common.models import UUIDModel


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
    CARD = "CARD", "Card"
    OTHER = "OTHER", "Other"


class PaymentState(models.TextChoices):
    VALID = "VALID", "Valid"
    REVERSED = "REVERSED", "Reversed"


class PaymentQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(status=PaymentState.VALID)

    def counted(self):
        """Payments that count as money received: valid and not on a cancelled order."""
        return self.valid().exclude(order__status="CANCELLED")


class Payment(UUIDModel):
    """
    A payment is never deleted or edited. Mistakes are corrected by an Admin
    reversal, which keeps the original record and stores the reason.
    """

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY_KWARGS)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    method_other = models.CharField(max_length=50, blank=True)
    transaction_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=PaymentState.choices, default=PaymentState.VALID, db_index=True
    )
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_received"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments_reversed",
    )
    reversal_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ["received_at", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_gt_0"),
        ]

    def __str__(self):
        return f"{self.amount} on {self.order_id} ({self.status})"

    @property
    def method_display(self):
        if self.payment_method == PaymentMethod.OTHER and self.method_other:
            return self.method_other
        return self.get_payment_method_display()
