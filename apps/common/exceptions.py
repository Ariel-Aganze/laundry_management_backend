"""
Uniform error format for the API.

Every error response looks like:

    {
        "detail": "Human readable message (English)",
        "code": "stable_machine_code",
        "errors": {"field": [{"message": "...", "code": "..."}]},   # validation only
        ...extra keys for some business errors (e.g. "balance")
    }

The frontend translates messages using `code` (English / Kinyarwanda) and falls back
to `detail` / `message` when it does not know a code.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessRuleError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This operation violates a business rule."
    default_code = "business_rule_violation"

    def __init__(self, detail=None, code=None, extra=None, status_code=None):
        super().__init__(detail=detail, code=code)
        self.extra = extra or {}
        if status_code is not None:
            self.status_code = status_code


class ConflictError(BusinessRuleError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class InvalidCredentials(APIException):
    """401 for failed logins (kept separate from AuthenticationFailed on purpose)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Invalid username/email or password."
    default_code = "invalid_credentials"


def _first_message(full_details):
    if isinstance(full_details, dict):
        if "message" in full_details and isinstance(full_details.get("message"), str):
            return full_details["message"]
        for value in full_details.values():
            message = _first_message(value)
            if message:
                return message
    elif isinstance(full_details, list):
        for value in full_details:
            message = _first_message(value)
            if message:
                return message
    return None


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        exc = ValidationError(detail=detail)
    elif isinstance(exc, ProtectedError):
        exc = BusinessRuleError(
            "This record is linked to other records and cannot be deleted.", code="protected"
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        full = exc.get_full_details()
        if isinstance(full, list):
            full = {"non_field_errors": full}
        payload = {
            "detail": _first_message(full) or "Please correct the highlighted fields.",
            "code": "validation_error",
            "errors": full,
        }
    else:
        full = exc.get_full_details() if hasattr(exc, "get_full_details") else None
        if isinstance(full, dict) and "message" in full:
            payload = {"detail": str(full["message"]), "code": full.get("code") or "error"}
        else:
            payload = {"detail": str(getattr(exc, "detail", "Error")), "code": "error"}
        payload.update(getattr(exc, "extra", {}) or {})

    response.data = payload
    return response
