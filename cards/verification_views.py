from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@login_required
@require_GET
def email_verification_status(request):
    """Return the current server-side member verification state without caching."""
    profile = getattr(request.user, "member_profile", None)
    response = JsonResponse({"email_verified": bool(profile and profile.email_verified)})
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response
