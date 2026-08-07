import hashlib

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


class ComplianceRateLimitMiddleware:
    """Small application-level safety net for authentication and QR endpoints.

    The reverse proxy should still enforce its own limits. This middleware keeps
    accidental brute-force and scan floods from reaching business logic even
    when the proxy rule is missing or temporarily bypassed.
    """

    LIMITS = {
        ("POST", "/accounts/login/"): (10, 15 * 60),
        ("POST", "/accounts/register/"): (10, 15 * 60),
        ("POST", "/api/v1/auth/apple/native/"): (20, 15 * 60),
        ("POST", "/sicherheit/2fa/einrichten/"): (10, 15 * 60),
        ("POST", "/sicherheit/2fa/bestaetigen/"): (10, 15 * 60),
        ("POST", "/sicherheit/2fa/notfallcodes-neu/"): (5, 15 * 60),
        ("POST", "/staff/charge/"): (120, 5 * 60),
        ("POST", "/api/v1/staff/charge/"): (120, 5 * 60),
        ("GET", "/manager/wallets/scan/"): (240, 5 * 60),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")

    @staticmethod
    def _is_api_request(request):
        return request.path.startswith("/api/") or "application/json" in request.headers.get("Accept", "")

    def __call__(self, request):
        rule = self.LIMITS.get((request.method, request.path))
        if rule is None:
            return self.get_response(request)

        limit, window_seconds = rule
        identity = hashlib.sha256(self._client_ip(request).encode("utf-8")).hexdigest()[:24]
        path_hash = hashlib.sha256(request.path.encode("utf-8")).hexdigest()[:16]
        cache_key = f"sams-rate:{request.method}:{path_hash}:{identity}"

        if cache.add(cache_key, 1, timeout=window_seconds):
            attempts = 1
        else:
            try:
                attempts = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window_seconds)
                attempts = 1

        if attempts <= limit:
            return self.get_response(request)

        payload = {"detail": "Zu viele Anfragen. Bitte später erneut versuchen."}
        response = JsonResponse(payload, status=429) if self._is_api_request(request) else HttpResponse(
            "Zu viele Anfragen. Bitte später erneut versuchen.",
            status=429,
            content_type="text/plain; charset=utf-8",
        )
        response["Retry-After"] = str(window_seconds)
        response["Cache-Control"] = "no-store"
        return response
