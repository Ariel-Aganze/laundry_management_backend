from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import IsAdmin
from apps.payments.models import Payment
from apps.payments.serializers import PaymentSerializer
from apps.receipts.models import Receipt, ReceiptType
from apps.receipts.serializers import ReceiptListSerializer, ReceiptSerializer
from apps.receipts.services import generate_receipt

from . import services
from .filters import OrderFilter, search_orders
from .models import Order
from .serializers import (
    CancelOrderSerializer,
    CollectionDecisionSerializer,
    CollectionRequestSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderUpdateSerializer,
    StatusChangeSerializer,
)

UUID_REGEX = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Cashiers and Admins can see all orders. Editing rules, cancellation and
    collection approvals are enforced in `services.py`.
    """

    lookup_value_regex = UUID_REGEX
    filterset_class = OrderFilter
    http_method_names = ["get", "post", "patch", "head", "options"]
    ordering_fields = ["created_at", "pickup_date", "drop_off_date", "total_amount", "balance", "reference"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Order.objects.select_related("customer", "created_by")
        if self.action not in ("list", "search"):
            qs = qs.select_related(
                "collected_by",
                "cancelled_by",
                "collection_requested_by",
                "collection_decided_by",
            ).prefetch_related(
                "items",
                Prefetch(
                    "payments",
                    queryset=Payment.objects.select_related(
                        "order", "order__customer", "received_by", "reversed_by"
                    ).order_by("received_at"),
                ),
                Prefetch("receipts", queryset=Receipt.objects.select_related("order", "generated_by")),
            )
        return qs

    def get_serializer_class(self):
        return {
            "list": OrderListSerializer,
            "search": OrderListSerializer,
            "create": OrderCreateSerializer,
            "partial_update": OrderUpdateSerializer,
            "status_change": StatusChangeSerializer,
            "cancel": CancelOrderSerializer,
            "request_collection": CollectionRequestSerializer,
            "decide_collection": CollectionDecisionSerializer,
        }.get(self.action, OrderDetailSerializer)

    def _detail(self, order, status_code=status.HTTP_200_OK, **extra):
        order = self.get_queryset().get(pk=order.pk)
        data = OrderDetailSerializer(order, context=self.get_serializer_context()).data
        return Response({**data, **extra} if extra else data, status=status_code)

    def _input(self, serializer_class):
        serializer = serializer_class(data=self.request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    # ---- CRUD -----------------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        data = self._input(OrderCreateSerializer)
        order, receipt = services.create_order(
            user=request.user,
            customer=data.get("customer"),
            new_customer=data.get("new_customer"),
            drop_off_date=data["drop_off_date"],
            pickup_date=data["pickup_date"],
            notes=data.get("notes", ""),
            items=data["items"],
            payment=data.get("payment"),
            request=request,
        )
        return self._detail(order, status.HTTP_201_CREATED, receipt=ReceiptSerializer(receipt).data)

    def partial_update(self, request, *args, **kwargs):
        order = self.get_object()
        data = self._input(OrderUpdateSerializer)
        order = services.update_order(order=order, user=request.user, data=data, request=request)
        return self._detail(order)

    # ---- Search ---------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def search(self, request):
        """GET /orders/search/?q=<reference | name | phone>"""
        term = request.query_params.get("q") or request.query_params.get("search") or ""
        qs = search_orders(self.get_queryset(), term).order_by("-created_at") if term.strip() else Order.objects.none()
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(OrderListSerializer(page, many=True).data)

    # ---- Status & collection --------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="status")
    def status_change(self, request, pk=None):
        data = self._input(StatusChangeSerializer)
        order = services.change_status(
            order=self.get_object(),
            new_status=data["status"],
            user=request.user,
            approve_balance=data["approve_balance"],
            note=data["note"],
            request=request,
        )
        return self._detail(order)

    @action(detail=True, methods=["post"], url_path="request-collection")
    def request_collection(self, request, pk=None):
        data = self._input(CollectionRequestSerializer)
        order = services.request_collection_approval(
            order=self.get_object(), user=request.user, note=data["note"], request=request
        )
        return self._detail(order)

    @action(detail=True, methods=["post"], url_path="decide-collection", permission_classes=[IsAdmin])
    def decide_collection(self, request, pk=None):
        data = self._input(CollectionDecisionSerializer)
        order = services.decide_collection_approval(
            order=self.get_object(),
            user=request.user,
            approve=data["decision"] == "approve",
            note=data["note"],
            request=request,
        )
        return self._detail(order)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def cancel(self, request, pk=None):
        data = self._input(CancelOrderSerializer)
        order = services.cancel_order(order=self.get_object(), user=request.user, reason=data["reason"], request=request)
        return self._detail(order)

    # ---- Payments & receipts --------------------------------------------------------
    @action(detail=True, methods=["get"])
    def payments(self, request, pk=None):
        order = self.get_object()
        payments = (
            order.payments.select_related("order", "order__customer", "received_by", "reversed_by")
            .order_by("received_at")
        )
        return Response(PaymentSerializer(payments, many=True).data)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        """Latest order receipt (generated if none exists yet)."""
        order = self.get_object()
        receipt = (
            order.receipts.filter(receipt_type=ReceiptType.ORDER).select_related("order", "generated_by").first()
        )
        if receipt is None:
            receipt = generate_receipt(order=order, user=request.user, receipt_type=ReceiptType.ORDER, request=request)
        return Response(ReceiptSerializer(receipt).data)

    @action(detail=True, methods=["get"])
    def receipts(self, request, pk=None):
        order = self.get_object()
        return Response(
            ReceiptListSerializer(order.receipts.select_related("order", "generated_by"), many=True).data
        )

    # ---- WhatsApp -------------------------------------------------------------------
    @action(detail=True, methods=["get", "post"])
    def whatsapp(self, request, pk=None):
        """
        GET  ?template=ORDER_READY&language=rw  -> preview message + wa.me link
        POST {template, language?, message?}    -> records that WhatsApp was opened, returns link
        """
        from apps.messaging.serializers import WhatsAppRequestSerializer
        from apps.messaging.services import initiate_message, render_message, whatsapp_url

        order = self.get_object()
        source = request.query_params if request.method == "GET" else request.data
        serializer = WhatsAppRequestSerializer(data=source)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["template"]
        message, lang = render_message(order, key, serializer.validated_data.get("language"))
        if request.method == "POST" and serializer.validated_data.get("message"):
            message = serializer.validated_data["message"]

        payload = {
            "template": key,
            "language": lang,
            "phone_number": order.customer.phone_number,
            "message": message,
            "url": whatsapp_url(order.customer.phone_number, message),
        }
        if request.method == "POST":
            entry = initiate_message(order=order, user=request.user, key=key, lang=lang, message=message, request=request)
            payload["log_id"] = str(entry.id)
            payload["note"] = "WhatsApp was opened with this message. Delivery is not confirmed."
        return Response(payload)
