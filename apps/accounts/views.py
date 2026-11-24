from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditAction
from apps.audit.services import diff, log_activity, snapshot
from apps.common.exceptions import BusinessRuleError, InvalidCredentials
from apps.common.permissions import IsAdmin

from .models import User
from .serializers import (
    CashierSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeUpdateSerializer,
    ResetPasswordSerializer,
    UserMiniSerializer,
    UserSerializer,
)

USER_AUDIT_FIELDS = ["username", "email", "first_name", "last_name", "preferred_language", "is_active"]


def revoke_user_tokens(user):
    """Blacklist every outstanding refresh token of `user`."""
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in tokens], ignore_conflicts=True
    )


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except InvalidCredentials:
            log_activity(
                AuditAction.LOGIN_FAILED,
                request=request,
                entity_type="User",
                description=f"Failed login attempt for '{str(request.data.get('login', ''))[:150]}'.",
            )
            raise

        user = serializer.validated_data["user"]
        update_last_login(None, user)
        log_activity(AuditAction.LOGIN, request=request, user=user, entity=user, description="Logged in.")
        return Response({**issue_tokens(user), "user": UserSerializer(user).data})


class LogoutView(APIView):
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            if str(token.get("user_id")) == str(request.user.pk):
                token.blacklist()
        except TokenError:
            pass  # Already expired/blacklisted: the user is logged out either way.
        log_activity(AuditAction.LOGOUT, request=request, entity=request.user, description="Logged out.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    serializer_class = MeUpdateSerializer

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        before = snapshot(request.user, USER_AUDIT_FIELDS)
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        old, new = diff(before, snapshot(user, USER_AUDIT_FIELDS))
        if new:
            log_activity(
                AuditAction.USER_UPDATED,
                request=request,
                entity=user,
                description="Updated own profile.",
                old_values=old,
                new_values=new,
            )
        return Response(UserSerializer(user).data)


class ChangePasswordView(APIView):
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password", "updated_at"])
            revoke_user_tokens(user)
            log_activity(AuditAction.PASSWORD_CHANGED, request=request, entity=user, description="Changed password.")
        # Old sessions are revoked; give this device fresh tokens.
        return Response(issue_tokens(user))


class StaffListView(mixins.ListModelMixin, viewsets.GenericViewSet):
    """All application users (Admins and Cashiers), e.g. for report filters."""

    serializer_class = UserMiniSerializer
    permission_classes = [IsAdmin]
    pagination_class = None
    queryset = User.objects.all()


class CashierViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CashierSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]
    ordering_fields = ["first_name", "username", "date_joined", "last_login"]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.CASHIER)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
                | Q(email__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        user = serializer.save()
        log_activity(
            AuditAction.USER_CREATED,
            request=self.request,
            entity=user,
            description=f"Created cashier account '{user.username}'.",
            new_values=snapshot(user, USER_AUDIT_FIELDS),
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, USER_AUDIT_FIELDS)
        user = serializer.save()
        old, new = diff(before, snapshot(user, USER_AUDIT_FIELDS))
        if new:
            log_activity(
                AuditAction.USER_UPDATED,
                request=self.request,
                entity=user,
                description=f"Updated cashier '{user.username}'.",
                old_values=old,
                new_values=new,
            )

    def _set_active(self, request, active):
        user = self.get_object()
        if user.is_active == active:
            raise BusinessRuleError(
                "The account is already active." if active else "The account is already deactivated.",
                code="status_unchanged",
            )
        with transaction.atomic():
            user.is_active = active
            user.save(update_fields=["is_active", "updated_at"])
            if not active:
                revoke_user_tokens(user)
            log_activity(
                AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
                request=request,
                entity=user,
                description=f"{'Activated' if active else 'Deactivated'} cashier '{user.username}'.",
                old_values={"is_active": not active},
                new_values={"is_active": active},
            )
        return Response(CashierSerializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self._set_active(request, False)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._set_active(request, True)

    @action(detail=True, methods=["post"], url_path="reset-password", serializer_class=ResetPasswordSerializer)
    def reset_password(self, request, pk=None):
        user = self.get_object()
        serializer = ResetPasswordSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password", "updated_at"])
            revoke_user_tokens(user)
            log_activity(
                AuditAction.PASSWORD_RESET,
                request=request,
                entity=user,
                description=f"Reset password of cashier '{user.username}'.",
            )
        return Response({"detail": "Password reset successfully."})

