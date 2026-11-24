import django_filters
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import IsAdmin
from apps.common.phone import phone_search_fragment

from .models import Payment, PaymentMethod, PaymentState
from .serializers import PaymentSerializer, RecordPaymentSerializer, ReversePaymentSerializer
from .services import record_payment, reverse_payment


class PaymentFilter(django_filters.FilterSet):
    order = django_filters.UUIDFilter(field_name="order_id")
    customer = django_filters.UUIDFilter(field_name="order__customer_id")
    status = django_filters.ChoiceFilter(choices=PaymentState.choices)
    payment_method = django_filters.MultipleChoiceFilter(choices=PaymentMethod.choices)
    received_by = django_filters.UUIDFilter(field_name="received_by_id")
    date_from = django_filters.DateFilter(field_name="received_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="received_at", lookup_expr="date__lte")

    class Meta:
        model = Payment
        fields = []


class PaymentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    ordering_fields = ["received_at", "amount"]
    ordering = ["-received_at"]

    def get_queryset(self):
        qs = Payment.objects.select_related("order", "order__customer", "received_by", "reversed_by")
        search = self.request.query_params.get("search", "").strip()
        if search:
            condition = Q(order__reference__icontains=search) | Q(order__customer__full_name__icontains=search)
            condition |= Q(transaction_reference__icontains=search)
            fragment = phone_search_fragment(search)
            if fragment:
                condition |= Q(order__customer__phone_number__icontains=fragment.lstrip("+"))
            qs = qs.filter(condition)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return RecordPaymentSerializer
        if self.action == "reverse":
            return ReversePaymentSerializer
        return PaymentSerializer

    def create(self, request, *args, **kwargs):
        from apps.orders.models import Order
        from apps.receipts.serializers import ReceiptSerializer

        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        order = get_object_or_404(Order, pk=data.pop("order"))
        payment, receipt = record_payment(order=order, user=request.user, request=request, **data)
        payment = self.get_queryset().get(pk=payment.pk)
        return Response(
            {"payment": PaymentSerializer(payment).data, "receipt": ReceiptSerializer(receipt).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def reverse(self, request, pk=None):
        payment = self.get_object()
        serializer = ReversePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reverse_payment(
            payment=payment, user=request.user, reason=serializer.validated_data["reason"], request=request
        )
        return Response(PaymentSerializer(self.get_queryset().get(pk=payment.pk)).data)
