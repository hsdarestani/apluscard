from django.conf import settings
from django.db import OperationalError, ProgrammingError

from .security_services import mfa_session_is_valid, privileged_membership


def apple_login(request):
    unread_count = 0
    has_customer_wallet = False
    is_privileged_account = False
    mfa_is_confirmed = False
    mfa_session_verified = False
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            unread_count = request.user.app_notifications.filter(is_read=False).count()
            has_customer_wallet = request.user.wallets.exists()
            is_privileged_account = bool(privileged_membership(request.user) or request.user.is_superuser)
            try:
                mfa_is_confirmed = bool(request.user.privileged_mfa_device.is_confirmed)
            except AttributeError:
                mfa_is_confirmed = False
            mfa_session_verified = mfa_session_is_valid(request) if mfa_is_confirmed else False
        except (OperationalError, ProgrammingError):
            unread_count = 0
            has_customer_wallet = False
            is_privileged_account = False
            mfa_is_confirmed = False
            mfa_session_verified = False
    return {
        "apple_login_enabled": settings.APPLE_LOGIN_ENABLED,
        "apple_wallet_enabled": settings.APPLE_WALLET_ENABLED,
        "global_unread_notification_count": unread_count,
        "has_customer_wallet": has_customer_wallet,
        "is_privileged_account": is_privileged_account,
        "mfa_is_confirmed": mfa_is_confirmed,
        "mfa_session_verified": mfa_session_verified,
        "app_name": settings.APP_NAME,
        "app_short_name": settings.APP_SHORT_NAME,
        "app_publisher": settings.APP_PUBLISHER,
        "app_support_email": settings.APP_SUPPORT_EMAIL,
        "android_package_name": settings.ANDROID_PACKAGE_NAME,
        "ios_bundle_id": settings.IOS_BUNDLE_ID,
    }
