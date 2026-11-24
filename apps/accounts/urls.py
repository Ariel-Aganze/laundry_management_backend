from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ChangePasswordView, CashierViewSet, LoginView, LogoutView, MeView, StaffListView

auth_urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]

router = SimpleRouter()
router.register("cashiers", CashierViewSet, basename="cashier")
router.register("", StaffListView, basename="staff")
users_urlpatterns = router.urls
