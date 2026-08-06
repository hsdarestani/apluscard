from django.conf import settings
from django.db import OperationalError, ProgrammingError


def apple_login(request):
    unread_count = 0
    has_customer_wallet = False
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            unread_count = request.user.app_notifications.filter(is_read=False).count()
            has_customer_wallet = request.user.wallets.exists()
        except (OperationalError, ProgrammingError):
            unread_count = 0
            has_customer_wallet = False
    return {
        "apple_login_enabled": settings.APPLE_LOGIN_ENABLED,
        "apple_wallet_enabled": settings.APPLE_WALLET_ENABLED,
        "global_unread_notification_count": unread_count,
        "has_customer_wallet": has_customer_wallet,
        "app_name": settings.APP_NAME,
        "app_short_name": settings.APP_SHORT_NAME,
        "app_publisher": settings.APP_PUBLISHER,
        "app_support_email": settings.APP_SUPPORT_EMAIL,
        "android_package_name": settings.ANDROID_PACKAGE_NAME,
        "ios_bundle_id": settings.IOS_BUNDLE_ID,
    }
