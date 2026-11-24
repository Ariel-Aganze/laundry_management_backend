from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.common.exceptions import InvalidCredentials

from .backends import find_user_by_login
from .models import User


def _validate_unique_ci(field, value, instance=None):
    if not value:
        return value
    qs = User.objects.filter(**{f"{field}__iexact": value})
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError(f"A user with this {field} already exists.", code="unique")
    return value


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "preferred_language",
            "is_active",
            "created_at",
            "last_login",
        ]
        read_only_fields = fields


class UserMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "role", "is_active"]


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "preferred_language"]

    def validate_email(self, value):
        return _validate_unique_ci("email", value.strip().lower(), self.instance)


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField(help_text="Username or email address")
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(request, username=attrs["login"], password=attrs["password"])
        if user is None:
            candidate = find_user_by_login(attrs["login"])
            if candidate and not candidate.is_active and candidate.check_password(attrs["password"]):
                raise InvalidCredentials(
                    "Your account has been deactivated. Contact the administrator.",
                    code="account_disabled",
                )
            raise InvalidCredentials()
        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.", code="wrong_password")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


class CashierSerializer(serializers.ModelSerializer):
    """Admin-side create / update of cashier accounts."""

    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    full_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "preferred_language",
            "is_active",
            "password",
            "created_at",
            "last_login",
        ]
        read_only_fields = ["id", "created_at", "last_login"]
        extra_kwargs = {
            "first_name": {"required": True, "allow_blank": False},
        }

    def validate_username(self, value):
        return _validate_unique_ci("username", value.strip(), self.instance)

    def validate_email(self, value):
        return _validate_unique_ci("email", value.strip().lower(), self.instance)

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": ["Password is required."]}, code="required")
            candidate = User(**{k: v for k, v in attrs.items() if k != "password"})
            try:
                validate_password(attrs["password"], candidate)
            except Exception as exc:  # django ValidationError -> DRF
                raise serializers.ValidationError({"password": list(exc.messages)})
        else:
            if "password" in attrs:
                raise serializers.ValidationError(
                    {"password": ["Use the reset-password action to change a cashier's password."]}
                )
            # Status changes go through activate/deactivate so tokens are revoked.
            attrs.pop("is_active", None)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(role=User.Role.CASHIER, **validated_data)
        user.set_password(password)
        user.save()
        return user


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value, self.context.get("user"))
        return value
