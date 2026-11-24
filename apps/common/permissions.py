from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdmin(BasePermission):
    message = "Only an administrator can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_admin", False))


class IsAdminOrReadOnly(BasePermission):
    message = "Only an administrator can perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return getattr(user, "is_admin", False)
