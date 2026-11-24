from decimal import Decimal
from urllib.parse import unquote

from apps.audit.models import AuditAction, AuditLog
from apps.messaging.models import WhatsAppMessageLog
from apps.payments.models import Payment

from .base import APITestBase


class PaymentTests(APITestBase):
    def setUp(self):
        super().setUp()
        # total 3,000
        self.order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 3}])

    def test_partial_then_full_payment(self):
        first = self.pay(self.order["id"], 1000)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["receipt"]["receipt_type"], "PAYMENT")
        second = self.pay(self.order["id"], 2000, method="MOBILE_MONEY")
        self.assertEqual(second.status_code, 201)

        self.login_as(self.cashier)
        detail = self.client.get(f"/api/v1/orders/{self.order['id']}/").data
        self.assertEqual(detail["payment_status"], "PAID")
        self.assertEqual(Decimal(detail["balance"]), Decimal("0"))
        history = self.client.get(f"/api/v1/orders/{self.order['id']}/payments/").data
        self.assertEqual([Decimal(p["amount"]) for p in history], [Decimal("1000"), Decimal("2000")])

    def test_overpayment_rejected(self):
        response = self.pay(self.order["id"], "3000.01")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "payment_exceeds_balance")
        self.assertEqual(response.data["balance"], "3000.00")

    def test_other_method_requires_description(self):
        response = self.pay(self.order["id"], 100, method="OTHER")
        self.assertEqual(response.status_code, 400)

    def test_reversal_admin_only_preserves_record(self):
        payment_id = self.pay(self.order["id"], 1000).data["payment"]["id"]
        self.login_as(self.cashier)
        self.assertEqual(self.client.post(f"/api/v1/payments/{payment_id}/reverse/", {"reason": "x"}).status_code, 403)
        self.login_as(self.admin)
        response = self.client.post(f"/api/v1/payments/{payment_id}/reverse/", {"reason": "Wrong order"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "REVERSED")
        detail = self.client.get(f"/api/v1/orders/{self.order['id']}/").data
        self.assertEqual(detail["payment_status"], "UNPAID")
        self.assertEqual(Decimal(detail["balance"]), Decimal("3000"))
        self.assertEqual(Payment.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.PAYMENT_REVERSED).exists())

    def test_payments_cannot_be_deleted_or_edited(self):
        payment_id = self.pay(self.order["id"], 1000).data["payment"]["id"]
        self.login_as(self.admin)
        self.assertEqual(self.client.delete(f"/api/v1/payments/{payment_id}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/v1/payments/{payment_id}/", {"amount": "1"}).status_code, 405)


class ReceiptTests(APITestBase):
    def test_receipt_snapshot_and_pdf_formats(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2, "condition_notes": "Torn"}])
        receipt_id = order["receipt"]["id"]
        data = order["receipt"]["data"]
        self.assertEqual(data["order"]["reference"], order["reference"])
        self.assertEqual(data["customer"]["phone"], "+250788123456")
        self.assertEqual(data["items"][0]["service_type"], "NORMAL")

        self.login_as(self.cashier)
        for paper in ("58mm", "80mm", "A4"):
            for lang in ("en", "rw"):
                response = self.client.get(f"/api/v1/receipts/{receipt_id}/pdf/?paper={paper}&lang={lang}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF"))

    def test_payment_receipt_does_not_change_order_receipt(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2}])
        self.pay(order["id"], 500)
        self.login_as(self.cashier)
        original = self.client.get(f"/api/v1/receipts/{order['receipt']['id']}/").data
        self.assertEqual(original["data"]["amount_paid"], "0.00")
        receipts = self.client.get(f"/api/v1/orders/{order['id']}/receipts/").data
        self.assertEqual(sorted(r["receipt_type"] for r in receipts), ["ORDER", "PAYMENT"])


