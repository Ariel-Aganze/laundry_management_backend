import re
from io import BytesIO
from string import Formatter

from django.conf import settings
from django.urls import reverse
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from .defaults import PLACEHOLDERS
from .models import BusinessSettings, WhatsAppTemplate

ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp"}


LOGO_MAX_PX = 512


def logo_url_for(obj, request=None):
    if not obj.logo_data:
        return None
    url = f"{reverse('business-logo')}?v={int(obj.updated_at.timestamp())}"
    return request.build_absolute_uri(url) if request else url


def process_logo(file):
    """Validate and shrink an uploaded logo. Returns (bytes, content_type)."""
    try:
        image = Image.open(file)
        image.load()
    except (UnidentifiedImageError, OSError):
        raise serializers.ValidationError("Logo must be a JPEG, PNG or WebP image.", code="invalid_image")
    image.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue(), "image/png"


class BusinessSettingsSerializer(serializers.ModelSerializer):
    logo = serializers.FileField(write_only=True, required=False, allow_null=True)
    remove_logo = serializers.BooleanField(write_only=True, required=False, default=False)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSettings
        fields = [
            "business_name",
            "phone_number",
            "address",
            "email",
            "logo",
            "logo_url",
            "remove_logo",
            "currency",
            "currency_decimals",
            "default_language",
            "receipt_footer",
            "receipt_paper",
            "receipt_show_logo",
            "upcoming_pickup_days",
            "updated_at",
        ]
        read_only_fields = ["updated_at", "logo_url"]

    def get_logo_url(self, obj):
        return logo_url_for(obj, self.context.get("request"))

    def validate_business_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Business name is required.", code="required")
        return value

    def validate_currency(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise serializers.ValidationError("Use a 3-letter currency code, e.g. RWF.", code="invalid_currency")
        return value

    def validate_logo(self, file):
        if file is None:
            return file
        if file.size > settings.LOGO_MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("The logo must be 2 MB or smaller.", code="file_too_large")
        content_type = getattr(file, "content_type", "")
        if content_type not in ALLOWED_LOGO_TYPES:
            raise serializers.ValidationError("Logo must be a JPEG, PNG or WebP image.", code="invalid_image")
        return process_logo(file)

    def update(self, instance, validated_data):
        remove_logo = validated_data.pop("remove_logo", False)
        logo = validated_data.pop("logo", None)
        if logo:
            instance.logo_data, instance.logo_content_type = logo
        elif remove_logo:
            instance.logo_data, instance.logo_content_type = None, ""
        return super().update(instance, validated_data)


class PublicBrandingSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSettings
        fields = ["business_name", "logo_url", "default_language"]

    def get_logo_url(self, obj):
        return logo_url_for(obj, self.context.get("request"))


class WhatsAppTemplateSerializer(serializers.ModelSerializer):
    key_label = serializers.CharField(source="get_key_display", read_only=True)

    class Meta:
        model = WhatsAppTemplate
        fields = ["id", "key", "key_label", "language", "body", "updated_at"]
        read_only_fields = ["id", "key", "key_label", "language", "updated_at"]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("The message cannot be empty.", code="required")
        if len(value) > 2000:
            raise serializers.ValidationError("The message is too long (max 2000 characters).", code="max_length")
        try:
            names = {name for _, name, _, _ in Formatter().parse(value) if name is not None}
        except ValueError:
            raise serializers.ValidationError(
                "Unbalanced { } braces in the message.", code="invalid_template"
            )
        unknown = sorted(n for n in names if n not in PLACEHOLDERS)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown placeholder(s): {', '.join('{' + n + '}' for n in unknown)}.",
                code="unknown_placeholder",
            )
        return value
