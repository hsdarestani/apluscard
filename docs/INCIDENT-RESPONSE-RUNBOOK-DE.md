# Incident-Response-Runbook – SAMS Club Lounge

**Stand:** 06.08.2026  
Dieses Runbook unterstützt technische und organisatorische Reaktion. Datenschutzrechtliche Meldeentscheidungen trifft der Verantwortliche mit Rechts-/Datenschutzberatung.

## 1. Kontakte vor Produktivfreigabe ergänzen

| Rolle | Name | Telefon | E-Mail | Stellvertretung |
|---|---|---|---|---|
| Incident Lead | `[OFFEN]` |  |  |  |
| Geschäftsführung/Verantwortlicher | `[OFFEN]` |  |  |  |
| Technische Leitung | `[OFFEN]` |  |  |  |
| Datenschutzberatung/DSB | `[OFFEN]` |  |  |  |
| Rechtsanwalt | `[OFFEN]` |  |  |  |
| Steuerberatung bei Finanzvorfall | `[OFFEN]` |  |  |  |
| STRATO Support | `[OFFEN]` |  |  |  |
| Cyberversicherung | `[OFFEN/NICHT VORHANDEN]` |  |  |  |

## 2. Prioritäten

1. Menschen und laufende Geschäftsprozesse schützen.
2. weitere Offenlegung, Manipulation oder finanzielle Fehlbuchung stoppen.
3. Beweismittel unverändert sichern.
4. Verfügbarkeit kontrolliert wiederherstellen.
5. Betroffene Daten, Zeitraum und Risiko bestimmen.
6. rechtliche Melde- und Informationspflichten fristgerecht entscheiden.
7. Ursache dauerhaft beseitigen und dokumentieren.

## 3. Schweregrade

| Stufe | Beispiel | Reaktion |
|---|---|---|
| SEV-1 kritisch | aktiver Kundendatenabfluss, kompromittierter Root-/Signing-Key, manipulierte Wallet-Salden, flächiger Ausfall | sofortige Eskalation, Incident Lead, ggf. Dienst isolieren |
| SEV-2 hoch | privilegiertes Konto übernommen, Backup kompromittiert, begrenzte personenbezogene Offenlegung | innerhalb 30 Minuten eskalieren |
| SEV-3 mittel | wiederholte Fehlversuche, einzelne verdächtige Transaktion, Sicherheitskontrolle ausgefallen | am selben Arbeitstag untersuchen |
| SEV-4 niedrig | Scanbefund ohne bestätigte Ausnutzung, Verbesserungsvorschlag | regulärer Security-Prozess |

## 4. Erste 15 Minuten

- Incident-ID erzeugen: `SAMS-IR-YYYYMMDD-NNN`.
- Zeitpunkt der ersten Kenntnis in UTC und Europe/Berlin notieren.
- keine Logs, Auditdaten oder betroffenen Systeme löschen.
- Screenshot/Alarm/Reporter und genaue Beobachtung sichern.
- Incident Lead und technische Leitung informieren.
- betroffene Konten, API-Schlüssel, Server und Datenkategorien grob bestimmen.
- bei aktivem Angriff Zugriff begrenzen, ohne Beweise unnötig zu verändern.

## 5. Eindämmung

Je nach Vorfall:

- kompromittiertes Benutzerkonto sperren und Sessions widerrufen;
- 2FA im dokumentierten Notfallprozess zurücksetzen;
- GitHub-, SSH-, Apple-, Firebase-, SMTP- oder Backup-Secrets rotieren;
- betroffenen Endpoint über Reverse Proxy/Firewall sperren;
- Push-/E-Mail-Versand pausieren;
- Zahlungsfunktion oder einzelnen Standort auf Read-only/Notbetrieb setzen;
- alten Schlüssel widerrufen, nachdem neue Konfiguration geprüft ist;
- bei Datenbankverdacht Schreibzugriffe kontrolliert stoppen;
- keinen produktiven Ledger-Eintrag löschen; falsche Werte über Prüffall/Gegenbuchung korrigieren.

## 6. Beweissicherung

Mindestens sichern:

- GitHub Actions Run, Commit und Deployment-Zeit;
- Server-Journal, Nginx-, Docker- und Anwendungslogs;
- Audit-JSONL und letztes Hash-Kettenende;
- relevante Datenbankzeilen als schreibgeschützten Export;
- Authentifizierungs-, Rollen- und 2FA-Ereignisse;
- Liste betroffener Secrets mit Erstellungs-/Widerrufszeit;
- Netzwerk-/WAF-Ereignisse, soweit vorhanden;
- Backup-Snapshot-ID vor Änderungen;
- alle durchgeführten Maßnahmen mit Benutzer und Zeit.

