# SAMS Club Lounge – Prüfpaket für Rechts- und Datenschutzberatung

**Status:** Technischer Arbeitsentwurf zur anwaltlichen Prüfung  
**Stand:** 06.08.2026  
**Kein Ersatz für Rechtsberatung.** Offene Felder müssen vor Freigabe durch den Verantwortlichen, Rechtsanwalt und gegebenenfalls Datenschutzbeauftragten ergänzt werden.

## 1. Benötigte Freigabeentscheidungen

Bitte schriftlich festlegen und freigeben:

1. Wer ist datenschutzrechtlich Verantwortlicher für die App und das Kundenguthaben?
2. Welche Rolle hat A+ Solution GmbH: Verantwortlicher, Auftragsverarbeiter oder gemeinsam Verantwortlicher?
3. Welche juristische Person betreibt jeden SAMS-Standort?
4. Welche Rechtsgrundlage gilt je Verarbeitungsvorgang?
5. Welche konkreten Aufbewahrungs- und Löschfristen gelten?
6. Welche Unterauftragsverarbeiter und internationalen Übermittlungen werden freigegeben?
7. Ist ein Datenschutzbeauftragter erforderlich oder freiwillig benannt?
8. Welche zuständige Datenschutzaufsichtsbehörde ist anzugeben?
9. Sind Datenschutz-Folgenabschätzung oder besondere Risikobewertung erforderlich?
10. Welche finale Fassung von Datenschutzerklärung, AGB und Einwilligungstexten wird veröffentlicht?

## 2. Produktbeschreibung

Die Anwendung bietet:

- digitales Mitgliedskonto und Mitgliedskarte;
- geschlossenes Kundenguthaben für definierte SAMS-Standorte;
- Aufladungen, Belastungen, Trinkgeld, Erstattungen und nachvollziehbare Gegenbuchungen;
- digitale Belege und Transaktionsprüffälle;
- standortbezogene Angebote;
- In-App- und Push-Mitteilungen;
- Sign in with Apple sowie klassische Anmeldung;
- Apple Wallet Pass;
- rollenbasierte Funktionen für Kunde, Mitarbeiter, Leitung und Inhaber.

Nicht vorgesehen sind derzeit:

- Barauszahlung des Guthabens;
- Übertragung zwischen Kunden;
- Verzinsung;
- Nutzung bei beliebigen externen Akzeptanzstellen;
- automatisierte Kreditentscheidung oder Profiling mit Rechtswirkung.

## 3. Datenkategorien

### Kundenkonto

- Name
- E-Mail-Adresse
- optional Telefonnummer
- optional Geburtsdatum
- Altersbestätigung
- E-Mail-Verifizierungsstatus
- Authentifizierungs- und Kontostatus

### Mitgliedschaft und Guthaben

- interne Wallet-ID
- Mitgliedsnummer
- Treuestufe
- Status
- aktueller Saldo
- monatliche Aufladesumme
- gewählter Standort

### Finanz- und Nachweisdaten

- Aufladung, Zahlung, Trinkgeld, Bonus, Erstattung und Korrektur
- Betrag und Saldo vor/nach Buchung
- Belegnummer
- Standort
- ausführender Benutzer
- Zeitstempel
- Kassen-/Bestellreferenz
- Beschreibung und Prüffall

### Sicherheits- und Betriebsdaten

- Rolle und Berechtigungen
- Audit-Ereignisse und kryptografische Integritätssiegel
- IP-Adresse bei sicherheits- oder finanzrelevanten Vorgängen
- Geräte-/Push-Token
- Einwilligungs- und Rechtsdokumentversionen
- Datenexport- und Löschanträge
- Backup- und Restore-Nachweise

## 4. Verarbeitungstätigkeiten und vorgeschlagene Rechtsgrundlagen

Die folgende Zuordnung ist **nur ein Prüfentwurf**:

| Tätigkeit | Zweck | Kandidat für Rechtsgrundlage | Prüfung erforderlich |
|---|---|---|---|
| Konto und Mitgliedschaft | Vertrag und Nutzung der App | Art. 6 Abs. 1 lit. b DSGVO | Ja |
| Guthaben und Buchungsnachweis | Vertragsdurchführung, Abrechnung | Art. 6 Abs. 1 lit. b und lit. c | Ja |
| Audit- und Sicherheitsprotokoll | Missbrauchsschutz, Nachweis | Art. 6 Abs. 1 lit. c oder lit. f | Ja, Interessenabwägung |
| Pflichtmitteilungen zu Zahlungen/Sicherheit | Vertrag und Sicherheit | Art. 6 Abs. 1 lit. b/f | Ja |
| Marketing-Push | Werbung | Einwilligung, Art. 6 Abs. 1 lit. a | Ja |
| Marketing-E-Mail | Werbung | Einwilligung und UWG-Prüfung | Ja |
| Altersbestätigung | Zugangskontrolle | Vertrag/rechtliche Pflicht/berechtigtes Interesse | Ja |
| Geburtsdatum und Geburtstagsbonus | freiwilliger Vorteil | Einwilligung oder Vertrag | Ja |
| Backups | Verfügbarkeit und Nachweis | gleiche Grundlage wie Quelldaten | Ja |

