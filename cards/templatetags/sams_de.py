from django import template

register = template.Library()

LABELS = {
    "OWNER": "Inhaber",
    "MANAGER": "Leitung",
    "STAFF": "Mitarbeiter",
    "ACTIVE": "Aktiv",
    "BLOCKED": "Gesperrt",
    "CLOSED": "Geschlossen",
    "SILVER": "Silber",
    "GOLD": "Gold",
    "PLATINUM": "Platin",
    "TOPUP": "Aufladung",
    "PURCHASE": "Zahlung",
    "TIP": "Trinkgeld",
    "REFUND": "Erstattung",
    "BONUS": "Bonus",
    "ADJUSTMENT": "Korrektur",
    "PENDING": "Wartet auf Bestätigung",
    "CONFIRMED": "Bestätigt",
    "CANCELLED": "Storniert",
    "EXPIRED": "Abgelaufen",
    "ALL": "Alle",
    "WEB": "Browser",
}


@register.filter
def sams_label(value):
    return LABELS.get(str(value), value)
