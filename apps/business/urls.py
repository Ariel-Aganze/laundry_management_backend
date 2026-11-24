from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BusinessSettingsView, PublicBrandingView, WhatsAppTemplateViewSet

router = SimpleRouter()
router.register("whatsapp-templates", WhatsAppTemplateViewSet, basename="whatsapp-template")

urlpatterns = [
    path("", BusinessSettingsView.as_view(), name="business-settings"),
    path("public/", PublicBrandingView.as_view(), name="business-public"),
    *router.urls,
]
