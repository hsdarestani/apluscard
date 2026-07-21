from django.conf import settings


def apple_login(request):
    return {"apple_login_enabled": settings.APPLE_LOGIN_ENABLED}
