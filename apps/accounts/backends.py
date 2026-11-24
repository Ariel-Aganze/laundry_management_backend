from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


def find_user_by_login(login):
    """Return the single user whose username or email matches `login` (case-insensitive)."""
    login = (login or "").strip()
    if not login:
        return None
    User = get_user_model()
    matches = list(
        User.objects.filter(Q(username__iexact=login) | (Q(email__iexact=login) & ~Q(email="")))[:2]
    )
    return matches[0] if len(matches) == 1 else None


class UsernameOrEmailBackend(ModelBackend):
    """Authenticate with either username or email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username or not password:
            return None
        user = find_user_by_login(username)
        if user is None:
            # Run the hasher anyway to reduce timing differences.
            get_user_model()().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
