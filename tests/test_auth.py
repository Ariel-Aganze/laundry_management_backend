from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog

from .base import PASSWORD, APITestBase


class AuthenticationTests(APITestBase):
    def login(self, login, password=PASSWORD):
        return self.client.post("/api/v1/auth/login/", {"login": login, "password": password}, format="json")

    def test_admin_login(self):
        response = self.login("admin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "ADMIN")
        self.assertIn("access", response.data)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.LOGIN, user=self.admin).exists())

    def test_cashier_login_with_email(self):
        response = self.login("CATHY@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "CASHIER")

    def test_incorrect_credentials(self):
        response = self.login("cashier", "wrong")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "invalid_credentials")
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).exists())

    def test_deactivated_cashier_cannot_login_or_use_token(self):
        access = self.login("cashier").data["access"]
        self.login_as(self.admin)
        self.assertEqual(self.client.post(f"/api/v1/users/cashiers/{self.cashier.id}/deactivate/").status_code, 200)
        self.client.force_authenticate(user=None)

        response = self.login("cashier")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "account_disabled")

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        tokens = self.login("cashier").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code, 204)
        self.client.credentials()
        response = self.client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_request_is_401(self):
        self.assertEqual(self.client.get("/api/v1/orders/").status_code, 401)

    def test_change_language_preference(self):
        self.login_as(self.cashier)
        response = self.client.patch("/api/v1/auth/me/", {"preferred_language": "rw"}, format="json")
        self.assertEqual(response.data["preferred_language"], "rw")


class RoleRestrictionTests(APITestBase):
    def test_cashier_cannot_access_admin_endpoints(self):
        self.login_as(self.cashier)
        forbidden = [
            ("post", "/api/v1/categories/", {"name": "X"}),
            ("post", "/api/v1/services/", {}),
            ("patch", f"/api/v1/services/{self.shirt.id}/", {"normal_price": "1"}),
            ("get", "/api/v1/users/cashiers/", None),
            ("get", "/api/v1/audit-logs/", None),
            ("get", "/api/v1/analytics/revenue/", None),
            ("patch", "/api/v1/settings/", {"business_name": "X"}),
        ]
        for method, url, data in forbidden:
            response = getattr(self.client, method)(url, data, format="json")
            self.assertEqual(response.status_code, 403, f"{method.upper()} {url}")

    def test_admin_creates_cashier(self):
        self.login_as(self.admin)
        response = self.client.post(
            "/api/v1/users/cashiers/",
            {"username": "newcash", "first_name": "New", "last_name": "Cashier", "password": "An0ther-Str0ng!"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="newcash")
        self.assertEqual(user.role, User.Role.CASHIER)
        self.assertTrue(user.check_password("An0ther-Str0ng!"))
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.USER_CREATED).exists())

    def test_weak_password_rejected(self):
        self.login_as(self.admin)
        response = self.client.post(
            "/api/v1/users/cashiers/", {"username": "weak", "first_name": "W", "password": "123"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["errors"])
