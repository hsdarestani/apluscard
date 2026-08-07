from pathlib import Path
import base64
import os
import sys

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
IS_TESTING = "test" in sys.argv
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,cards.smarbiz.sbs").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://cards.smarbiz.sbs").split(",") if origin.strip()]
DEFAULT_BUSINESS_SLUG = os.getenv("DEFAULT_BUSINESS_SLUG", "shisha-bar")
APP_RELEASE_SHA = os.getenv("APP_RELEASE_SHA", "dev").strip() or "dev"

# Zentrale öffentliche Identität für Web-App, Store-Einträge und Systemmails.
# Alte Production-Werte werden automatisch auf die neue Store-Identität migriert.
_configured_app_name = os.getenv("APP_NAME", "").strip()
APP_NAME = "Sams Club Lounge" if _configured_app_name in {"", "SAMS Card"} else _configured_app_name
_configured_short_name = os.getenv("APP_SHORT_NAME", "").strip()
APP_SHORT_NAME = "Sams Lounge" if _configured_short_name in {"", "SAMS"} else _configured_short_name
APP_PUBLISHER = os.getenv("APP_PUBLISHER", "A+ Solution GmbH").strip()
APP_SUPPORT_EMAIL = os.getenv("APP_SUPPORT_EMAIL", "app@aplus-solution.de").strip()
APP_PUBLIC_BASE_URL = os.getenv("APP_PUBLIC_BASE_URL", "https://cards.smarbiz.sbs").strip().rstrip("/")
ANDROID_PACKAGE_NAME = os.getenv("ANDROID_PACKAGE_NAME", "de.aplussolution.samscard").strip()
ANDROID_APP_SIGNING_SHA256 = [
    fingerprint.strip().upper()
    for fingerprint in os.getenv("ANDROID_APP_SIGNING_SHA256", "").split(",")
    if fingerprint.strip()
]
IOS_BUNDLE_ID = os.getenv("IOS_BUNDLE_ID", "de.aplussolution.samscard").strip()
IOS_APP_TEAM_ID = os.getenv("IOS_APP_TEAM_ID", os.getenv("APPLE_TEAM_ID", "")).strip()

# Native Push: Android über Firebase Cloud Messaging, iOS direkt über APNs.
PUSH_NOTIFICATIONS_ENABLED = os.getenv("PUSH_NOTIFICATIONS_ENABLED", "0") == "1"
PUSH_HTTP_TIMEOUT_SECONDS = float(os.getenv("PUSH_HTTP_TIMEOUT_SECONDS", "10"))
PUSH_NOTIFICATION_MAX_AGE_SECONDS = int(os.getenv("PUSH_NOTIFICATION_MAX_AGE_SECONDS", "21600"))
PUSH_MAX_ATTEMPTS = int(os.getenv("PUSH_MAX_ATTEMPTS", "5"))
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_SERVICE_ACCOUNT_JSON_BASE64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
APNS_KEY_ID = os.getenv("APNS_KEY_ID", "").strip()
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", IOS_APP_TEAM_ID).strip()
APNS_PRIVATE_KEY_BASE64 = os.getenv("APNS_PRIVATE_KEY_BASE64", "").strip()
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "0") == "1"

# Compliance defaults are deliberately restrictive in production.
WALLET_QR_MAX_AGE_SECONDS = max(30, int(os.getenv("WALLET_QR_MAX_AGE_SECONDS", "90")))
WALLET_QR_REFRESH_SECONDS = max(15, min(int(os.getenv("WALLET_QR_REFRESH_SECONDS", "45")), WALLET_QR_MAX_AGE_SECONDS - 5))
ALLOW_TEST_DATA_PURGE = os.getenv("ALLOW_TEST_DATA_PURGE", "0") == "1"

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
    "cards.compliance_security.ComplianceRateLimitMiddleware",
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
TEMPLATES = [
    {
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
    }
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"),
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "auth.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# django-allauth
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGOUT_ON_GET = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = False
APPLE_LOGIN_ENABLED = os.getenv("APPLE_LOGIN_ENABLED", "0") == "1"
APPLE_WALLET_ENABLED = os.getenv("APPLE_WALLET_ENABLED", "0") == "1"
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", IOS_BUNDLE_ID).strip()
APPLE_BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID", IOS_BUNDLE_ID).strip()
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", IOS_APP_TEAM_ID).strip()
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "").strip()
APPLE_PRIVATE_KEY = os.getenv("APPLE_PRIVATE_KEY", "").strip()
APPLE_REDIRECT_URI = os.getenv("APPLE_REDIRECT_URI", f"{APP_PUBLIC_BASE_URL}/accounts/apple/callback/").strip()

if APPLE_LOGIN_ENABLED and all([APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY]):
    SOCIALACCOUNT_PROVIDERS = {
        "apple": {
            "APP": {
                "client_id": APPLE_CLIENT_ID,
                "secret": APPLE_PRIVATE_KEY,
                "key": APPLE_KEY_ID,
                "settings": {
                    "certificate_key": APPLE_PRIVATE_KEY,
                },
            }
        }
    }
else:
    SOCIALACCOUNT_PROVIDERS = {}

# Email
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.strato.de")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "1") == "1"
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "0") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"{APP_NAME} <{APP_SUPPORT_EMAIL}>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", APP_SUPPORT_EMAIL)

# Security
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "1") == "1"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "1") == "1"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Apple Wallet
APPLE_PASS_TYPE_IDENTIFIER = os.getenv("APPLE_PASS_TYPE_IDENTIFIER", "").strip()
APPLE_PASS_CERTIFICATE_BASE64 = os.getenv("APPLE_PASS_CERTIFICATE_BASE64", "").strip()
APPLE_PASS_PRIVATE_KEY_BASE64 = os.getenv("APPLE_PASS_PRIVATE_KEY_BASE64", "").strip()
APPLE_PASS_WWDR_CERTIFICATE_BASE64 = os.getenv("APPLE_PASS_WWDR_CERTIFICATE_BASE64", "").strip()
APPLE_PASS_CERTIFICATE_PASSWORD = os.getenv("APPLE_PASS_CERTIFICATE_PASSWORD", "").strip()

# Throttling / compliance
COMPLIANCE_RATE_LIMITS = {
    "login": (10, 60),
    "register": (5, 300),
    "payment": (60, 60),
}
