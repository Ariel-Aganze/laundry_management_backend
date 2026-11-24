from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.common.fields import MoneyField
from apps.common.models import TimeStampedModel


class ServiceCategory(TimeStampedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "service categories"
        constraints = [models.UniqueConstraint(Lower("name"), name="unique_category_name_ci")]

    def __str__(self):
        return self.name


class ServiceItem(TimeStampedModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    normal_price = MoneyField()
    express_price = MoneyField()
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category__display_order", "category__name", "display_order", "name"]
        constraints = [
            models.UniqueConstraint("category", Lower("name"), name="unique_item_name_per_category_ci"),
            models.CheckConstraint(condition=Q(normal_price__gte=0), name="service_normal_price_gte_0"),
            models.CheckConstraint(condition=Q(express_price__gte=0), name="service_express_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.category.name} / {self.name}"

    @property
    def is_orderable(self):
        return self.is_active and self.category.is_active

    def price_for(self, service_type):
        return self.express_price if service_type == "EXPRESS" else self.normal_price
