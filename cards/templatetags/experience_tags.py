import re

from django import template

from cards.qr_utils import qr_data_uri as build_qr_data_uri

register = template.Library()


@register.filter
def qr_data_uri(value):
    if not value:
        return ""
    return build_qr_data_uri(value)


@register.filter
def location_phone(address):
    match = re.search(r"Telefon:\s*([^\n]+)", address or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


@register.filter
def location_address_only(address):
    return re.sub(r"\n?Telefon:\s*[^\n]+", "", address or "", flags=re.IGNORECASE).strip()
