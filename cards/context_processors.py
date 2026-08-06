from django.conf import settings
from django.db import OperationalError, ProgrammingError


def apple_login(request):
    unread_count = 0
    has_customer_wallet = False
    current_membership_role = ""
    can_manage_content = False
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            unread_count = request.user.app_notifications.filter(is_read=False).count()
            has_customer_wallet = request.user.wallets.exists()
            membership = (
                request.user.business_memberships.select_related("business")
                .filter(is_active=True, business__is_active=True)
                .first()
            )
            if membership:
                current_membership_role = membership.role
                can_manage_content = bool(
                    membership.role == "OWNER" or membership.can_manage_content
                )
        except (OperationalError, ProgrammingError):
            unread_count = 0
            has_customer_wallet = False
            current_membership_role = ""
            can_manage_content = False
    return {
        "apple_login_enabled": settings.APPLE_LOGIN_ENABLED,
        "apple_wallet_enabled": settings.APPLE_WALLET_ENABLED,
        "global_unread_notification_count": unread_count,
        "has_customer_wallet": has_customer_wallet,
        "current_membership_role": current_membership_role,
        "can_manage_content": can_manage_content,
        "app_name": settings.APP_NAME,
        "app_short_name": settings.APP_SHORT_NAME,
        "app_publisher": settings.APP_PUBLISHER,
        "app_support_email": settings.APP_SUPPORT_EMAIL,
        "android_package_name": settings.ANDROID_PACKAGE_NAME,
        "ios_bundle_id": settings.IOS_BUNDLE_ID,
    }
