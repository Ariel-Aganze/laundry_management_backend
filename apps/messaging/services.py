from urllib.parse import quote

from apps.audit.models import AuditAction
from apps.audit.services import log_activity
from apps.business.defaults import DEFAULT_TEMPLATES
from apps.business.models import BusinessSettings, WhatsAppTemplate
from apps.common.i18n import format_date, format_money, normalize_language

from .models import WhatsAppMessageLog


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def build_context(order, lang):
    business = BusinessSettings.load()

    def money(value):
        return format_money(value, business.currency, business.currency_decimals)

    return {
        "customer_name": order.customer.full_name,
        "reference": order.reference,
        "drop_off_date": format_date(order.drop_off_date, lang),
        "pickup_date": format_date(order.pickup_date, lang),
        "total_quantity": order.total_quantity,
        "total": money(order.total_amount),
        "amount_paid": money(order.amount_paid),
        "balance": money(order.balance),
        "business_name": business.business_name,
        "business_phone": business.phone_number,
    }


def template_body(key, lang):
    template = WhatsAppTemplate.objects.filter(key=key, language=lang).first()
    if template:
        return template.body
    return DEFAULT_TEMPLATES.get(key, {}).get(lang) or DEFAULT_TEMPLATES.get(key, {}).get("en", "")


def render_message(order, key, lang=None):
    lang = normalize_language(lang or order.customer.preferred_language)
    return template_body(key, lang).format_map(_SafeDict(build_context(order, lang))), lang


def whatsapp_url(phone_number, message):
    return f"https://wa.me/{phone_number.lstrip('+')}?text={quote(message)}"


def initiate_message(*, order, user, key, lang, message, request=None):
    customer = order.customer
    entry = WhatsAppMessageLog.objects.create(
        order=order,
        customer=customer,
        template_key=key,
        language=lang,
        phone_number=customer.phone_number,
        message=message,
        initiated_by=user,
    )
    log_activity(
        AuditAction.WHATSAPP_INITIATED,
        request=request,
        user=user,
        entity=order,
        description=f"Opened WhatsApp ({key}) for {customer.full_name} on {order.reference}. Delivery not confirmed.",
    )
    return entry
