from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.business.models import BusinessSettings
from apps.common.i18n import normalize_language

from .models import Receipt
from .pdf import PAPERS, render_receipt_pdf
from .serializers import ReceiptListSerializer, ReceiptSerializer


def receipt_pdf_response(receipt, request):
    paper = request.query_params.get("paper") or BusinessSettings.load().receipt_paper
    if paper not in PAPERS:
        paper = "80mm"
    lang = normalize_language(request.query_params.get("lang") or request.user.preferred_language)
    pdf = render_receipt_pdf(receipt.data, paper=paper, lang=lang)
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.query_params.get("download") in ("1", "true") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{receipt.receipt_number}.pdf"'
    return response


class ReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    """Previously generated receipts (FR-050). Content never changes after generation."""

    filterset_fields = ["order", "receipt_type", "payment"]
    ordering_fields = ["generated_at"]
    ordering = ["-generated_at"]

    def get_queryset(self):
        return Receipt.objects.select_related("order", "generated_by")

    def get_serializer_class(self):
        return ReceiptSerializer if self.action == "retrieve" else ReceiptListSerializer

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """?paper=58mm|80mm|A4  &lang=en|rw  &download=1"""
        return receipt_pdf_response(self.get_object(), request)
