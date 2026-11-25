"""
Server-side text that ends up on paper or in WhatsApp messages (receipts, dates,
money). The web UI itself is translated by the frontend.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

SUPPORTED_LANGUAGES = ("en", "rw")

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "rw": [
        "Mutarama", "Gashyantare", "Werurwe", "Mata", "Gicurasi", "Kamena",
        "Nyakanga", "Kanama", "Nzeri", "Ukwakira", "Ugushyingo", "Ukuboza",
    ],
}

LABELS = {
    "en": {
        "order_receipt": "ORDER RECEIPT",
        "payment_receipt": "PAYMENT RECEIPT",
        "receipt_no": "Receipt No.",
        "order_ref": "Order Ref.",
        "date": "Date",
        "cashier": "Served by",
        "customer": "Customer",
        "phone": "Phone",
        "drop_off": "Drop-off",
        "pickup": "Pickup",
        "notes": "Notes",
        "total_items": "Total items",
        "total": "TOTAL",
        "paid": "Paid",
        "balance": "BALANCE",
        "payment_status": "Status",
        "this_payment": "PAYMENT DETAILS",
        "amount": "Amount",
        "method": "Method",
        "reference": "Reference",
        "received_at": "Received",
        "thank_you": "Thank you for your business!",
        "tel": "Tel",
        "NORMAL": "Normal",
        "EXPRESS": "Express",
        "CUSTOM": "Custom price",
        "free": "FREE",
        "UNPAID": "Unpaid",
        "PARTIALLY_PAID": "Partially paid",
        "PAID": "Paid",
        "CASH": "Cash",
        "MOBILE_MONEY": "Mobile Money",
        "BANK_TRANSFER": "Bank transfer",
        "CARD": "Card",
        "OTHER": "Other",
    },
    "rw": {
        "order_receipt": "INYEMEZABUGUZI",
        "payment_receipt": "INYEMEZABWISHYU",
        "receipt_no": "Nomero y'inyemezabuguzi",
        "order_ref": "Nomero y'itumiza",
        "date": "Itariki",
        "cashier": "Yakiriwe na",
        "customer": "Umukiriya",
        "phone": "Telefoni",
        "drop_off": "Yakiriwe",
        "pickup": "Kuyafata",
        "notes": "Icyitonderwa",
        "total_items": "Umubare w'ibintu",
        "total": "IGITERANYO",
        "paid": "Byishyuwe",
        "balance": "IBISIGAYE",
        "payment_status": "Uko byishyuwe",
        "this_payment": "IBYEREKEYE KWISHYURA",
        "amount": "Amafaranga",
        "method": "Uburyo",
        "reference": "Nomero",
        "received_at": "Byakiriwe",
        "thank_you": "Murakoze kutugana!",
        "tel": "Tel",
        "NORMAL": "Bisanzwe",
        "EXPRESS": "Byihuse",
        "CUSTOM": "Igiciro cyihariye",
        "free": "KU BUNTU",
        "UNPAID": "Ntibyishyuwe",
        "PARTIALLY_PAID": "Byishyuwe igice",
        "PAID": "Byishyuwe byose",
        "CASH": "Amafaranga mu ntoki",
        "MOBILE_MONEY": "Mobile Money",
        "BANK_TRANSFER": "Banki",
        "CARD": "Ikarita",
        "OTHER": "Ubundi buryo",
    },
}


def normalize_language(lang):
    lang = (lang or "en").lower()[:2]
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def label(key, lang="en"):
    return LABELS[normalize_language(lang)].get(key, LABELS["en"].get(key, key))


def _to_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def format_date(value, lang="en"):
    d = _to_date(value)
    if d is None:
        return ""
    lang = normalize_language(lang)
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def format_datetime(value, lang="en"):
    if value is None or value == "":
        return ""
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return f"{format_date(value, lang)} {value:%H:%M}"


def format_money(amount, currency="RWF", decimals=0):
    amount = Decimal(str(amount if amount not in (None, "") else "0"))
    decimals = max(0, min(int(decimals or 0), 2))
    quantum = Decimal(1).scaleb(-decimals)
    amount = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{currency} {amount:,.{decimals}f}"
