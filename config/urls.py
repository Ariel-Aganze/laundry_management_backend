from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.urls import auth_urlpatterns, users_urlpatterns
from apps.audit.views import AuditLogViewSet
from apps.catalog.urls import categories_router, services_router
from apps.catalog.views import CatalogView
from apps.reports.urls import analytics_urlpatterns, dashboard_urlpatterns
from rest_framework.routers import SimpleRouter

audit_router = SimpleRouter()
audit_router.register("", AuditLogViewSet, basename="audit-log")


def health(request):
    return JsonResponse({"status": "ok"})


api_v1 = [
    path("health/", health, name="health"),
    path("auth/", include(auth_urlpatterns)),
    path("users/", include(users_urlpatterns)),
    path("customers/", include("apps.customers.urls")),
    path("categories/", include(categories_router.urls)),
    path("services/", include(services_router.urls)),
    path("catalog/", CatalogView.as_view(), name="catalog"),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("receipts/", include("apps.receipts.urls")),
    path("settings/", include("apps.business.urls")),
    path("audit-logs/", include(audit_router.urls)),
    path("dashboard/", include(dashboard_urlpatterns)),
    path("analytics/", include(analytics_urlpatterns)),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
