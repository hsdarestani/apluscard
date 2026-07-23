import base64
import json
import logging
import time
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urljoin

import httpx
import jwt
from django.conf import settings

from .models import AppNotification, PushDevice

logger = logging.getLogger(__name__)

_APNS_TOKEN_CACHE = {"value": "", "expires_at": 0}
_FIREBASE_APP = None


class PushConfigurationError(RuntimeError):
    pass


def _decode_secret(value):
    value = (value or "").strip()
    if not value:
        return ""
    if "-----BEGIN" in value:
        return value.replace("\\n", "\n")
    try:
        return base64.b64decode("".join(value.split()), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value.replace("\\n", "\n")


def _absolute_url(path):
    if not path:
        return settings.APP_PUBLIC_BASE_URL
    if str(path).startswith(("https://", "http://")):
        return str(path)
    return urljoin(f"{settings.APP_PUBLIC_BASE_URL}/", str(path).lstrip("/"))


def _string_data(notification):
    source = notification.data if isinstance(notification.data, dict) else {}
    payload = {
        "notification_id": str(notification.pk),
        "kind": notification.kind,
        "url": _absolute_url(source.get("url")),
    }
    for key, value in source.items():
        if key == "url" or value is None:
            continue
        if isinstance(value, (dict, list)):
            payload[str(key)] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            payload[str(key)] = str(value)
    return payload


def _firebase_app():
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    raw = _decode_secret(settings.FIREBASE_SERVICE_ACCOUNT_JSON_BASE64)
    if not raw:
        raise PushConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON_BASE64 fehlt.")
    try:
        service_account = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PushConfigurationError("Firebase Service Account JSON ist ungültig.") from exc
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise PushConfigurationError("firebase-admin ist nicht installiert.") from exc
    try:
        _FIREBASE_APP = firebase_admin.get_app("sams-card")
    except ValueError:
        _FIREBASE_APP = firebase_admin.initialize_app(
            credentials.Certificate(service_account),
            {"projectId": settings.FIREBASE_PROJECT_ID or service_account.get("project_id")},
            name="sams-card",
        )
    return _FIREBASE_APP


def _send_android(notification, devices):
    if not devices:
        return 0
    from firebase_admin import messaging

    message = messaging.MulticastMessage(
        tokens=[device.token for device in devices],
        notification=messaging.Notification(
            title=notification.title,
            body=notification.body,
        ),
        data=_string_data(notification),
        android=messaging.AndroidConfig(
            priority="high",
            ttl=timedelta(days=1),
            notification=messaging.AndroidNotification(
                channel_id="sams_updates",
                sound="default",
                color="#B88746",
                tag=f"sams-{notification.kind.lower()}",
            ),
        ),
    )
    response = messaging.send_each_for_multicast(message, app=_firebase_app())
    invalid_ids = []
    for device, result in zip(devices, response.responses):
        if result.success:
            continue
        error = result.exception
        code = str(getattr(error, "code", "") or "").lower()
        name = error.__class__.__name__.lower() if error else ""
        if (
            "unregistered" in name
            or "registration-token-not-registered" in code
            or "invalid-registration-token" in code
            or "sender-id-mismatch" in code
        ):
            invalid_ids.append(device.pk)
        logger.warning("Android push failed for device %s: %s", device.pk, error)
    if invalid_ids:
        PushDevice.objects.filter(pk__in=invalid_ids).update(is_active=False)
    return response.success_count


def _apns_auth_token():
    now = int(time.time())
    if _APNS_TOKEN_CACHE["value"] and _APNS_TOKEN_CACHE["expires_at"] > now + 60:
        return _APNS_TOKEN_CACHE["value"]
    private_key = _decode_secret(settings.APNS_PRIVATE_KEY_BASE64)
    if not all([private_key, settings.APNS_KEY_ID, settings.APNS_TEAM_ID, settings.IOS_BUNDLE_ID]):
        raise PushConfigurationError("APNs Key, Key ID, Team ID oder iOS Bundle ID fehlt.")
    token = jwt.encode(
        {"iss": settings.APNS_TEAM_ID, "iat": now},
        private_key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": settings.APNS_KEY_ID},
    )
    _APNS_TOKEN_CACHE["value"] = token
    _APNS_TOKEN_CACHE["expires_at"] = now + 50 * 60
    return token


def _send_ios(notification, devices):
    if not devices:
        return 0
    endpoint = "https://api.sandbox.push.apple.com" if settings.APNS_USE_SANDBOX else "https://api.push.apple.com"
    unread_count = AppNotification.objects.filter(recipient=notification.recipient, is_read=False).count()
    payload = {
        "aps": {
            "alert": {"title": notification.title, "body": notification.body},
            "sound": "default",
            "badge": unread_count,
            "thread-id": "sams-card",
        },
        **_string_data(notification),
    }
    headers = {
        "authorization": f"bearer {_apns_auth_token()}",
        "apns-topic": settings.IOS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    success_count = 0
    invalid_ids = []
    with httpx.Client(http2=True, timeout=settings.PUSH_HTTP_TIMEOUT_SECONDS) as client:
        for device in devices:
            response = client.post(f"{endpoint}/3/device/{device.token}", headers=headers, json=payload)
            if response.status_code == 200:
                success_count += 1
                continue
            reason = ""
            try:
                reason = response.json().get("reason", "")
            except (ValueError, AttributeError):
                reason = response.text[:200]
            if response.status_code in {400, 410} and reason in {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}:
                invalid_ids.append(device.pk)
            logger.warning("iOS push failed for device %s: HTTP %s %s", device.pk, response.status_code, reason)
    if invalid_ids:
        PushDevice.objects.filter(pk__in=invalid_ids).update(is_active=False)
    return success_count


def send_notification(notification):
    devices = list(
        PushDevice.objects.filter(
            user=notification.recipient,
            is_active=True,
            platform__in=[PushDevice.Platform.ANDROID, PushDevice.Platform.IOS],
        ).order_by("platform", "-updated_at")
    )
    result = {"device_count": len(devices), "android": 0, "ios": 0, "sent_total": 0, "errors": []}
    if not devices:
        return result
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        result["errors"].append("PUSH_NOTIFICATIONS_ENABLED ist deaktiviert.")
        return result

    grouped = defaultdict(list)
    for device in devices:
        grouped[device.platform].append(device)

    if grouped[PushDevice.Platform.ANDROID]:
        try:
            result["android"] = _send_android(notification, grouped[PushDevice.Platform.ANDROID])
        except Exception as exc:
            logger.exception("Android push dispatch failed for notification %s.", notification.pk)
            result["errors"].append(f"Android: {exc}")
    if grouped[PushDevice.Platform.IOS]:
        try:
            result["ios"] = _send_ios(notification, grouped[PushDevice.Platform.IOS])
        except Exception as exc:
            logger.exception("iOS push dispatch failed for notification %s.", notification.pk)
            result["errors"].append(f"iOS: {exc}")
    result["sent_total"] = result["android"] + result["ios"]
    return result
