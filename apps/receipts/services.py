import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import log_activity
from apps.common.sequences import next_sequence_value

from .models import Receipt, ReceiptType


def generate_receipt_number(on_date=None):
    on_date = on_date or timezone.localdate()
    number = next_sequence_value("RECEIPT", on_date)
    return f"RCP-{on_date:%Y%m%d}-{number:04d}"


def build_receipt_data(*, order, receipt_number, receipt_type, user, payment=None):
    from apps.business.models import BusinessSettings

    business = BusinessSettings.load()
    items = list(order.items.all())
    data = {
        "receipt_number": receipt_number,
        "receipt_type": receipt_type,
        "generated_at": timezone.now(),
        "generated_by": user.full_name,
        "business": {
            "name": business.business_name,
            "phone": business.phone_number,
            "address": business.address,
            "email": business.email,
            "footer": business.receipt_footer,
            "currency": business.currency,
            "currency_decimals": business.currency_decimals,
        },
        "order": {
            "id": str(order.id),
            "reference": order.reference,
            "drop_off_date": order.drop_off_date,
            "pickup_date": order.pickup_date,
            "created_at": order.created_at,
            "status": order.status,
        },
        "customer": {"name": order.customer.full_name, "phone": order.customer.phone_number},
        "items": [
            {
                "category": item.category_name_snapshot,
                "item": item.item_name_snapshot,
                "service_type": item.service_type,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "is_free": item.is_free,
                "condition_notes": item.condition_notes,
            }
            for item in items
        ],
        "total_quantity": order.total_quantity,
        "total_amount": order.total_amount,
        "amount_paid": order.amount_paid,
        "balance": order.balance,
        "payment_status": order.payment_status,
        "payment": (
            {
                "amount": payment.amount,
                "payment_method": payment.payment_method,
                "method_other": payment.method_other,
                "transaction_reference": payment.transaction_reference,
                "received_at": payment.received_at,
                "received_by": payment.received_by.full_name,
            }
            if payment is not None
            else None
        ),
    }
    # Store plain JSON (decimals/dates as strings) so fresh and reloaded receipts look identical.
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


@transaction.atomic
def generate_receipt(*, order, user, receipt_type=ReceiptType.ORDER, payment=None, request=None):
    number = generate_receipt_number()
    receipt = Receipt.objects.create(
        order=order,
        payment=payment,
        receipt_number=number,
        receipt_type=receipt_type,
        data=build_receipt_data(
            order=order, receipt_number=number, receipt_type=receipt_type, user=user, payment=payment
        ),
        generated_by=user,
    )
    log_activity(
        AuditAction.RECEIPT_GENERATED,
        request=request,
        user=user,
        entity=receipt,
        description=f"Generated {receipt.get_receipt_type_display().lower()} {number} for {order.reference}.",
    )
    return receipt
