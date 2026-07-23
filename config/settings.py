from pathlib import Path
import base64
import os

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,cards.smarbiz.sbs").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://cards.smarbiz.sbs").split(",") if origin.strip()]
DEFAULT_BUSINESS_SLUG = os.getenv("DEFAULT_BUSINESS_SLUG", "shisha-bar")

# Zentrale öffentliche Identität für Web-App, Store-Einträge und Systemmails.
APP_NAME = os.getenv("APP_NAME", "A+ Card").strip()
APP_SHORT_NAME = os.getenv("APP_SHORT_NAME", "A+ Card").strip()
APP_PUBLISHER = os.getenv("APP_PUBLISHER", "A+Solution GmbH").strip()
APP_SUPPORT_EMAIL = os.getenv("APP_SUPPORT_EMAIL", "app@aplus-solution.de").strip()
APP_PUBLIC_BASE_URL = os.getenv("APP_PUBLIC_BASE_URL", "https://cards.smarbiz.sbs").strip().rstrip("/")
ANDROID_PACKAGE_NAME = os.getenv("ANDROID_PACKAGE_NAME", "de.aplussolution.apluscard").strip()
ANDROID_APP_SIGNING_SHA256 = [
    fingerprint.strip().upper()
    for fingerprint in os.getenv("ANDROID_APP_SIGNING_SHA256", "").split(",")
    if fingerprint.strip()
]
IOS_BUNDLE_ID = os.getenv("IOS_BUNDLE_ID", "de.aplussolution.apluscard").strip()
IOS_APP_TEAM_ID = os.getenv("IOS_APP_TEAM_ID", os.getenv("APPLE_TEAM_ID", "")).strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.apple",
    "rest_framework",
    "rest_framework.authtoken",
    "cards",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "cards.security_middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "cards.legal_middleware.LegalAcceptanceMiddleware",
    "cards.location_middleware.CustomerLocationSelectionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "cards.context_processors.apple_login",
        ]
    },
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600, conn_health_checks=True)}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LANGUAGE_CODE = "de"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", APP_SUPPORT_EMAIL).strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "1") == "1"
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "0" if EMAIL_USE_SSL else "1") == "1"
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"{APP_NAME} <{APP_SUPPORT_EMAIL}>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", f"{APP_NAME} System <{APP_SUPPORT_EMAIL}>")
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", APP_SUPPORT_EMAIL)

DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "landing"
ACCOUNT_ADAPTER = "cards.adapters.SamsAccountAdapter"
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_QUERY_EMAIL = True


def _apple_private_key():
    direct_value = os.getenv("APPLE_PRIVATE_KEY", "").strip()
    encoded_value = os.getenv("APPLE_PRIVATE_KEY_BASE64", "").strip()
    value = direct_value or encoded_value
    if not value:
        return ""

    normalized = value.replace("\\n", "\n").strip()
    if "-----BEGIN PRIVATE KEY-----" in normalized:
        return normalized

    try:
        compact_value = "".join(value.split())
        decoded = base64.b64decode(compact_value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""
    return decoded.replace("\\n", "\n").strip()


APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "").strip()
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "").strip()
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "").strip()
APPLE_PRIVATE_KEY = _apple_private_key()
APPLE_BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID", "").strip()
APPLE_REDIRECT_URI = os.getenv(
    "APPLE_REDIRECT_URI",
    "https://cards.smarbiz.sbs/accounts/apple/callback/",
).strip()
APPLE_PRIVATE_KEY_HAS_PEM_MARKERS = (
    APPLE_PRIVATE_KEY.startswith("-----BEGIN PRIVATE KEY-----")
    and APPLE_PRIVATE_KEY.endswith("-----END PRIVATE KEY-----")
)
APPLE_LOGIN_ENABLED = all([
    APPLE_CLIENT_ID,
    APPLE_KEY_ID,
    APPLE_TEAM_ID,
    APPLE_PRIVATE_KEY_HAS_PEM_MARKERS,
    APPLE_REDIRECT_URI,
])
APPLE_PROVIDER_APPS = []
if APPLE_LOGIN_ENABLED:
    apple_settings = {"certificate_key": APPLE_PRIVATE_KEY}
    APPLE_PROVIDER_APPS.append({
        "client_id": APPLE_CLIENT_ID,
        "secret": APPLE_KEY_ID,
        "key": APPLE_TEAM_ID,
        "settings": apple_settings,
    })
    if APPLE_BUNDLE_ID and APPLE_BUNDLE_ID != APPLE_CLIENT_ID:
        APPLE_PROVIDER_APPS.append({
            "client_id": APPLE_BUNDLE_ID,
            "secret": APPLE_KEY_ID,
            "key": APPLE_TEAM_ID,
            "settings": {**apple_settings, "hidden": True},
        })
SOCIALACCOUNT_PROVIDERS = {"apple": {"APPS": APPLE_PROVIDER_APPS}}

# Apple Wallet uses a Pass Type ID certificate, not the Sign-in-with-Apple .p8 key.
APPLE_WALLET_PASS_TYPE_ID = os.getenv("APPLE_WALLET_PASS_TYPE_ID", "").strip()
APPLE_WALLET_TEAM_ID = os.getenv("APPLE_WALLET_TEAM_ID", APPLE_TEAM_ID).strip()
APPLE_WALLET_P12_BASE64 = os.getenv("APPLE_WALLET_P12_BASE64", "").strip()
APPLE_WALLET_P12_PASSWORD = os.getenv("APPLE_WALLET_P12_PASSWORD", "").strip()
APPLE_WALLET_WWDR_CERT_BASE64 = os.getenv("APPLE_WALLET_WWDR_CERT_BASE64", "").strip()
APPLE_WALLET_ENABLED = all([
    APPLE_WALLET_PASS_TYPE_ID,
    APPLE_WALLET_TEAM_ID,
    APPLE_WALLET_P12_BASE64,
    APPLE_WALLET_WWDR_CERT_BASE64,
])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication", "rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "1") == "1"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "1") == "1"
SESSION_COOKIE_SAMESITE = os.getenv("DJANGO_SESSION_COOKIE_SAMESITE", "None")
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "__Host-sid" if SESSION_COOKIE_SECURE else "sid"
CSRF_COOKIE_NAME = "__Host-ct" if CSRF_COOKIE_SECURE else "ct"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
X_FRAME_OPTIONS = "DENY"
