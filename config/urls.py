from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

from cards import security_views
from cards.apple_views import apple_callback

admin.site.site_header = "Sams Club Lounge Verwaltung"
admin.site.site_title = "Sams Club Lounge"
admin.site.index_title = "A+ Solution GmbH · Übersicht"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("allauth.urls")),
    path(
        "accounts/apple/callback/",
        apple_callback,
        name="apple_callback",
    ),
    path("sicherheit/2fa/einrichten/", security_views.mfa_setup, name="mfa_setup"),
    path("sicherheit/2fa/bestaetigen/", security_views.mfa_challenge, name="mfa_challenge"),
    path("sicherheit/2fa/biometrie/", security_views.mfa_biometric_verify, name="mfa_biometric_verify"),
    path("sicherheit/2fa/notfallcodes-neu/", security_views.mfa_regenerate_recovery_codes, name="mfa_regenerate_recovery_codes"),
    path("", include("cards.urls")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
