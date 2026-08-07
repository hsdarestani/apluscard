# Technische und organisatorische Maßnahmen (TOM) – SAMS Club Lounge

**Arbeitsentwurf nach Art. 32 DSGVO**  
**Stand:** 06.08.2026  
Die Wirksamkeit ist regelmäßig zu prüfen und organisatorische Verantwortliche müssen ergänzt werden.

## 1. Zutritts- und Infrastrukturschutz

- Produktivbetrieb auf STRATO-Server in dokumentierter Umgebung.
- Administrativer Serverzugriff ausschließlich über SSH-Schlüssel.
- Passwortbasierter automatisierter Deployment-Zugriff wird nicht verwendet.
- Root-/Systemzugänge werden auf den notwendigen Personenkreis beschränkt.
- Server-, Hosting- und Rechenzentrumsmaßnahmen werden über Anbieterunterlagen/AVV nachgewiesen.
- Nicht benötigte Ports und Dienste sind zu deaktivieren; Firewall- und Patchstatus sind regelmäßig zu prüfen.

## 2. Zugangskontrolle

- Passwörter werden mit Argon2 gehasht; keine Klartextspeicherung.
- Inhaber und Leitung müssen TOTP-Zwei-Faktor-Authentifizierung einrichten.
- TOTP-Secrets werden verschlüsselt gespeichert.
- Wiederherstellungscodes werden nur einmal angezeigt und ausschließlich gehasht gespeichert.
- Einmalcodes besitzen Replay-Schutz.
- Privilegierte 2FA-Sitzung läuft spätestens nach zwölf Stunden ab.
- Notfall-Reset ist nur per dokumentiertem Management-Befehl mit Begründung möglich und wird auditiert.
- Login-, Registrierungs-, Apple-Login-, MFA- und QR-Endpunkte besitzen Rate Limits.
- Sitzungs-ID wird nach MFA-Verifikation rotiert.

## 3. Zugriffskontrolle und Rollen

- Rollen: Kunde, Mitarbeiter, Leitung, Inhaber, technischer Superuser.
- Zugriff ist an Betrieb und aktive Mitgliedschaft gebunden.
- Mitarbeiter können Zahlungen nur für ihren Betrieb und aktive Standorte ausführen.
- Aufladung, direkte Erstattung und zentrale Einstellungen sind auf Inhaber beschränkt.
- Finanz- und Auditmodelle sind im Admin schreibgeschützt.
- API und Browseransicht verwenden dieselben Rollen- und QR-Prüfungen.
- Berechtigungen sind bei Rollenwechsel oder Ausscheiden unverzüglich zu deaktivieren.

## 4. Übertragungskontrolle

- Produktivzugriff ausschließlich über HTTPS/TLS.
- Secure-, HttpOnly- und SameSite-Cookies.
- HSTS nach erfolgreicher TLS-Abnahme.
- CSRF-Schutz für Browseraktionen.
- Geheimnisse und Schlüssel werden nicht im Repository gespeichert.
- Deployment-Secrets werden über GitHub Secrets und SSH-Schlüssel übertragen.
- Offsite-Backups werden vor Verlassen des Servers mit Restic verschlüsselt.
- Kundendaten dürfen nicht in Issues, Actions-Logs oder Support-Screenshots erscheinen.

## 5. Eingabekontrolle und Nachvollziehbarkeit

- Jede Finanzbuchung enthält eindeutige Belegnummer, Betrag, Saldo vor/nachher, Benutzer, Standort und Zeit.
- Audit-Ereignisse dokumentieren Registrierung, Einwilligung, Rollen-/Statusänderung, Zahlung, Aufladung, Erstattung, Datenexport, Löschvorgang und MFA-Aktionen.
- Audit-Ereignisse werden in einer fortlaufenden SHA-256-Hash-Kette versiegelt.
- Änderung oder Lücke der Kette wird durch automatisierte Integritätsprüfung erkannt.
- Produktive Finanz- und Auditdaten können nicht regulär gelöscht werden.
- Korrekturen erfolgen durch Gegenbuchung und neues Audit-Ereignis.

## 6. Auftragskontrolle

- Dienstleister dürfen Daten nur auf dokumentierte Weisung und vertraglicher Grundlage verarbeiten.
- AV-Verträge, Datenregion, Unterauftragsverarbeiter und Löschverfahren sind vor Freigabe zu dokumentieren.
- Secrets werden je Dienst getrennt und nach Personal-/Dienstleisterwechsel rotiert.
- Produktionszugriff von Entwicklern ist auf notwendige Wartung und dokumentierte Incidents beschränkt.

