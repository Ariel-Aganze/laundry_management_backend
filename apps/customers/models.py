from django.conf import settings
from django.db import models

from apps.common.choices import Language
from apps.common.models import TimeStampedModel


class Customer(TimeStampedModel):
    full_name = models.CharField(max_length=150)
    # Stored in E.164 form with country code, e.g. +250788123456
    phone_number = models.CharField(max_length=20, db_index=True)
    preferred_language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customers_created",
    )

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["full_name"], name="customer_name_idx")]

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    @property
    def whatsapp_number(self):
        return self.phone_number.lstrip("+")
