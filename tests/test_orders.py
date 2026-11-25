from datetime import timedelta
from decimal import Decimal

from apps.audit.models import AuditAction, AuditLog
from apps.customers.models import Customer
from apps.orders.models import Order

from .base import APITestBase


class CustomerTests(APITestBase):
    def test_phone_requires_country_code_and_is_normalized(self):
        self.login_as(self.cashier)
        bad = self.client.post("/api/v1/customers/", {"full_name": "A B", "phone_number": "0788000000"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.data["errors"]["phone_number"][0]["code"], "phone_missing_country_code")

        ok = self.client.post("/api/v1/customers/", {"full_name": "Amani  Bisimwa", "phone_number": "+243 81 234 5678"})
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(ok.data["phone_number"], "+243812345678")
        self.assertEqual(ok.data["full_name"], "Amani Bisimwa")

    def test_duplicate_phone_returns_existing_customer(self):
        self.login_as(self.cashier)
        response = self.client.post("/api/v1/customers/", {"full_name": "Other", "phone_number": "+250 788 123 456"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "duplicate_phone")
        self.assertEqual(response.data["existing_customer"]["id"], str(self.customer.id))

    def test_only_admin_changes_phone(self):
        self.login_as(self.cashier)
        url = f"/api/v1/customers/{self.customer.id}/"
        self.assertEqual(self.client.patch(url, {"phone_number": "+250788999999"}).status_code, 400)
        self.login_as(self.admin)
        self.assertEqual(self.client.patch(url, {"phone_number": "+250788999999"}).status_code, 200)

    def test_search_by_name_and_phone(self):
        self.login_as(self.cashier)
        self.assertEqual(self.client.get("/api/v1/customers/?search=mugabo").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/customers/?search=0788 123").data["count"], 1)


class OrderCreationTests(APITestBase):
    def test_multi_item_order_totals_and_reference(self):
        order = self.create_order()
        # 3*1000 + 2*1500 + 1*5500 (express) + 2*2000 = 15,500 ; quantity 8
        self.assertEqual(Decimal(order["total_amount"]), Decimal("15500"))
        self.assertEqual(order["total_quantity"], 8)
        self.assertEqual(order["payment_status"], "UNPAID")
        self.assertEqual(Decimal(order["balance"]), Decimal("15500"))
        self.assertRegex(order["reference"], rf"^LND-{self.today:%Y%m%d}-0001$")
        self.assertEqual(order["receipt"]["receipt_type"], "ORDER")
        suit = next(i for i in order["items"] if i["item_name_snapshot"] == "Suit")
        self.assertEqual(Decimal(suit["unit_price"]), Decimal("5500"))

    def test_references_are_unique_and_sequential(self):
        refs = {self.create_order()["reference"] for _ in range(3)}
        self.assertEqual(len(refs), 3)
        self.assertIn(f"LND-{self.today:%Y%m%d}-0003", refs)

    def test_client_prices_are_ignored(self):
        items = [{"service_item": str(self.shirt.id), "quantity": 1, "unit_price": "1"}]
        order = self.create_order(items=items)
        self.assertEqual(Decimal(order["total_amount"]), Decimal("1000"))

    def test_historical_price_preserved(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2}])
        self.login_as(self.admin)
        self.client.patch(f"/api/v1/services/{self.shirt.id}/", {"normal_price": "9999"}, format="json")
        detail = self.client.get(f"/api/v1/orders/{order['id']}/").data
        self.assertEqual(Decimal(detail["items"][0]["unit_price"]), Decimal("1000"))
        self.assertEqual(Decimal(detail["total_amount"]), Decimal("2000"))
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.PRICE_CHANGED).exists())

    def test_validation_rules(self):
        self.login_as(self.cashier)
        url = "/api/v1/orders/"
        # pickup before drop-off
        bad_date = self.order_payload(pickup_days=-1)
        self.assertEqual(self.client.post(url, bad_date, format="json").status_code, 400)
        # quantity zero
        zero = self.order_payload(items=[{"service_item": str(self.shirt.id), "quantity": 0}])
        self.assertEqual(self.client.post(url, zero, format="json").status_code, 400)
        # no items
        self.assertEqual(self.client.post(url, self.order_payload(items=[]) | {"items": []}, format="json").status_code, 400)
        # inactive service
        self.shirt.is_active = False
        self.shirt.save()
        inactive = self.order_payload(items=[{"service_item": str(self.shirt.id), "quantity": 1}])
        self.assertEqual(self.client.post(url, inactive, format="json").status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_inline_new_customer_and_initial_payment(self):
        self.login_as(self.cashier)
        payload = self.order_payload(
            items=[{"service_item": str(self.shirt.id), "quantity": 2}],
            payment={"amount": "500", "payment_method": "MOBILE_MONEY", "transaction_reference": "MP123"},
        )
        payload.pop("customer")
        payload["new_customer"] = {"full_name": "Grace Uwase", "phone_number": "+256 700 111222"}
        response = self.client.post("/api/v1/orders/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_status"], "PARTIALLY_PAID")
        self.assertEqual(Decimal(response.data["balance"]), Decimal("1500"))
        self.assertEqual(response.data["receipt"]["data"]["amount_paid"], "500.00")
        self.assertTrue(Customer.objects.filter(phone_number="+256700111222").exists())

    def test_initial_payment_above_total_rolls_back_everything(self):
        self.login_as(self.cashier)
        payload = self.order_payload(
            items=[{"service_item": str(self.shirt.id), "quantity": 1}],
            payment={"amount": "5000", "payment_method": "CASH"},
        )
        response = self.client.post("/api/v1/orders/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "payment_exceeds_balance")
        self.assertEqual(Order.objects.count(), 0)

    def test_search_and_filters(self):
        order = self.create_order()
        self.login_as(self.cashier)
        self.assertEqual(self.client.get(f"/api/v1/orders/search/?q={order['reference']}").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/orders/?search=Jean").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/orders/?service_type=EXPRESS").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/orders/?payment_status=PAID").data["count"], 0)


class OrderEditingTests(APITestBase):
    def test_cashier_may_only_edit_permitted_fields(self):
        order = self.create_order()
        url = f"/api/v1/orders/{order['id']}/"
        self.login_as(self.cashier)
        new_pickup = (self.today + timedelta(days=5)).isoformat()
        self.assertEqual(self.client.patch(url, {"pickup_date": new_pickup}, format="json").status_code, 200)
        item_id = order["items"][0]["id"]
        response = self.client.patch(
            url, {"item_notes": [{"id": item_id, "condition_notes": "Stain on collar"}]}, format="json"
        )
        self.assertEqual(response.data["items"][0]["condition_notes"], "Stain on collar")
        items = [{"service_item": str(self.shirt.id), "quantity": 1}]
        self.assertEqual(self.client.patch(url, {"items": items}, format="json").status_code, 403)

    def test_admin_item_correction_recalculates_and_keeps_old_price(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2}])
        self.shirt.normal_price = Decimal("1200")
        self.shirt.save()
        item_id = order["items"][0]["id"]
        self.login_as(self.admin)
        response = self.client.patch(
            f"/api/v1/orders/{order['id']}/",
            {"items": [
                {"id": item_id, "service_item": str(self.shirt.id), "quantity": 3},
                {"service_item": str(self.bedsheet.id), "quantity": 1},
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        # 3 x 1000 (historical) + 1 x 2000
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("5000"))
        self.assertEqual(len(response.data["receipts"]), 2)  # corrected receipt added
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.ORDER_UPDATED).exists())


