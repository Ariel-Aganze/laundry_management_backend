from django.http import Http404, HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import diff, log_activity, snapshot
from apps.common.permissions import IsAdmin, IsAdminOrReadOnly

from .defaults import PLACEHOLDERS
from .models import BusinessSettings, WhatsAppTemplate
from .serializers import BusinessSettingsSerializer, PublicBrandingSerializer, WhatsAppTemplateSerializer

SETTINGS_AUDIT_FIELDS = [
    "business_name",
    "phone_number",
    "address",
    "email",
    "logo_content_type",
    "currency",
    "currency_decimals",
    "default_language",
    "receipt_footer",
    "receipt_paper",
    "receipt_show_logo",
    "upcoming_pickup_days",
]


class BusinessSettingsView(APIView):
    """GET for every signed-in user (the UI needs currency/name); PATCH for Admin."""

    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = BusinessSettingsSerializer

    def get(self, request):
        settings_obj = BusinessSettings.load()
        return Response(BusinessSettingsSerializer(settings_obj, context={"request": request}).data)

    def patch(self, request):
        settings_obj = BusinessSettings.load()
        before = snapshot(settings_obj, SETTINGS_AUDIT_FIELDS)
        old_logo = bytes(settings_obj.logo_data or b"")
        serializer = BusinessSettingsSerializer(
            settings_obj, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        settings_obj = serializer.save(updated_by=request.user)
        old, new = diff(before, snapshot(settings_obj, SETTINGS_AUDIT_FIELDS))
        new_logo = bytes(settings_obj.logo_data or b"")
        if new_logo != old_logo:
            old["logo"], new["logo"] = ("set" if old_logo else None), ("updated" if new_logo else "removed")
        if new:
            log_activity(
                AuditAction.SETTINGS_UPDATED,
                request=request,
                entity=settings_obj,
                description="Updated business settings.",
                old_values=old,
                new_values=new,
            )
        return Response(BusinessSettingsSerializer(settings_obj, context={"request": request}).data)


class PublicBrandingView(APIView):
    """Business name and logo for the login screen (no authentication)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(PublicBrandingSerializer(BusinessSettings.load(), context={"request": request}).data)


class BusinessLogoView(APIView):
    """The business logo image (public: shown on the login screen and receipts)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        business = BusinessSettings.load()
        if not business.logo_data:
            raise Http404
        response = HttpResponse(bytes(business.logo_data), content_type=business.logo_content_type or "image/png")
        # URLs carry ?v=<updated_at>, so the image can be cached for a long time.
        response["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


class WhatsAppTemplateViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = WhatsAppTemplate.objects.all()
    serializer_class = WhatsAppTemplateSerializer
    pagination_class = None
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["key", "language"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAdmin()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data = {"placeholders": PLACEHOLDERS, "results": response.data}
        return response

    def perform_update(self, serializer):
        old_body = serializer.instance.body
        template = serializer.save(updated_by=self.request.user)
        if old_body != template.body:
            log_activity(
                AuditAction.TEMPLATE_UPDATED,
                request=self.request,
                entity=template,
                description=f"Updated WhatsApp template {template.key} ({template.language}).",
                old_values={"body": old_body},
                new_values={"body": template.body},
            )
