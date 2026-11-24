import uuid

from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DailySequence(models.Model):
    """
    Database-backed counter used to build human-readable references
    (e.g. LND-20261123-0001, RCP-20261123-0001). Rows are locked with
    SELECT ... FOR UPDATE so concurrent cashiers never get the same number.
    """

    key = models.CharField(max_length=20)
    date = models.DateField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "date"], name="unique_daily_sequence"),
        ]

    def __str__(self):
        return f"{self.key} {self.date}: {self.last_number}"
