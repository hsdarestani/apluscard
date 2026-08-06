"""Reliable push queueing for notifications created in bulk."""

from django.db import transaction


def install_notification_queueing():
    from . import experience_services
    from .push_models import PushDelivery

    original = experience_services.create_notifications
    if getattr(original, "_sams_push_queueing", False):
        return

    def create_notifications_with_push_queue(*args, **kwargs):
        notifications = original(*args, **kwargs)
        if notifications:
            def enqueue():
                PushDelivery.objects.bulk_create(
                    [PushDelivery(notification_id=item.pk) for item in notifications if item.pk],
                    ignore_conflicts=True,
                )
            transaction.on_commit(enqueue)
        return notifications

    create_notifications_with_push_queue._sams_push_queueing = True
    experience_services.create_notifications = create_notifications_with_push_queue
