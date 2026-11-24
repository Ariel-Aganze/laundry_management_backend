from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import ServiceCategory, ServiceItem

DEMO_CATALOG = {
    "Clothing": [
        ("Shirt", 1000, 1500),
        ("Trousers", 1500, 2000),
        ("Suit", 4000, 5500),
        ("Dress", 2000, 3000),
        ("Jacket", 2500, 3500),
    ],
    "Bedding": [
        ("Bedsheet", 2000, 3000),
        ("Blanket", 4000, 5500),
        ("Duvet", 6000, 8000),
    ],
    "Household items": [
        ("Curtain", 3000, 4500),
        ("Table cloth", 1500, 2000),
    ],
    "Special garments": [
        ("Wedding dress", 15000, 20000),
        ("Traditional attire", 5000, 7000),
    ],
}


class Command(BaseCommand):
    help = "Create demonstration categories and service items (safe to run twice)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for order, (category_name, items) in enumerate(DEMO_CATALOG.items()):
            category, _ = ServiceCategory.objects.get_or_create(
                name=category_name, defaults={"display_order": order}
            )
            for position, (name, normal, express) in enumerate(items):
                _, was_created = ServiceItem.objects.get_or_create(
                    category=category,
                    name=name,
                    defaults={
                        "normal_price": Decimal(normal),
                        "express_price": Decimal(express),
                        "display_order": position,
                    },
                )
                created += was_created
        self.stdout.write(self.style.SUCCESS(f"Demo catalog ready ({created} new items)."))
