from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.models import AuditAction
from apps.audit.services import log_activity
from apps.common.exceptions import BusinessRuleError
from apps.common.fields import ZERO

from .models import Payment, PaymentMethod, PaymentState


@transaction.atomic
def record_payment(
    *,
    order,
    amount,
    payment_method,
    user,
    method_other="",
    transaction_reference="",
    notes="",
    request=None,
    generate_receipt=True,
):
    """
    Record a payment against an order (atomic, order row locked).
    Returns (payment, receipt_or_None).
    """
    from apps.orders.models import Order, OrderStatus
    from apps.orders.services import refresh_payment_state

    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise BusinessRuleError("Enter a valid amount.", code="invalid_amount")
    if amount <= ZERO:
        raise BusinessRuleError("The amount must be greater than zero.", code="invalid_amount")
    if payment_method not in PaymentMethod.values:
        raise BusinessRuleError("Select a valid payment method.", code="invalid_payment_method")
    if payment_method == PaymentMethod.OTHER and not (method_other or "").strip():
        raise BusinessRuleError("Specify the payment method.", code="method_other_required")

    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == OrderStatus.CANCELLED:
        raise BusinessRuleError("Payments cannot be recorded on a cancelled order.", code="order_cancelled")
    if amount > order.balance:
        raise BusinessRuleError(
            f"The payment exceeds the outstanding balance of {order.balance}.",
            code="payment_exceeds_balance",
            extra={"balance": str(order.balance)},
        )

    payment = Payment.objects.create(
        order=order,
        amount=amount,
        payment_method=payment_method,
        method_other=(method_other or "").strip() if payment_method == PaymentMethod.OTHER else "",
        transaction_reference=(transaction_reference or "").strip(),
        notes=(notes or "").strip(),
        received_by=user,
    )
    refresh_payment_state(order)
    order.save(update_fields=["amount_paid", "balance", "payment_status", "updated_at"])

    log_activity(
        AuditAction.PAYMENT_RECORDED,
        request=request,
        user=user,
        entity=payment,
        description=(
            f"Recorded {payment.method_display} payment of {amount} on {order.reference}. "
            f"New balance: {order.balance}."
        ),
        new_values={
            "order": order.reference,
            "amount": amount,
            "payment_method": payment_method,
            "transaction_reference": payment.transaction_reference,
            "balance_after": order.balance,
        },
    )

    receipt = None
    if generate_receipt:
        from apps.receipts.models import ReceiptType
        from apps.receipts.services import generate_receipt as make_receipt

        receipt = make_receipt(
            order=order, user=user, receipt_type=ReceiptType.PAYMENT, payment=payment, request=request
        )
    return payment, receipt


@transaction.atomic
def reverse_payment(*, payment, user, reason, request=None):
    """Admin-only correction. The original payment is preserved and marked REVERSED."""
    from apps.orders.models import Order
    from apps.orders.services import refresh_payment_state

    if not user.is_admin:
        raise PermissionDenied("Only an administrator can reverse a payment.")
    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("A reason is required to reverse a payment.", code="reason_required")

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == PaymentState.REVERSED:
        raise BusinessRuleError("This payment has already been reversed.", code="already_reversed")

    payment.status = PaymentState.REVERSED
    payment.reversed_at = timezone.now()
    payment.reversed_by = user
    payment.reversal_reason = reason
    payment.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason"])

    refresh_payment_state(order)
    order.save(update_fields=["amount_paid", "balance", "payment_status", "updated_at"])

    log_activity(
        AuditAction.PAYMENT_REVERSED,
        request=request,
        user=user,
        entity=payment,
        description=f"Reversed payment of {payment.amount} on {order.reference}: {reason}",
        old_values={"status": PaymentState.VALID},
        new_values={"status": PaymentState.REVERSED, "reason": reason, "balance_after": order.balance},
    )
    return payment