## 5. Empfänger und Unterauftragsverarbeiter

Für jeden Dienst müssen Vertrag, Region, Zweck, Datenkategorien, Löschregeln und internationale Übermittlung dokumentiert werden:

| Dienst | Vorgesehener Zweck | Offene Unterlagen |
|---|---|---|
| STRATO | Server/Hosting | AVV, Standort, TOM |
| Cloudflare, soweit aktiv | DNS, Proxy, Schutz | AVV/DPA, Region, Drittlandprüfung |
| Apple | Login, APNs, Wallet, Store | Bedingungen, Datenschutzrollen |
| Google/Firebase | Android Push, Play Store | DPA, SCC/TIA soweit erforderlich |
| SMTP-Anbieter | transaktionale E-Mails | AVV, Hostingregion |
| GitHub | Quellcode und CI/CD | Zugriffs- und Vertragsprüfung |
| Offsite-Backup-Ziel | verschlüsselte Sicherungen | AVV, Region, Zugriff |

## 6. Betroffenenrechte

Technisch vorgesehen:

- öffentliche Datenschutzerklärung;
- Anzeige der gültigen Dokumentversionen;
- protokollierte Annahme von AGB und Datenschutzhinweisen;
- getrennte freiwillige Marketing-Einwilligungen;
- authentifizierter Datenexport als JSON;
- Löschantrag mit Status und Referenz;
- Widerruf von Sign in with Apple beim Abschluss der Löschung;
- Löschung oder Anonymisierung direkter Identifikatoren;
- Erhalt gesetzlich erforderlicher Finanz- und Nachweisdaten;
- Auditierung von Export- und Löschvorgängen.

Noch festzulegen:

- Identitätsprüfung bei manuellen Auskunftsersuchen;
- Antwortkanal und Verantwortliche;
- Fristen- und Eskalationskalender;
- konkrete Anonymisierungsregeln;
- zulässige Einschränkungen der Löschung;
- Musterantworten für Auskunft, Berichtigung, Einschränkung und Widerspruch.

## 7. Einwilligungen

Die finale Gestaltung soll sicherstellen:

- keine vorangekreuzten Marketingfelder;
- getrennte Zustimmung für Push und E-Mail;
- verständliche Zweckbeschreibung;
- freiwillige Einwilligung ohne Nachteil für Kernfunktionen;
- dokumentierte Version, Zeitpunkt, Quelle und Benutzer;
- jederzeit ebenso einfache Widerrufsmöglichkeit;
- Pflichtmitteilungen zu Konto, Zahlung und Sicherheit werden nicht als Marketing behandelt.

## 8. Löschung und Aufbewahrung

Die technische Löschung produktiver Ledger- und Audit-Daten ist gesperrt. Fehler werden durch Gegenbuchung und neues Audit-Ereignis korrigiert. Eine endgültige Fristenmatrix ist durch Rechts- und Steuerberatung freizugeben.

Siehe `RETENTION-MATRIX-DE.md`.

## 9. Technische und organisatorische Maßnahmen

Siehe:

- `COMPLIANCE-SECURITY-ARCHITECTURE-DE.md`
- `TOM-DE.md`
- `INCIDENT-RESPONSE-RUNBOOK-DE.md`

Wesentliche Kontrollen:

- HTTPS/TLS und sichere Cookies;
- Argon2-Passwort-Hashing;
- verpflichtende TOTP-2FA für Inhaber und Leitung;
- Rollen- und Mandantentrennung;
- kurzlebige signierte Zahlungs-QR-Codes;
- transaktionale Saldoänderungen und Idempotenz;
- unveränderliche Finanzdaten;
- verkettete SHA-256-Integritätssiegel für Audit-Ereignisse;
- verschlüsselte Offsite-Backups und regelmäßige Restore-Tests;
- Rate Limits, CSRF-, XSS-, SQL-Injection- und Clickjacking-Schutz;
- minimierte Secrets und SSH-Key-Deployment.

## 10. Datenschutzverletzungen

Der Incident-Prozess muss Verantwortliche, 72-Stunden-Bewertung, Beweissicherung und Kommunikation festlegen. Technischer Runbook-Entwurf: `INCIDENT-RESPONSE-RUNBOOK-DE.md`.

## 11. Offizielle Referenzen

- DSGVO, insbesondere Art. 5, 6, 12–22, 24, 25, 28, 30, 32–36: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- BfDI – Datenschutz-Grundverordnung: https://www.bfdi.bund.de/DE/Fachthemen/Inhalte/Europa-Internationales/DSGVO.html

## 12. Unterschrifts-/Freigabeblock

| Rolle | Name | Datum | Freigabe/Anmerkung |
|---|---|---|---|
| Verantwortlicher |  |  |  |
| Rechtsanwalt |  |  |  |
| Datenschutzberatung/DSB |  |  |  |
| Technische Leitung |  |  |  |
