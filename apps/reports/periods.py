from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

PERIODS = ("today", "yesterday", "last_7_days", "last_30_days", "this_month", "last_month", "custom")
MAX_CUSTOM_DAYS = 366 * 3


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date  # inclusive

    @property
    def bounds(self):
        """Aware datetimes [start, end) in the business time zone."""
        tz = timezone.get_current_timezone()
        return (
            timezone.make_aware(datetime.combine(self.start, time.min), tz),
            timezone.make_aware(datetime.combine(self.end + timedelta(days=1), time.min), tz),
        )

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def as_dict(self):
        return {"period": self.key, "start": self.start.isoformat(), "end": self.end.isoformat()}


def _parse(value, name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError({name: ["Use the format YYYY-MM-DD."]}, code="invalid_date")


def resolve_period(params, default="today"):
    key = (params.get("period") or default).lower()
    today = timezone.localdate()
    if key == "today":
        start = end = today
    elif key == "yesterday":
        start = end = today - timedelta(days=1)
    elif key == "last_7_days":
        start, end = today - timedelta(days=6), today
    elif key == "last_30_days":
        start, end = today - timedelta(days=29), today
    elif key == "this_month":
        start, end = today.replace(day=1), today
    elif key == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif key == "custom":
        if not params.get("start") or not params.get("end"):
            raise ValidationError({"period": ["A custom period needs start and end dates."]}, code="required")
        start, end = _parse(params.get("start"), "start"), _parse(params.get("end"), "end")
        if start > end:
            raise ValidationError({"end": ["The end date must be after the start date."]}, code="invalid_range")
        if (end - start).days > MAX_CUSTOM_DAYS:
            raise ValidationError({"end": ["The period is too long (max 3 years)."]}, code="invalid_range")
    else:
        raise ValidationError({"period": [f"Use one of: {', '.join(PERIODS)}."]}, code="invalid_choice")
    return Period(key, start, end)


# ---- Time-series buckets ------------------------------------------------------------
def auto_group(period):
    if period.days <= 62:
        return "day"
    if period.days <= 182:
        return "week"
    return "month"


def bucket_start(day, group):
    if group == "week":
        return day - timedelta(days=day.weekday())
    if group == "month":
        return day.replace(day=1)
    return day


def iter_buckets(period, group):
    current = bucket_start(period.start, group)
    while current <= period.end:
        yield current
        if group == "day":
            current += timedelta(days=1)
        elif group == "week":
            current += timedelta(days=7)
        else:
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def resolve_group(params, period):
    group = (params.get("group_by") or "auto").lower()
    if group == "auto":
        return auto_group(period)
    if group not in ("day", "week", "month"):
        raise ValidationError({"group_by": ["Use day, week, month or auto."]}, code="invalid_choice")
    return group
