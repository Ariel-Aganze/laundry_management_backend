"""
Django settings for the Laundry Management & POS backend.

All environment-specific values are read from environment variables / the `.env`
file (see `.env.example`). Never commit real secrets.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local apps
    "apps.common",
    "apps.accounts",
    "apps.audit",
    "apps.business",
    "apps.customers",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.receipts",
    "apps.messaging",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------
# PostgreSQL is the production database. `DB_ENGINE=sqlite` exists only for quick
# local test runs without a PostgreSQL server.
DB_ENGINE = config("DB_ENGINE", default="postgresql")

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DATABASE_NAME", default="laundry_db"),
            "USER": config("DATABASE_USER", default="postgres"),
            "PASSWORD": config("DATABASE_PASSWORD", default=""),
            "HOST": config("DATABASE_HOST", default="localhost"),
            "PORT": config("DATABASE_PORT", default="5432"),
            "CONN_MAX_AGE": config("DATABASE_CONN_MAX_AGE", default=60, cast=int),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.UsernameOrEmailBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MINUTES", default=30, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --------------------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": config("LOGIN_THROTTLE_RATE", default="10/min"),
    },
    "DATETIME_FORMAT": "iso-8601",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Laundry Management & POS API",
    "DESCRIPTION": "REST API for the Laundry Management & POS system.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173", cast=Csv())
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

# --------------------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Africa/Kigali")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static & media files
# --------------------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))

# Business logo upload limits
LOGO_MAX_UPLOAD_BYTES = config("LOGO_MAX_UPLOAD_BYTES", default=2 * 1024 * 1024, cast=int)

# Trust X-Forwarded-For only when running behind a known reverse proxy.
TRUST_X_FORWARDED_FOR = config("TRUST_X_FORWARDED_FOR", default=False, cast=bool)

# --------------------------------------------------------------------------------------
# Production security (HTTPS)
# --------------------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}