class StatusAndCollectionTests(APITestBase):
    def status(self, order_id, new_status, user, **extra):
        self.login_as(user)
        return self.client.post(f"/api/v1/orders/{order_id}/status/", {"status": new_status, **extra}, format="json")

    def test_collection_with_balance_requires_admin_approval(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 1}])
        self.assertEqual(self.status(order["id"], "READY", self.cashier).status_code, 200)

        blocked = self.status(order["id"], "COLLECTED", self.cashier)
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.data["code"], "collection_requires_approval")

        self.login_as(self.cashier)
        req = self.client.post(f"/api/v1/orders/{order['id']}/request-collection/", {"note": "Will pay Friday"})
        self.assertEqual(req.data["collection_approval"], "PENDING")
        # cashier cannot approve
        self.assertEqual(
            self.client.post(f"/api/v1/orders/{order['id']}/decide-collection/", {"decision": "approve"}).status_code,
            403,
        )
        self.login_as(self.admin)
        self.client.post(f"/api/v1/orders/{order['id']}/decide-collection/", {"decision": "approve"})

        done = self.status(order["id"], "COLLECTED", self.cashier)
        self.assertEqual(done.status_code, 200, done.data)
        self.assertIsNotNone(done.data["collected_at"])
        self.assertEqual(done.data["collected_by_name"], "Cathy Cash")

    def test_paid_order_collects_without_approval(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 1}])
        self.pay(order["id"], 1000)
        self.assertEqual(self.status(order["id"], "COLLECTED", self.cashier).status_code, 200)

    def test_admin_can_approve_inline(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 1}])
        response = self.status(order["id"], "COLLECTED", self.admin, approve_balance=True, note="Trusted client")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["collection_approval"], "APPROVED")

    def test_only_admin_cancels_with_reason_and_payments_kept(self):
        order = self.create_order()
        self.pay(order["id"], 1000)
        self.login_as(self.cashier)
        self.assertEqual(self.client.post(f"/api/v1/orders/{order['id']}/cancel/", {"reason": "x"}).status_code, 403)
        self.login_as(self.admin)
        self.assertEqual(self.client.post(f"/api/v1/orders/{order['id']}/cancel/", {}).status_code, 400)
        response = self.client.post(f"/api/v1/orders/{order['id']}/cancel/", {"reason": "Customer changed mind"})
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(len(response.data["payments"]), 1)
        # no more payments, no edits
        self.assertEqual(self.pay(order["id"], 100).status_code, 400)


