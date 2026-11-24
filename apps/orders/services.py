"""
Order business logic. Every financial value is computed here, on the server,
inside database transactions (SRS 2.3, BR-009, 5.1).
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.models import AuditAction
from apps.audit.services import diff, log_activity
from apps.common.exceptions import BusinessRuleError
from apps.common.fields import ZERO
from apps.common.sequences import next_sequence_value

from .models import CLOSED_STATUSES, CollectionApproval, Order, OrderItem, OrderStatus, PaymentStatus

# Allowed manual status transitions (cancellation has its own endpoint).
STATUS_TRANSITIONS = {
    OrderStatus.RECEIVED: {OrderStatus.PROCESSING, OrderStatus.READY, OrderStatus.COLLECTED},
    OrderStatus.PROCESSING: {OrderStatus.RECEIVED, OrderStatus.READY, OrderStatus.COLLECTED},
    OrderStatus.READY: {OrderStatus.PROCESSING, OrderStatus.COLLECTED},
    OrderStatus.COLLECTED: {OrderStatus.READY},  # Admin only: undo a mistaken collection
    OrderStatus.CANCELLED: set(),
}


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def generate_order_reference(on_date=None):
    on_date = on_date or timezone.localdate()
    for _ in range(10):
        number = next_sequence_value("ORDER", on_date)
        reference = f"LND-{on_date:%Y%m%d}-{number:04d}"
        if not Order.objects.filter(reference=reference).exists():
            return reference
    raise BusinessRuleError("Could not generate a unique order reference.", code="reference_generation_failed")


def compute_payment_status(total, paid):
    if total <= ZERO or paid >= total:
        return PaymentStatus.PAID
    if paid <= ZERO:
        return PaymentStatus.UNPAID
    return PaymentStatus.PARTIALLY_PAID


def build_order_item(order, *, service_item, service_type, quantity, condition_notes=""):
    """Create an (unsaved) OrderItem with the price copied from the catalog (BR-007)."""
    unit_price = service_item.price_for(service_type)
    return OrderItem(
        order=order,
        service_item=service_item,
        category=service_item.category,
        item_name_snapshot=service_item.name,
        category_name_snapshot=service_item.category.name,
        service_type=service_type,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=unit_price * quantity,
        condition_notes=(condition_notes or "").strip(),
    )


def recalculate_totals(order):
    totals = order.items.aggregate(quantity=Sum("quantity"), amount=Sum("subtotal"))
    order.total_quantity = totals["quantity"] or 0
    order.total_amount = totals["amount"] or ZERO


def refresh_payment_state(order):
    """Recalculate amount paid, balance (B = T - P) and payment status from valid payments."""
    paid = order.payments.valid().aggregate(total=Sum("amount"))["total"] or ZERO
    order.amount_paid = paid
    order.balance = max(order.total_amount - paid, ZERO)
    order.payment_status = compute_payment_status(order.total_amount, paid)


def order_audit_snapshot(order):
    return {
        "customer": str(order.customer_id),
        "drop_off_date": order.drop_off_date,
        "pickup_date": order.pickup_date,
        "notes": order.notes,
        "status": order.status,
        "total_quantity": order.total_quantity,
        "total_amount": order.total_amount,
        "amount_paid": order.amount_paid,
        "balance": order.balance,
        "items": [
            {
                "id": str(item.id),
                "item": item.item_name_snapshot,
                "category": item.category_name_snapshot,
                "service_type": item.service_type,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "condition_notes": item.condition_notes,
            }
            for item in order.items.all()
        ],
    }


def _lock(order):
    return Order.objects.select_for_update().get(pk=order.pk)


def _ensure_orderable(service_item):
    if not service_item.is_orderable:
        raise BusinessRuleError(
            f"'{service_item.name}' is not available for new orders.", code="inactive_service"
        )


def _validate_dates(drop_off_date, pickup_date):
    if pickup_date < drop_off_date:
        raise BusinessRuleError(
            "The pickup date cannot be earlier than the drop-off date.", code="pickup_before_dropoff"
        )


# --------------------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------------------
@transaction.atomic
def create_order(
    *,
    user,
    items,
    pickup_date,
    customer=None,
    new_customer=None,
    drop_off_date=None,
    notes="",
    payment=None,
    request=None,
):
    """
    Create an order with its items, an optional first payment and the order receipt
    in one transaction. Returns (order, receipt).
    """
    from apps.customers.services import create_customer
    from apps.payments.services import record_payment
    from apps.receipts.models import ReceiptType
    from apps.receipts.services import generate_receipt

    if not items:
        raise BusinessRuleError("An order must contain at least one item.", code="no_items")
    if customer is None:
        if not new_customer:
            raise BusinessRuleError("An order must have a customer.", code="customer_required")
        customer = create_customer(data=new_customer, user=user, request=request)

    drop_off_date = drop_off_date or timezone.localdate()
    _validate_dates(drop_off_date, pickup_date)
    for entry in items:
        _ensure_orderable(entry["service_item"])

    order = Order.objects.create(
        reference=generate_order_reference(),
        customer=customer,
        drop_off_date=drop_off_date,
        pickup_date=pickup_date,
        notes=(notes or "").strip(),
        created_by=user,
    )
    OrderItem.objects.bulk_create(
        [
            build_order_item(
                order,
                service_item=entry["service_item"],
                service_type=entry["service_type"],
                quantity=entry["quantity"],
                condition_notes=entry.get("condition_notes", ""),
            )
            for entry in items
        ]
    )
    recalculate_totals(order)
    refresh_payment_state(order)
    order.save()

    log_activity(
        AuditAction.ORDER_CREATED,
        request=request,
        user=user,
        entity=order,
        description=(
            f"Created order {order.reference} for {customer.full_name}: "
            f"{order.total_quantity} item(s), total {order.total_amount}."
        ),
        new_values=order_audit_snapshot(order),
    )

    if payment and Decimal(payment.get("amount") or 0) > ZERO:
        record_payment(order=order, user=user, request=request, generate_receipt=False, **payment)
        order.refresh_from_db()

    receipt = generate_receipt(order=order, user=user, receipt_type=ReceiptType.ORDER, request=request)
    return order, receipt


# --------------------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------------------
ADMIN_ONLY_UPDATE_FIELDS = {"customer", "drop_off_date", "items"}


def _replace_items(order, items_data):
    existing = {item.id: item for item in order.items.select_related("service_item__category")}
    keep = set()
    for entry in items_data:
        item_id = entry.get("id")
        service_item = entry["service_item"]
        service_type = entry["service_type"]
        if item_id:
            item = existing.get(item_id)
            if item is None:
                raise BusinessRuleError("An item does not belong to this order.", code="invalid_item")
            keep.add(item_id)
            if item.service_item_id != service_item.pk or item.service_type != service_type:
                # Different service / type: price comes from the current catalog.
                fresh = build_order_item(order, service_item=service_item, service_type=service_type, quantity=1)
                for field in (
                    "service_item",
                    "category",
                    "item_name_snapshot",
                    "category_name_snapshot",
                    "service_type",
                    "unit_price",
                ):
                    setattr(item, field, getattr(fresh, field))
            # Same service & type: keep the historical unit price (BR-008).
            item.quantity = entry["quantity"]
            item.subtotal = item.unit_price * item.quantity
            if "condition_notes" in entry:
                item.condition_notes = (entry.get("condition_notes") or "").strip()
            item.save()
        else:
            _ensure_orderable(service_item)
            build_order_item(
                order,
                service_item=service_item,
                service_type=service_type,
                quantity=entry["quantity"],
                condition_notes=entry.get("condition_notes", ""),
            ).save()
    removed = [pk for pk in existing if pk not in keep]
    if removed:
        order.items.filter(pk__in=removed).delete()
    if not order.items.exists():
        raise BusinessRuleError("An order must contain at least one item.", code="no_items")


@transaction.atomic
def update_order(*, order, user, data, request=None):
    """
    Cashiers may change: notes, pickup_date, item condition notes.
    Admins may additionally change: customer, drop_off_date, items (with prices recalculated).
    """
    from apps.receipts.models import ReceiptType
    from apps.receipts.services import generate_receipt

    order = _lock(order)
    if order.status == OrderStatus.CANCELLED:
        raise BusinessRuleError("Cancelled orders cannot be modified.", code="order_cancelled")
    if not user.is_admin and ADMIN_ONLY_UPDATE_FIELDS & set(data):
        raise PermissionDenied("Only an administrator can change the customer, drop-off date or items.")

    before = order_audit_snapshot(order)

    for field in ("customer", "drop_off_date", "pickup_date", "notes"):
        if field in data:
            value = data[field]
            setattr(order, field, value.strip() if isinstance(value, str) else value)
    _validate_dates(order.drop_off_date, order.pickup_date)

    items_changed = False
    if "items" in data:
        if order.status == OrderStatus.COLLECTED:
            raise BusinessRuleError("Items of a collected order cannot be changed.", code="order_collected")
        _replace_items(order, data["items"])
        recalculate_totals(order)
        if order.total_amount < order.amount_paid:
            raise BusinessRuleError(
                "The new total is lower than the amount already paid. Reverse a payment first.",
                code="total_below_paid",
            )
        items_changed = True

    for entry in data.get("item_notes", []):
        updated = order.items.filter(pk=entry["id"]).update(
            condition_notes=(entry.get("condition_notes") or "").strip(), updated_at=timezone.now()
        )
        if not updated:
            raise BusinessRuleError("An item does not belong to this order.", code="invalid_item")

    refresh_payment_state(order)
    order.save()

    old, new = diff(before, order_audit_snapshot(order))
    if new:
        log_activity(
            AuditAction.ORDER_UPDATED,
            request=request,
            user=user,
            entity=order,
            description=f"Updated order {order.reference} ({', '.join(sorted(new))}).",
            old_values=old,
            new_values=new,
        )
    if items_changed and new.get("items") is not None:
        # Corrected order receipt; earlier receipts remain retrievable.
        generate_receipt(order=order, user=user, receipt_type=ReceiptType.ORDER, request=request)
    return order


# --------------------------------------------------------------------------------------
# Status, collection approval, cancellation
# --------------------------------------------------------------------------------------
def _decide_collection(order, user, approve, note):
    order.collection_approval = CollectionApproval.APPROVED if approve else CollectionApproval.REJECTED
    order.collection_decided_by = user
    order.collection_decided_at = timezone.now()
    order.collection_decision_note = (note or "").strip()


@transaction.atomic
def change_status(*, order, new_status, user, approve_balance=False, note="", request=None):
    order = _lock(order)
    old_status = order.status

    if new_status == OrderStatus.CANCELLED:
        raise BusinessRuleError("Use the cancel action to cancel an order.", code="use_cancel_endpoint")
    if old_status == new_status:
        raise BusinessRuleError("The order already has this status.", code="status_unchanged")
    if new_status not in STATUS_TRANSITIONS[old_status]:
        raise BusinessRuleError(
            f"Cannot change status from {old_status} to {new_status}.", code="invalid_status_transition"
        )
    if old_status == OrderStatus.COLLECTED and not user.is_admin:
        raise PermissionDenied("Only an administrator can reopen a collected order.")

    if new_status == OrderStatus.COLLECTED and order.balance > ZERO:
        if order.collection_approval != CollectionApproval.APPROVED:
            if user.is_admin and approve_balance:
                _decide_collection(order, user, True, note)
                log_activity(
                    AuditAction.COLLECTION_APPROVED,
                    request=request,
                    user=user,
                    entity=order,
                    description=f"Approved collection of {order.reference} with balance {order.balance}.",
                    new_values={"balance": order.balance, "note": note},
                )
            else:
                raise BusinessRuleError(
                    f"This order still has an outstanding balance of {order.balance}. "
                    "Collection requires administrator approval.",
                    code="collection_requires_approval",
                    extra={"balance": str(order.balance), "collection_approval": order.collection_approval},
                )

    order.status = new_status
    if new_status == OrderStatus.COLLECTED:
        order.collected_at = timezone.now()
        order.collected_by = user
    elif old_status == OrderStatus.COLLECTED:
        order.collected_at = None
        order.collected_by = None
    order.save()

    log_activity(
        AuditAction.ORDER_STATUS_CHANGED,
        request=request,
        user=user,
        entity=order,
        description=f"Order {order.reference}: {old_status} -> {new_status}.",
        old_values={"status": old_status},
        new_values={"status": new_status, **({"note": note} if note else {})},
    )
    return order


@transaction.atomic
def request_collection_approval(*, order, user, note="", request=None):
    order = _lock(order)
    if order.status in CLOSED_STATUSES:
        raise BusinessRuleError("This order is already closed.", code="order_closed")
    if order.balance <= ZERO:
        raise BusinessRuleError("This order has no outstanding balance.", code="no_balance")
    if order.collection_approval == CollectionApproval.APPROVED:
        raise BusinessRuleError("Collection has already been approved.", code="already_approved")

    order.collection_approval = CollectionApproval.PENDING
    order.collection_requested_by = user
    order.collection_requested_at = timezone.now()
    order.collection_request_note = (note or "").strip()
    order.save()
    log_activity(
        AuditAction.COLLECTION_APPROVAL_REQUESTED,
        request=request,
        user=user,
        entity=order,
        description=f"Requested approval to release {order.reference} with balance {order.balance}.",
        new_values={"balance": order.balance, "note": order.collection_request_note},
    )
    return order


@transaction.atomic
def decide_collection_approval(*, order, user, approve, note="", request=None):
    if not user.is_admin:
        raise PermissionDenied("Only an administrator can approve collection with a balance.")
    order = _lock(order)
    if order.status in CLOSED_STATUSES:
        raise BusinessRuleError("This order is already closed.", code="order_closed")
    if approve and order.balance <= ZERO:
        raise BusinessRuleError("This order has no outstanding balance.", code="no_balance")

    old = order.collection_approval
    _decide_collection(order, user, approve, note)
    order.save()
    log_activity(
        AuditAction.COLLECTION_APPROVED if approve else AuditAction.COLLECTION_REJECTED,
        request=request,
        user=user,
        entity=order,
        description=(
            f"{'Approved' if approve else 'Rejected'} collection of {order.reference} "
            f"with balance {order.balance}."
        ),
        old_values={"collection_approval": old},
        new_values={"collection_approval": order.collection_approval, "note": order.collection_decision_note},
    )
    return order


@transaction.atomic
def cancel_order(*, order, user, reason, request=None):
    if not user.is_admin:
        raise PermissionDenied("Only an administrator can cancel an order.")
    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("A cancellation reason is required.", code="reason_required")
    order = _lock(order)
    if order.status == OrderStatus.CANCELLED:
        raise BusinessRuleError("The order is already cancelled.", code="order_cancelled")
    if order.status == OrderStatus.COLLECTED:
        raise BusinessRuleError("A collected order cannot be cancelled.", code="order_collected")

    old_status = order.status
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancelled_by = user
    order.cancellation_reason = reason
    order.save()
    log_activity(
        AuditAction.ORDER_CANCELLED,
        request=request,
        user=user,
        entity=order,
        description=f"Cancelled order {order.reference}: {reason}",
        old_values={"status": old_status},
        new_values={"status": OrderStatus.CANCELLED, "reason": reason, "amount_paid": order.amount_paid},
    )
    return order
