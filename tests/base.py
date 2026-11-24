from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import ServiceCategory, ServiceItem
from apps.customers.models import Customer

PASSWORD = "Str0ng-Passw0rd!"


class APITestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin", password=PASSWORD, role=User.Role.ADMIN, first_name="Ada", last_name="Admin"
        )
        cls.cashier = User.objects.create_user(
            username="cashier", password=PASSWORD, role=User.Role.CASHIER, first_name="Cathy", last_name="Cash",
            email="cathy@example.com",
        )
        cls.clothing = ServiceCategory.objects.create(name="Clothing")
        cls.bedding = ServiceCategory.objects.create(name="Bedding")
        cls.shirt = ServiceItem.objects.create(
            category=cls.clothing, name="Shirt", normal_price=Decimal("1000"), express_price=Decimal("1500")
        )
        cls.trousers = ServiceItem.objects.create(
            category=cls.clothing, name="Trousers", normal_price=Decimal("1500"), express_price=Decimal("2000")
        )
        cls.suit = ServiceItem.objects.create(
            category=cls.clothing, name="Suit", normal_price=Decimal("4000"), express_price=Decimal("5500")
        )
        cls.bedsheet = ServiceItem.objects.create(
            category=cls.bedding, name="Bedsheet", normal_price=Decimal("2000"), express_price=Decimal("3000")
        )
        cls.customer = Customer.objects.create(
            full_name="Jean Mugabo", phone_number="+250788123456", created_by=cls.cashier
        )

    def setUp(self):
        cache.clear()  # reset login throttling between tests

    # ---- helpers ----
    def login_as(self, user):
        self.client.force_authenticate(user=user)

    @property
    def today(self):
        return timezone.localdate()

    def order_payload(self, items=None, pickup_days=2, payment=None, **extra):
        payload = {
            "customer": str(self.customer.id),
            "pickup_date": (self.today + timedelta(days=pickup_days)).isoformat(),
            "items": items
            or [
                {"service_item": str(self.shirt.id), "service_type": "NORMAL", "quantity": 3},
                {"service_item": str(self.trousers.id), "service_type": "NORMAL", "quantity": 2},
                {"service_item": str(self.suit.id), "service_type": "EXPRESS", "quantity": 1},
                {"service_item": str(self.bedsheet.id), "service_type": "NORMAL", "quantity": 2},
            ],
            **extra,
        }
        if payment is not None:
            payload["payment"] = payment
        return payload

    def create_order(self, user=None, **kwargs):
        self.login_as(user or self.cashier)
        response = self.client.post("/api/v1/orders/", self.order_payload(**kwargs), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def pay(self, order_id, amount, method="CASH", user=None):
        self.login_as(user or self.cashier)
        return self.client.post(
            "/api/v1/payments/",
            {"order": order_id, "amount": str(amount), "payment_method": method},
            format="json",
        )
