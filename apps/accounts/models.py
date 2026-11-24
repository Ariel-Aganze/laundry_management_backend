import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.common.choices import Language


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Application user. Exactly two roles: Admin and Cashier."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        CASHIER = "CASHIER", "Cashier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CASHIER, db_index=True)
    preferred_language = models.CharField(
        max_length=5, choices=Language.choices, default=Language.ENGLISH
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name", "username"]
        constraints = [
            models.UniqueConstraint(Lower("username"), name="unique_username_ci"),
            models.UniqueConstraint(
                Lower("email"), condition=~Q(email=""), name="unique_user_email_ci"
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    @property
    def full_name(self):
        return self.get_full_name() or self.username