class WhatsAppTests(APITestBase):
    def test_preview_and_initiate(self):
        order = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 2}])
        self.login_as(self.cashier)
        url = f"/api/v1/orders/{order['id']}/whatsapp/"
        preview = self.client.get(url, {"template": "ORDER_READY", "language": "en"})
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertIn(order["reference"], preview.data["message"])
        self.assertIn("RWF 2,000", preview.data["message"])
        self.assertTrue(preview.data["url"].startswith("https://wa.me/250788123456?text="))
        self.assertEqual(WhatsAppMessageLog.objects.count(), 0)

        rw = self.client.get(url, {"template": "PAYMENT_REMINDER", "language": "rw"})
        self.assertIn("Muraho Jean Mugabo", unquote(rw.data["url"]))

        sent = self.client.post(url, {"template": "ORDER_READY"}, format="json")
        self.assertEqual(sent.status_code, 200)
        self.assertIn("not confirmed", sent.data["note"])
        self.assertEqual(WhatsAppMessageLog.objects.count(), 1)

    def test_template_placeholder_validation(self):
        self.login_as(self.admin)
        templates = self.client.get("/api/v1/settings/whatsapp-templates/").data["results"]
        self.assertEqual(len(templates), 8)
        tid = templates[0]["id"]
        bad = self.client.patch(f"/api/v1/settings/whatsapp-templates/{tid}/", {"body": "Hi {unknown}"})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.patch(f"/api/v1/settings/whatsapp-templates/{tid}/", {"body": "Hi {customer_name}"})
        self.assertEqual(ok.status_code, 200)


class DashboardAnalyticsTests(APITestBase):
    def test_metrics_are_separate_and_exclude_cancelled(self):
        o1 = self.create_order(items=[{"service_item": str(self.shirt.id), "quantity": 3}])  # 3000
        o2 = self.create_order(items=[{"service_item": str(self.suit.id), "quantity": 1, "service_type": "EXPRESS"}])  # 5500
        self.pay(o1["id"], 1000)
        self.pay(o2["id"], 5500)
        self.login_as(self.admin)
        self.client.post(f"/api/v1/orders/{o2['id']}/cancel/", {"reason": "Test"})

        summary = self.client.get("/api/v1/dashboard/summary/?period=today").data
        self.assertEqual(summary["orders_count"], 1)
        self.assertEqual(summary["order_value"], "3000.00")
        self.assertEqual(summary["money_received"], "1000.00")
        self.assertEqual(summary["outstanding_balance"], "2000.00")
        self.assertIn("cashier_activity", summary)

        revenue = self.client.get("/api/v1/analytics/revenue/?period=last_7_days").data
        self.assertEqual(revenue["totals"]["money_received"], "1000.00")
        self.assertEqual(len(revenue["series"]), 7)

        services = self.client.get("/api/v1/analytics/services/?period=today").data
        self.assertEqual(services["top_items"][0]["name"], "Shirt")
        express = next(s for s in services["service_types"] if s["service_type"] == "EXPRESS")
        self.assertEqual(express["orders"], 0)

        for path in ("cashiers", "customers", "payments"):
            self.assertEqual(self.client.get(f"/api/v1/analytics/{path}/?period=this_month").status_code, 200)

    def test_cashier_dashboard_is_today_only(self):
        self.create_order()
        self.login_as(self.cashier)
        data = self.client.get("/api/v1/dashboard/summary/?period=last_month").data
        self.assertEqual(data["period"], "today")
        self.assertEqual(data["my_orders_count"], 1)
        self.assertNotIn("cashier_activity", data)

    def test_pickups_and_overdue(self):
        upcoming = self.create_order(pickup_days=1)
        overdue = self.create_order(pickup_days=0)
        Order = __import__("apps.orders.models", fromlist=["Order"]).Order
        from datetime import timedelta

        Order.objects.filter(pk=overdue["id"]).update(
            drop_off_date=self.today - timedelta(days=5), pickup_date=self.today - timedelta(days=2)
        )
        self.login_as(self.cashier)
        pickups = self.client.get("/api/v1/dashboard/pickups/").data
        self.assertEqual([o["id"] for o in pickups["results"]], [upcoming["id"]])
        late = self.client.get("/api/v1/dashboard/overdue/").data
        self.assertEqual([o["id"] for o in late["results"]], [overdue["id"]])
        self.assertTrue(late["results"][0]["is_overdue"])


class AuditTests(APITestBase):
    def test_audit_log_is_admin_only_and_read_only(self):
        self.create_order()
        self.login_as(self.admin)
        logs = self.client.get("/api/v1/audit-logs/?action=ORDER_CREATED").data
        self.assertEqual(logs["count"], 1)
        log_id = logs["results"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/v1/audit-logs/{log_id}/").status_code, 405)
        entry = AuditLog.objects.get(pk=log_id)
        entry.description = "tampered"
        with self.assertRaises(RuntimeError):
            entry.save()
