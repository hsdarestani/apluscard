class SecurityHeadersMiddleware:
    """Reduce passive stack fingerprinting and apply browser hardening."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Permitted-Cross-Domain-Policies"] = "none"
        response["X-Download-Options"] = "noopen"
        response["Referrer-Policy"] = "same-origin"
        response["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        response["Origin-Agent-Cluster"] = "?1"
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data: blob: https://appleid.cdn-apple.com; "
            "font-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "media-src 'self' blob:; "
            "worker-src 'self' blob:; "
            "form-action 'self' https://appleid.apple.com"
        )
        content_type = response.get("Content-Type", "").lower()
        is_html = content_type.startswith("text/html")
        if is_html or (getattr(request, "user", None) and request.user.is_authenticated):
            response["Cache-Control"] = "private, no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
