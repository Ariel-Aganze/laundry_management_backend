from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.choices import Language
from apps.common.models import UUIDModel

CURRENCY_CHOICES = ["RWF", "CDF", "USD", "KES", "UGX", "TZS", "EUR", "BIF"]


class ReceiptPaper(models.TextChoices):
    THERMAL_58 = "58mm", "58mm thermal"
    THERMAL_80 = "80mm", "80mm thermal"
    A4 = "A4", "A4"


class BusinessSettings(UUIDModel):
    """Single-row table holding the business profile and preferences."""

    singleton = models.BooleanField(default=True, unique=True, editable=False)
    business_name = models.CharField(max_length=150, default="My Laundry")
    phone_number = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    # The logo is stored in the database (not on disk) so it survives redeploys
    # on hosts with ephemeral file systems. Resized to max 512px on upload.
    logo_data = models.BinaryField(null=True, blank=True, editable=False)
    logo_content_type = models.CharField(max_length=30, blank=True, editable=False)
    currency = models.CharField(max_length=10, default="RWF")
    currency_decimals = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(2)]
    )
    default_language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    receipt_footer = models.TextField(blank=True, default="Thank you for choosing us!")
    receipt_paper = models.CharField(max_length=5, choices=ReceiptPaper.choices, default=ReceiptPaper.THERMAL_80)
    receipt_show_logo = models.BooleanField(default=True)
    upcoming_pickup_days = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(0), MaxValueValidator(60)]
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "business settings"
        verbose_name_plural = "business settings"

    def __str__(self):
        return self.business_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(singleton=True)
        return obj


class TemplateKey(models.TextChoices):
    ORDER_RECEIVED = "ORDER_RECEIVED", "Order received"
    ORDER_READY = "ORDER_READY", "Clothes ready for pickup"
    PICKUP_REMINDER = "PICKUP_REMINDER", "Upcoming pickup reminder"
    PAYMENT_REMINDER = "PAYMENT_REMINDER", "Outstanding payment reminder"


class WhatsAppTemplate(UUIDModel):
    key = models.CharField(max_length=30, choices=TemplateKey.choices)
    language = models.CharField(max_length=5, choices=Language.choices)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["key", "language"]
        constraints = [
            models.UniqueConstraint(fields=["key", "language"], name="unique_template_per_language"),
        ]

    def __str__(self):
        return f"{self.key} ({self.language})"
