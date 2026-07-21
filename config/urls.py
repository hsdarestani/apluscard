from allauth.socialaccount.providers.apple.views import oauth2_callback as apple_oauth2_callback
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = "SAMS Verwaltung"
admin.site.site_title = "SAMS Verwaltung"
admin.site.index_title = "Übersicht"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("allauth.urls")),
    # Apple Developer is configured with this exact return URL. Keeping the
    # standard allauth URL above preserves compatibility, while this later
    # duplicate route name makes allauth generate the registered short URL.
    path(
        "accounts/apple/callback/",
        apple_oauth2_callback,
        name="apple_callback",
    ),
    path("", include("cards.urls")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
