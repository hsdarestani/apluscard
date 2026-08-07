import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .experience_models import TransactionCase
from .legal_models import AccountDeletionRequest, LegalAcceptance, PrivacyPreference
from .models import AppNotification, AuditEvent, LedgerEntry, PaymentRequest, PushDevice, Wallet

EXPORT_SIGNING_SALT = "sams-gdpr-export-v1"
EXPORT_LINK_MAX_AGE_SECONDS = 120


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _wallet_for_export(user):
    wallet = Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(owner=user).first()
    if wallet is None or user.business_memberships.filter(is_active=True).exists():
        raise PermissionDenied
    return wallet


def _export_payload(user, wallet):
    profile = getattr(user, "member_profile", None)
    return {
        "exported_at": timezone.now(),
        "controller": wallet.business.name,
        "account": {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
        },
        "profile": {
            "birth_date": profile.birth_date if profile else None,
            "age_confirmed": bool(profile and profile.age_confirmed),
            "email_verified": bool(profile and profile.email_verified),
            "email_verified_at": profile.email_verified_at if profile else None,
        },
        "wallet": {
            "id": wallet.pk,
            "member_number": wallet.member_number,
            "display_name": wallet.display_name,
            "phone": wallet.phone,
            "email": wallet.email,
            "status": wallet.status,
            "tier": wallet.tier,
            "monthly_topup_total": wallet.monthly_topup_total,
            "balance": wallet.balance,
            "created_at": wallet.created_at,
            "updated_at": wallet.updated_at,
        },
        "ledger_entries": list(
            LedgerEntry.objects.filter(wallet=wallet).values(
                "id", "bill_number", "entry_type", "amount", "balance_before", "balance_after",
                "description", "order_reference", "location_id", "payment_request_id", "performed_by_id", "created_at",
            )
        ),
        "payment_requests": list(
            PaymentRequest.objects.filter(wallet=wallet).values(
                "id", "location_id", "base_amount", "tip_selected_amount", "tip_amount", "tip_recipient",
                "description", "order_reference", "status", "created_by_id", "created_at", "confirmed_at", "expires_at",
            )
        ),
        "transaction_cases": list(
            TransactionCase.objects.filter(wallet=wallet).values(
                "id", "case_number", "reason", "status", "description", "requested_amount", "approved_amount",
                "manager_note", "ledger_entry_id", "opened_by_id", "reviewed_by_id", "created_at", "reviewed_at", "updated_at",
            )
        ),
        "privacy_preferences": list(
            PrivacyPreference.objects.filter(user=user, business=wallet.business).values(
                "marketing_push_enabled", "marketing_email_enabled", "consented_at", "withdrawn_at", "updated_at",
            )
        ),
        "legal_acceptances": list(
            LegalAcceptance.objects.filter(user=user, business=wallet.business).values(
                "document_type", "version", "source", "accepted_at",
            )
        ),
        "account_deletion_requests": list(
            AccountDeletionRequest.objects.filter(user=user, business=wallet.business).values(
                "reference_number", "reason", "status", "requested_at", "completed_at",
            )
        ),
        "notifications": list(
            AppNotification.objects.filter(recipient=user, business=wallet.business).values(
                "id", "kind", "title", "body", "data", "location_id", "is_read", "created_at",
            )
        ),
        "push_devices": list(
            PushDevice.objects.filter(user=user).values("platform", "is_active", "updated_at")
        ),
    }


def _export_response(*, user, wallet, request):
    AuditEvent.objects.create(
        actor=user,
        business=wallet.business,
        action="gdpr_data_export",
        object_type="wallet",
        object_id=str(wallet.pk),
        details={"format": "json"},
        ip_address=_client_ip(request),
    )
    content = json.dumps(_export_payload(user, wallet), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="sams-data-export-{wallet.member_number}.json"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


@login_required
@require_GET
def customer_data_export(request):
    wallet = _wallet_for_export(request.user)
    if request.GET.get("handoff") == "1":
        token = signing.dumps(
            {"uid": request.user.pk},
            salt=EXPORT_SIGNING_SALT,
            compress=True,
        )
        url = request.build_absolute_uri(reverse("customer_data_export_download", args=[token]))
        response = JsonResponse({"url": url, "expires_in": EXPORT_LINK_MAX_AGE_SECONDS})
        response["Cache-Control"] = "private, no-store, max-age=0"
        return response
    return _export_response(user=request.user, wallet=wallet, request=request)


@require_GET
def customer_data_export_download(request, token):
    try:
        payload = signing.loads(
            token,
            salt=EXPORT_SIGNING_SALT,
            max_age=EXPORT_LINK_MAX_AGE_SECONDS,
        )
        user_id = int(payload["uid"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise PermissionDenied("Dieser Export-Link ist ungültig oder abgelaufen.")

    user = get_object_or_404(get_user_model(), pk=user_id, is_active=True)
    wallet = _wallet_for_export(user)
    return _export_response(user=user, wallet=wallet, request=request)
