import re

from rest_framework.exceptions import ValidationError

_STRIP = re.compile(r"[\s\-\.\(\)/]")


def normalize_phone(value):
    """
    Normalise a phone number typed with its country code into E.164 form.

    "+250 788 123 456" -> "+250788123456"
    "00243 81 234 5678" -> "+243812345678"

    Numbers must include the country code so WhatsApp links work for customers
    from any country.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValidationError("Phone number is required.", code="required")

    cleaned = _STRIP.sub("", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        raise ValidationError(
            "Include the country code, for example +250788123456.",
            code="phone_missing_country_code",
        )

    digits = cleaned[1:]
    if not digits.isdigit() or not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValidationError("Enter a valid phone number with country code.", code="invalid_phone")
    return "+" + digits


def phone_search_fragment(term):
    """Digits (and leading +) from a search term, for partial phone matching."""
    fragment = re.sub(r"[^\d+]", "", term or "")
    return fragment if len(fragment.lstrip("+")) >= 3 else ""
