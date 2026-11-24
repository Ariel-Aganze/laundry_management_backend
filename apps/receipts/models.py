from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.common.models import UUIDModel


class ReceiptType(models.TextChoices):
    ORDER = "ORDER", "Order receipt"
    PAYMENT = "PAYMENT", "Payment receipt"


class Receipt(UUIDModel):
    """
    A receipt stores a frozen snapshot (`data`) of everything printed on it, so
    reprinting it later always shows exactly what the customer originally got.
    """

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="receipts")
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="receipts"
    )
    receipt_number = models.CharField(max_length=30, unique=True)
    receipt_type = models.CharField(max_length=10, choices=ReceiptType.choices, db_index=True)
    data = models.JSONField(encoder=DjangoJSONEncoder)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="receipts_generated"
    )
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return self.receipt_number
