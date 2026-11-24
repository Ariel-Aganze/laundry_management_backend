from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.common.models import UUIDModel


class AuditAction(models.TextChoices):
    LOGIN = "LOGIN", "Login"
    LOGIN_FAILED = "LOGIN_FAILED", "Failed login"
    LOGOUT = "LOGOUT", "Logout"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
    USER_CREATED = "USER_CREATED", "User created"
    USER_UPDATED = "USER_UPDATED", "User updated"
    USER_ACTIVATED = "USER_ACTIVATED", "User activated"
    USER_DEACTIVATED = "USER_DEACTIVATED", "User deactivated"
    PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
    CUSTOMER_CREATED = "CUSTOMER_CREATED", "Customer registered"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED", "Customer updated"
    CATEGORY_CREATED = "CATEGORY_CREATED", "Category created"
    CATEGORY_UPDATED = "CATEGORY_UPDATED", "Category updated"
    SERVICE_CREATED = "SERVICE_CREATED", "Service item created"
    SERVICE_UPDATED = "SERVICE_UPDATED", "Service item updated"
    PRICE_CHANGED = "PRICE_CHANGED", "Price changed"
    ORDER_CREATED = "ORDER_CREATED", "Order created"
    ORDER_UPDATED = "ORDER_UPDATED", "Order updated"
    ORDER_STATUS_CHANGED = "ORDER_STATUS_CHANGED", "Order status changed"
    ORDER_CANCELLED = "ORDER_CANCELLED", "Order cancelled"
    COLLECTION_APPROVAL_REQUESTED = "COLLECTION_APPROVAL_REQUESTED", "Collection approval requested"
    COLLECTION_APPROVED = "COLLECTION_APPROVED", "Collection with balance approved"
    COLLECTION_REJECTED = "COLLECTION_REJECTED", "Collection with balance rejected"
    PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment recorded"
    PAYMENT_REVERSED = "PAYMENT_REVERSED", "Payment reversed"
    RECEIPT_GENERATED = "RECEIPT_GENERATED", "Receipt generated"
    WHATSAPP_INITIATED = "WHATSAPP_INITIATED", "WhatsApp message initiated"
    SETTINGS_UPDATED = "SETTINGS_UPDATED", "Settings updated"
    TEMPLATE_UPDATED = "TEMPLATE_UPDATED", "Message template updated"


class AuditLog(UUIDModel):
    """Append-only record of significant actions. Never edited or deleted by the app."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=40, choices=AuditAction.choices, db_index=True)
    entity_type = models.CharField(max_length=50, blank=True, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)
    description = models.TextField(blank=True)
    old_values = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    new_values = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit log entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit log entries cannot be deleted.")