## 7. Verfügbarkeitskontrolle

- PostgreSQL, Media, verschlüsselte Konfiguration und Audit-Beweisexport werden regelmäßig gesichert.
- Backup-Intervall: alle sechs Stunden.
- Backup-Aufbewahrung technisch: 7-Tage-Fenster, 30 täglich, 12 wöchentlich, 12 monatlich, 3 jährlich; rechtliche Freigabe erforderlich.
- Wöchentlicher Restore-Drill in eine temporäre Datenbank.
- Restore-Drill prüft Prüfsummen, Migrationen, Wallet-Anzahl und vollständige Audit-Hash-Kette.
- Backup- und Restore-Status werden als maschinenlesbare Statusdatei gespeichert.
- Alte Produktionsinstanz wird bei Migration zeitlich begrenzt als Rollback gehalten.

## 8. Trennungsgebot

- Daten werden über Betrieb, Standort, Benutzer und Wallet logisch getrennt.
- Produktions-, Test- und CI-Umgebungen verwenden getrennte Zugangsdaten.
- Produktive Hard-Delete-Funktion ist deaktiviert.
- Testdatenlöschung erfordert gleichzeitig Testumgebung, ausdrückliche Testkonto-Markierung und Inhaberbestätigung.
- Marketing-Einwilligungen werden getrennt von Pflichtmitteilungen verwaltet.

## 9. Datenschutz durch Technikgestaltung

- Telefonnummer und Geburtsdatum sind optional, soweit betrieblich nicht erforderlich.
- Marketing-Push und Marketing-E-Mail benötigen getrennte freiwillige Einwilligung.
- Zahlungs-QR enthält einen kurzlebigen signierten Token statt einer dauerhaften statischen Kennung.
- Datenexport wird nur authentifiziert ausgegeben, nicht gecacht und auditiert.
- Löschanträge besitzen Referenz und Status; Identifikatoren werden nach Freigabe gelöscht/anonymisiert, während erforderliche Nachweise erhalten bleiben.

## 10. Anwendungssicherheit

- Django ORM statt dynamischer SQL-Zusammensetzung.
- serverseitige Validierung von Beträgen und Rollen.
- Datenbanktransaktionen und Zeilensperren bei Saldoänderung.
- Idempotenzschlüssel gegen Doppelbuchung.
- Content Security Policy, Clickjacking- und MIME-Schutz.
- eingeschränkte Uploadtypen, Größenprüfung und Bildnormalisierung.
- selbst gehostete, checksum-geprüfte Scanner-Bibliothek.
- wöchentliche Dependency-Prüfung und statische Sicherheitsanalyse.
- Dependabot für Python, Mobile-NPM, Docker und GitHub Actions.

## 11. Kontroll- und Prüfplan

| Kontrolle | Rhythmus | Nachweis | Verantwortlich |
|---|---|---|---|
| Dependency- und Code-Sicherheitsaudit | wöchentlich/bei PR | GitHub Actions | Technische Leitung |
| Backup | alle 6 Stunden | Statusdatei/Restic-Snapshot | Betrieb |
| Restore-Drill | wöchentlich | Restore-Status/Logs | Betrieb |
| Audit-Hash-Kette | bei Backup und Restore | Command-Ausgabe/JSONL | Betrieb |
| Rollen- und Zugriffsreview | monatlich und bei Austritt | Checkliste | Betreiber |
| Secret-Rotation | mindestens jährlich/bei Ereignis | Rotationsprotokoll | Technische Leitung |
| Incident-Übung | mindestens jährlich | Übungsprotokoll | Betreiber/DSB |
| TOM-Review | jährlich und bei wesentlicher Änderung | freigegebene Version | Verantwortlicher |

## 12. Offene organisatorische Punkte

- `[OFFEN]` benannte technische und datenschutzrechtliche Verantwortliche
- `[OFFEN]` AV-Verträge und Unterauftragsverarbeiterliste
- `[OFFEN]` Firewall-/Patch- und Server-Hardening-Nachweis
- `[OFFEN]` dokumentierter Rollenreview mit realen Namen
- `[OFFEN]` freigegebene Aufbewahrungsfristen
- `[OFFEN]` getestete Kontaktkette für Datenschutzverletzungen
- `[OFFEN]` schriftliche ZAG- und Steuerberaterbewertung

## 13. Freigabe

| Rolle | Name | Datum | Freigabe |
|---|---|---|---|
| Verantwortlicher |  |  |  |
| Datenschutzberatung/DSB |  |  |  |
| Technische Leitung |  |  |  |