Beweise erhalten eine Prüfsumme und werden zugriffsbeschränkt abgelegt. Kundendaten dürfen nicht in öffentliche Issues oder Chatverläufe kopiert werden.

## 7. Datenschutzbewertung

Innerhalb der ersten Stunden gemeinsam mit Datenschutz-/Rechtsberatung dokumentieren:

- Welche personenbezogenen Daten sind betroffen?
- Wie viele Personen und Datensätze?
- Waren Daten verschlüsselt/pseudonymisiert?
- Wurden Daten nur verfügbar, tatsächlich abgerufen oder verändert?
- Sind Finanzdaten, Identitätsdaten, Zugangsdaten oder besonders schutzbedürftige Informationen betroffen?
- Welche möglichen Folgen bestehen für Betroffene?
- Welche Gegenmaßnahmen wurden bereits wirksam?
- Besteht voraussichtlich ein Risiko für Rechte und Freiheiten?
- Besteht ein hohes Risiko mit Pflicht zur direkten Information?
- Wann begann die 72-Stunden-Frist aus Sicht des Verantwortlichen?

Die Entscheidung über Meldung an die Aufsichtsbehörde und Information Betroffener wird schriftlich freigegeben. Auch die Entscheidung, nicht zu melden, wird begründet dokumentiert.

## 8. Wiederherstellung

1. Ursache und Persistenzmechanismus beseitigen.
2. neue Secrets/Schlüssel mit Least Privilege bereitstellen.
3. betroffene Version mit Tests und Security-Review neu bauen.
4. Backup-Integrität und Audit-Hash-Kette prüfen.
5. bei Restore temporäre Datenbank testen, bevor Production ersetzt wird.
6. Health-, Login-, Rollen-, Zahlung-, Push-, Wallet- und Datenschutz-Smoke-Tests ausführen.
7. Dienst schrittweise freigeben und Monitoring erhöhen.
8. Rollback-Option bis zur bestätigten Stabilität erhalten.

## 9. Kommunikationsvorlagen

### Interne Erstmeldung

```text
Incident-ID:
Zeitpunkt Kenntnisnahme:
Schweregrad:
Betroffenes System:
Kurzbeschreibung:
Aktive Auswirkung:
Bereits eingedämmt:
Mögliche Datenkategorien:
Incident Lead:
Nächster Status um:
```

### Technischer Status ohne Kundendaten

```text
Wir untersuchen derzeit eine Sicherheits-/Verfügbarkeitsstörung im SAMS-System.
Die betroffene Funktion wurde vorsorglich eingeschränkt. Finanz- und Auditdaten
werden nicht gelöscht; Wiederherstellung und Integritätsprüfungen laufen.
Nächste Aktualisierung: [ZEIT].
```

### Betroffeneninformation

Nur nach anwaltlicher/DSB-Freigabe; muss Art des Vorfalls, wahrscheinliche Folgen, ergriffene Maßnahmen, Kontakt und konkrete Schutzschritte verständlich enthalten.

## 10. Abschluss und Lessons Learned

Innerhalb von fünf Arbeitstagen nach Stabilisierung:

- Timeline finalisieren;
- Root Cause und beitragende Faktoren dokumentieren;
- Umfang betroffener Daten und Personen bestätigen;
- Melde-/Informationsentscheidungen archivieren;
- rotierte Secrets und widerrufene Zugänge prüfen;
- Gegenmaßnahmen mit Verantwortlichem und Frist erfassen;
- Tests und Runbooks aktualisieren;
- Wirksamkeitskontrolle terminieren;
- Abschluss durch Geschäftsführung, Datenschutz und Technik freigeben.

## 11. Pflichtfelder im Abschlussbericht

| Feld | Inhalt |
|---|---|
| Incident-ID |  |
| Beginn/Ende |  |
| Kenntnisnahme |  |
| Systeme |  |
| Datenkategorien |  |
| Anzahl Betroffene |  |
| Ursache |  |
| Ausnutzung bestätigt |  |
| finanzielle Auswirkung |  |
| Eindämmung |  |
| Wiederherstellung |  |
| Datenschutzmeldung |  |
| Betroffeneninformation |  |
| verbleibendes Risiko |  |
| Maßnahmen/Fristen |  |
| Freigaben |  |
