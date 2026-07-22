# Apple Wallet Production

Apple Wallet wird über ein A+-Pass-Type-Zertifikat signiert. Zertifikate und Kennwörter bleiben ausschließlich in GitHub Actions Secrets und in der geschützten Production-Umgebung. Der Workflow erzeugt zur Prüfung einen temporären signierten Pass und veröffentlicht weder Mitgliedsdaten noch Secret-Werte.
