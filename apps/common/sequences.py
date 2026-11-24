from django.db import IntegrityError, transaction

from .models import DailySequence


def next_sequence_value(key, on_date):
    """
    Return the next number for (key, date). Must be called inside a transaction;
    the sequence row stays locked until that transaction ends.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_sequence_value() must run inside transaction.atomic().")

    try:
        with transaction.atomic():
            DailySequence.objects.get_or_create(key=key, date=on_date)
    except IntegrityError:
        # Another transaction created the row at the same time; it exists now.
        pass

    sequence = DailySequence.objects.select_for_update().get(key=key, date=on_date)
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    return sequence.last_number
