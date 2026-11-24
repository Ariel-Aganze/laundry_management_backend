from django.conf import settings


def get_client_ip(request):
    if request is None:
        return None
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None
