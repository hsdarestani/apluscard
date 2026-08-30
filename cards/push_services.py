import base64
import json
import logging
import time
from collections import defaultdict
from datetime import timedelta
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import httpx
import jwt
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import AppNotification, PushDevice

logger = logging.getLogger(__name__)

_APNS_TOKEN_CACHE = {"value": "", "expires_at": 0}
_FIREBASE_APP = None
_PUSH_IMAGE_CANVAS = (1200, 600)
_PUSH_IMAGE_SAFE_AREA = (1080, 520)


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


def _local_media_storage_name(image_url):
    value = str(image_url or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        public_host = urlparse(str(settings.APP_PUBLIC_BASE_URL or "")).netloc.lower()
        if public_host and parsed.netloc.lower() != public_host:
            return ""
        value = parsed.path

    media_path = urlparse(str(settings.MEDIA_URL or "/media/")).path or "/media/"
    if not media_path.startswith("/"):
        media_path = f"/{media_path}"
    if not media_path.endswith("/"):
        media_path = f"{media_path}/"
    if not value.startswith(media_path):
        return ""
    return unquote(value[len(media_path):].lstrip("/"))


def _push_safe_local_image_url(image_url):
    storage_name = _local_media_storage_name(image_url)
    if not storage_name or not default_storage.exists(storage_name):
        return ""

    source_path = PurePosixPath(storage_name)
    derived_name = str(source_path.parent / "push" / f"{source_path.stem}-push.jpg")
    if default_storage.exists(derived_name):
        return default_storage.url(derived_name)

    with default_storage.open(storage_name, "rb") as source_file:
        with Image.open(source_file) as image:
            image.load()
            source = ImageOps.exif_transpose(image).convert("RGB")

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    canvas_width, canvas_height = _PUSH_IMAGE_CANVAS
    safe_width, safe_height = _PUSH_IMAGE_SAFE_AREA

    background = ImageOps.fit(source, _PUSH_IMAGE_CANVAS, method=resampling)
    background = background.filter(ImageFilter.GaussianBlur(radius=28))
    background = ImageEnhance.Brightness(background).enhance(0.42)

    foreground = source.copy()
    foreground.thumbnail(_PUSH_IMAGE_SAFE_AREA, resampling)
    x = (canvas_width - foreground.width) // 2
    y = (canvas_height - foreground.height) // 2
    background.paste(foreground, (x, y))

    output = BytesIO()
    background.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    saved_name = default_storage.save(derived_name, ContentFile(output.getvalue()))
    return default_storage.url(saved_name)


def _notification_image_url(notification):
    source = notification.data if isinstance(notification.data, dict) else {}
    image_url = str(source.get("image_url") or "").strip()
    if not image_url:
        return ""
    try:
        push_safe_url = _push_safe_local_image_url(image_url)
    except Exception:
        logger.exception("Could not prepare push-safe image for notification %s.", getattr(notification, "pk", "?"))
        push_safe_url = ""
    return _absolute_url(push_safe_url or image_url)


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
        if key in {"image_url", "push_image_url"}:
            payload[str(key)] = _absolute_url(value)
        elif isinstance(value, (dict, list)):
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
        return 0, []
    from firebase_admin import messaging

    image_url = _notification_image_url(notification) or None
    message = messaging.MulticastMessage(
        tokens=[device.token for device in devices],
        notification=messaging.Notification(
            title=notification.title,
            body=notification.body,
            image=image_url,
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
                image=image_url,
            ),
        ),
    )
    response = messaging.send_each_for_multicast(message, app=_firebase_app())
    invalid_ids = []
    errors = []
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
        detail = str(error or "Unbekannter FCM-Fehler")
        errors.append(f"Android Gerät {device.pk}: {detail}")
        logger.warning("Android push failed for device %s: %s", device.pk, error)
    if invalid_ids:
        PushDevice.objects.filter(pk__in=invalid_ids).update(is_active=False)
    return response.success_count, errors


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
        return 0, []
    endpoint = "https://api.sandbox.push.apple.com" if settings.APNS_USE_SANDBOX else "https://api.push.apple.com"
    unread_count = AppNotification.objects.filter(recipient=notification.recipient, is_read=False).count()
    image_url = _notification_image_url(notification)
    aps = {
        "alert": {"title": notification.title, "body": notification.body},
        "sound": "default",
        "badge": unread_count,
        "thread-id": "sams-card",
    }
    if image_url:
        aps["mutable-content"] = 1
    payload = {
        "aps": aps,
        **_string_data(notification),
    }
    if image_url:
        payload["media-url"] = image_url
    headers = {
        "authorization": f"bearer {_apns_auth_token()}",
        "apns-topic": settings.IOS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    success_count = 0
    invalid_ids = []
    errors = []
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
            reason = reason or "Unbekannter APNs-Fehler"
            if response.status_code in {400, 410} and reason in {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}:
                invalid_ids.append(device.pk)
            detail = f"iOS Gerät {device.pk}: HTTP {response.status_code} {reason}"
            errors.append(detail)
            logger.warning("iOS push failed for device %s: HTTP %s %s", device.pk, response.status_code, reason)
    if invalid_ids:
        PushDevice.objects.filter(pk__in=invalid_ids).update(is_active=False)
    return success_count, errors


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
            result["android"], android_errors = _send_android(notification, grouped[PushDevice.Platform.ANDROID])
            result["errors"].extend(android_errors)
        except Exception as exc:
            logger.exception("Android push dispatch failed for notification %s.", notification.pk)
            result["errors"].append(f"Android: {exc}")
    if grouped[PushDevice.Platform.IOS]:
        try:
            result["ios"], ios_errors = _send_ios(notification, grouped[PushDevice.Platform.IOS])
            result["errors"].extend(ios_errors)
        except Exception as exc:
            logger.exception("iOS push dispatch failed for notification %s.", notification.pk)
            result["errors"].append(f"iOS: {exc}")
    result["sent_total"] = result["android"] + result["ios"]
    return result
