from rest_framework import serializers

from apps.business.models import TemplateKey
from apps.common.choices import Language

from .models import WhatsAppMessageLog


class WhatsAppRequestSerializer(serializers.Serializer):
    template = serializers.ChoiceField(choices=TemplateKey.choices)
    language = serializers.ChoiceField(choices=Language.choices, required=False)
    message = serializers.CharField(
        required=False, allow_blank=False, max_length=2000, help_text="Optional edited message text."
    )


class WhatsAppMessageLogSerializer(serializers.ModelSerializer):
    initiated_by_name = serializers.CharField(source="initiated_by.full_name", read_only=True)

    class Meta:
        model = WhatsAppMessageLog
        fields = [
            "id",
            "template_key",
            "language",
            "phone_number",
            "message",
            "initiated_by",
            "initiated_by_name",
            "initiated_at",
        ]
        read_only_fields = fields
