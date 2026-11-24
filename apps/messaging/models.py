from django.conf import settings
from django.db import models

from apps.common.models import UUIDModel


class WhatsAppMessageLog(UUIDModel):
    """
    Records that a user OPENED WhatsApp with a pre-filled message.
    This is not proof of delivery - the user sends the message manually (FR-055).
    """

    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="whatsapp_logs"
    )
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="whatsapp_logs")
    template_key = models.CharField(max_length=30, blank=True)
    language = models.CharField(max_length=5)
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    initiated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-initiated_at"]

    def __str__(self):
        return f"{self.template_key} -> {self.phone_number}"
