"""Reliable push queueing for notifications created in bulk."""

from django.db import transaction


def install_notification_queueing():
    from . import experience_services
    from .legal_models import PrivacyPreference
    from .models import AppNotification
    from .push_models import PushDelivery

    original = experience_services.create_notifications
    if getattr(original, "_sams_push_queueing", False):
        return

    def create_notifications_with_push_queue(*args, **kwargs):
        notifications = original(*args, **kwargs)
        if notifications:
            def enqueue():
                marketing_kinds = {
                    AppNotification.Kind.OFFER,
                    AppNotification.Kind.BIRTHDAY,
                }
                marketing_notifications = [
                    item for item in notifications if item.kind in marketing_kinds
                ]
                consented_pairs = set()
                if marketing_notifications:
                    user_ids = {item.recipient_id for item in marketing_notifications}
                    business_ids = {item.business_id for item in marketing_notifications}
                    consented_pairs = set(
                        PrivacyPreference.objects.filter(
                            user_id__in=user_ids,
                            business_id__in=business_ids,
                            marketing_push_enabled=True,
                        ).values_list("user_id", "business_id")
                    )

                deliveries = []
                for item in notifications:
                    if not item.pk:
                        continue
                    if (
                        item.kind in marketing_kinds
                        and (item.recipient_id, item.business_id) not in consented_pairs
                    ):
                        # Keep the in-app notification visible, but never queue a
                        # marketing push without the member's explicit consent.
                        continue
                    deliveries.append(PushDelivery(notification_id=item.pk))

                if deliveries:
                    PushDelivery.objects.bulk_create(deliveries, ignore_conflicts=True)

            transaction.on_commit(enqueue)
        return notifications

    create_notifications_with_push_queue._sams_push_queueing = True
    experience_services.create_notifications = create_notifications_with_push_queue
