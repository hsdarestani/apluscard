from django import template
from django.conf import settings

from cards.compliance_models import TestWalletMarker
from cards.compliance_qr import wallet_qr_payload as build_wallet_qr_payload

register = template.Library()


@register.simple_tag
def wallet_qr_payload(wallet):
    return build_wallet_qr_payload(wallet)


@register.simple_tag
def test_purge_allowed(wallet):
    return bool(
        settings.ALLOW_TEST_DATA_PURGE
        and wallet
        and TestWalletMarker.objects.filter(wallet=wallet).exists()
    )