class CustomAndFreePricingTests(APITestBase):
    def test_custom_price_is_entered_and_summed(self):
        order = self.create_order(items=[
            {"service_item": str(self.shirt.id), "service_type": "CUSTOM", "custom_price": "800", "quantity": 3},
            {"service_item": str(self.suit.id), "service_type": "NORMAL", "quantity": 1},
        ])
        custom = next(i for i in order["items"] if i["service_type"] == "CUSTOM")
        self.assertEqual(Decimal(custom["unit_price"]), Decimal("800"))
        self.assertEqual(Decimal(custom["subtotal"]), Decimal("2400"))
        self.assertEqual(Decimal(order["total_amount"]), Decimal("6400"))  # 2400 + 4000
        self.assertIn("custom price", AuditLog.objects.get(action=AuditAction.ORDER_CREATED).description)

    def test_custom_price_required(self):
        self.login_as(self.cashier)
        payload = self.order_payload(items=[{"service_item": str(self.shirt.id), "service_type": "CUSTOM", "quantity": 1}])
        response = self.client.post("/api/v1/orders/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_custom_price_ignored_for_normal(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "service_type": "NORMAL", "custom_price": "1", "quantity": 1}])
        self.assertEqual(Decimal(order["total_amount"]), Decimal("1000"))

    def test_free_of_charge_counts_zero_but_keeps_price(self):
        order = self.create_order(items=[
            {"service_item": str(self.shirt.id), "quantity": 2, "is_free": True},
            {"service_item": str(self.trousers.id), "quantity": 1},
        ])
        free = next(i for i in order["items"] if i["is_free"])
        self.assertEqual(Decimal(free["unit_price"]), Decimal("1000"))
        self.assertEqual(Decimal(free["subtotal"]), Decimal("0"))
        self.assertEqual(order["total_quantity"], 3)
        self.assertEqual(Decimal(order["total_amount"]), Decimal("1500"))
        self.assertTrue(order["receipt"]["data"]["items"][0]["is_free"])
        self.login_as(self.cashier)
        pdf = self.client.get(f"/api/v1/receipts/{order['receipt']['id']}/pdf/?lang=rw")
        self.assertEqual(pdf.status_code, 200)

    def test_fully_free_order_is_paid_and_collectable(self):
        order = self.create_order(items=[{"service_item": str(self.suit.id), "quantity": 1, "is_free": True}])
        self.assertEqual(order["payment_status"], "PAID")
        self.assertEqual(Decimal(order["balance"]), Decimal("0"))
        self.login_as(self.cashier)
        response = self.client.post(f"/api/v1/orders/{order['id']}/status/", {"status": "COLLECTED"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_admin_can_switch_line_to_custom_or_free(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2}])
        item_id = order["items"][0]["id"]
        self.login_as(self.admin)
        url = f"/api/v1/orders/{order['id']}/"
        r = self.client.patch(url, {"items": [{"id": item_id, "service_item": str(self.shirt.id), "service_type": "CUSTOM", "custom_price": "700", "quantity": 2}]}, format="json")
        self.assertEqual(Decimal(r.data["total_amount"]), Decimal("1400"))
        r = self.client.patch(url, {"items": [{"id": item_id, "service_item": str(self.shirt.id), "service_type": "CUSTOM", "custom_price": "700", "quantity": 2, "is_free": True}]}, format="json")
        self.assertEqual(Decimal(r.data["total_amount"]), Decimal("0"))
        self.assertEqual(r.data["payment_status"], "PAID")

    def test_analytics_include_custom_and_free(self):
        self.create_order(items=[
            {"service_item": str(self.shirt.id), "service_type": "CUSTOM", "custom_price": "500", "quantity": 2},
            {"service_item": str(self.suit.id), "quantity": 1, "is_free": True},
        ])
        self.login_as(self.admin)
        data = self.client.get("/api/v1/analytics/services/?period=today").data
        custom = next(s for s in data["service_types"] if s["service_type"] == "CUSTOM")
        self.assertEqual(custom["value"], "1000.00")
        self.assertEqual(data["free_items"]["quantity"], 1)
        self.assertEqual(data["free_items"]["value_given"], "4000.00")
