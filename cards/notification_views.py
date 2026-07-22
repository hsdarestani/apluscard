from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@login_required
@never_cache
def unread_notification_count(request):
    count = request.user.app_notifications.filter(is_read=False).count()
    latest = request.user.app_notifications.order_by("-created_at").values("id", "title", "created_at").first()
    return JsonResponse({
        "count": count,
        "latest": {
            "id": latest["id"],
            "title": latest["title"],
            "created_at": latest["created_at"].isoformat(),
        } if latest else None,
    })
