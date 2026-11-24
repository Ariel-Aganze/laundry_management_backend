from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

ZERO = Decimal("0.00")

MONEY_KWARGS = {"max_digits": 14, "decimal_places": 2}


def MoneyField(**kwargs):  # noqa: N802 - behaves like a field class
    """DecimalField(max_digits=14, decimal_places=2) - never floats for money."""
    options = {**MONEY_KWARGS, "default": ZERO, "validators": [MinValueValidator(ZERO)]}
    options.update(kwargs)
    return models.DecimalField(**options)
