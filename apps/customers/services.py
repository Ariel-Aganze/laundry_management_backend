from apps.audit.models import AuditAction
from apps.audit.services import log_activity, snapshot

from .models import Customer

CUSTOMER_AUDIT_FIELDS = ["full_name", "phone_number", "preferred_language", "notes"]


def create_customer(*, data, user, request=None):
    """Create a customer from validated serializer data and audit it."""
    from apps.business.models import BusinessSettings

    data = dict(data)
    data.pop("allow_duplicate", None)
    data.setdefault("preferred_language", BusinessSettings.load().default_language)
    customer = Customer.objects.create(created_by=user, **data)
    log_activity(
        AuditAction.CUSTOMER_CREATED,
        request=request,
        user=user,
        entity=customer,
        description=f"Registered customer {customer.full_name} ({customer.phone_number}).",
        new_values=snapshot(customer, CUSTOMER_AUDIT_FIELDS),
    )
    return customer
