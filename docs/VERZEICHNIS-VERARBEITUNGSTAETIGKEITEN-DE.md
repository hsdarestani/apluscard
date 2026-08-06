# Verzeichnis von Verarbeitungstätigkeiten – SAMS Club Lounge

**Arbeitsentwurf nach Art. 30 DSGVO**  
**Stand:** 06.08.2026  
Vor Freigabe sind Verantwortlicher, Datenschutzkontakt, Empfänger, Rechtsgrundlagen und Fristen verbindlich zu ergänzen.

## A. Stammdaten des Verantwortlichen

| Feld | Angabe |
|---|---|
| Verantwortlicher | `[OFFEN]` |
| Anschrift | `[OFFEN]` |
| Geschäftsführung | `[OFFEN]` |
| Datenschutzkontakt | `[OFFEN]` |
| Datenschutzbeauftragter | `[OFFEN/NICHT BESTELLT]` |
| Zuständige Aufsichtsbehörde | `[OFFEN]` |
| Technischer Dienstleister | A+ Solution GmbH – Rolle vertraglich festlegen |

## B. Verarbeitungstätigkeiten

### 1. Registrierung und Mitgliedskonto

| Merkmal | Beschreibung |
|---|---|
| Zweck | Einrichtung und Verwaltung der digitalen Mitgliedschaft |
| Betroffene | Kunden/Mitglieder |
| Daten | Name, E-Mail, optional Telefon/Geburtsdatum, Altersbestätigung, Verifizierungsstatus |
| Rechtsgrundlage | `[anwaltlich festlegen; voraussichtlich Vertrag/gesetzliche Pflicht/berechtigtes Interesse]` |
| Empfänger | Hosting, E-Mail-Anbieter, Apple bei Apple Login |
| Drittlandübermittlung | `[prüfen und dokumentieren]` |
| Löschung | siehe freizugebende Fristenmatrix |
| TOM | TLS, Argon2, Rollen, 2FA für Verwaltung, Audit |

### 2. Kundenguthaben und Transaktionen

| Merkmal | Beschreibung |
|---|---|
| Zweck | Aufladung, Einlösung, Erstattung, Beleg und Saldennachweis |
| Betroffene | Kunden, Mitarbeiter, Betreiber |
| Daten | Wallet-ID, Mitgliedsnummer, Beträge, Saldo vorher/nachher, Belegnummer, Standort, Kassierer, Zeit, Referenz |
| Rechtsgrundlage | `[Vertrag/rechtliche Aufbewahrung – festlegen]` |
| Empfänger | Betreiber, Steuerberatung, Finanzbehörden bei Pflicht, Hosting/Backup |
| Drittlandübermittlung | nicht vorgesehen; technische Dienstleister prüfen |
| Löschung | keine vorzeitige Hard-Delete-Funktion; gesetzliche Frist festlegen |
| TOM | DB-Transaktion, Idempotenz, unveränderlicher Ledger, Audit-Hash-Kette, Backup |

### 3. Zahlungs-QR und Betrugsprävention

| Merkmal | Beschreibung |
|---|---|
| Zweck | sichere Zuordnung des Kundenwallets und Verhinderung kopierter Codes |
| Betroffene | Kunden und Kassenpersonal |
| Daten | signierter kurzlebiger Token, Wallet-/Business-ID, Zeitstempel, IP-/Auditdaten |
| Rechtsgrundlage | `[Vertrag/berechtigtes Interesse – Interessenabwägung ergänzen]` |
| Empfänger | nur Betreiber und technischer Dienstleister |
| Löschung | Token läuft technisch ab; Auditfrist gesondert |
| TOM | Signatur, kurze Gültigkeit, automatische Rotation, Rate Limit |

### 4. Pflicht- und Marketingmitteilungen

| Merkmal | Beschreibung |
|---|---|
| Zweck | Zahlungs-/Sicherheitshinweise sowie freiwillige Angebote |
| Betroffene | Kunden/Mitglieder |
| Daten | Nutzer-ID, Push-Token, Plattform, Nachricht, Zustellstatus, Einwilligung |
| Rechtsgrundlage | Pflichtnachricht: `[Vertrag/berechtigtes Interesse]`; Marketing: Einwilligung/UWG-Prüfung |
| Empfänger | Apple APNs, Google Firebase, Hosting |
| Drittlandübermittlung | DPA/SCC/TIA prüfen |
| Löschung | Push-Token bei Abmeldung/Unzustellbarkeit deaktivieren; Frist für Nachrichten festlegen |
| TOM | getrennte Einwilligungen, Rollenprüfung, gezielte Empfänger, Audit |

### 5. Support, Prüffälle und Betroffenenanfragen

| Merkmal | Beschreibung |
|---|---|
| Zweck | Reklamation, Berichtigung, Auskunft, Löschung und Nachweis |
| Betroffene | Kunden, Mitarbeiter |
| Daten | Transaktionsreferenzen, Beschreibung, Kommunikation, Status, Identitätsnachweis soweit nötig |
| Rechtsgrundlage | Vertrag und rechtliche Pflicht |
| Empfänger | Betreiber, Rechts-/Datenschutzberatung bei Bedarf |
| Löschung | Frist je Falltyp festlegen |
| TOM | rollenbasierter Zugriff, Referenznummern, Audit, sichere Exporte |

### 6. Sicherheits-, Zugriffs- und Auditprotokolle

| Merkmal | Beschreibung |
|---|---|
| Zweck | Missbrauchserkennung, Nachweis, Incident Response und Revisionsfähigkeit |
| Betroffene | Kunden, Mitarbeiter, Administratoren |
| Daten | Benutzer, Rolle, Aktion, Objekt, Zeitpunkt, IP, technische Details, kryptografisches Siegel |
| Rechtsgrundlage | `[rechtliche Pflicht/berechtigtes Interesse – festlegen]` |
| Empfänger | Betreiber, technische Sicherheitsverantwortliche, Behörden bei Pflicht |
| Löschung | Frist risikobasiert und nachweissicher festlegen |
| TOM | Unveränderlichkeit, SHA-256-Kette, verschlüsseltes Offsite-Backup, Restore-Test |

### 7. Backups und Disaster Recovery

| Merkmal | Beschreibung |
|---|---|
| Zweck | Wiederherstellbarkeit, Verfügbarkeit und Beweissicherung |
| Betroffene | alle Kategorien der produktiven Anwendung |
| Daten | verschlüsselte Datenbank-, Media-, Konfigurations- und Audit-Sicherung |
| Rechtsgrundlage | gleiche Grundlagen wie Quelldaten plus Art. 32 DSGVO |
| Empfänger | freigegebener Offsite-Backup-Anbieter |
| Drittlandübermittlung | Standort und Vertragsmechanismus prüfen |
| Löschung | Restic-Retention: 7-Tage-Fenster, 30 täglich, 12 wöchentlich, 12 monatlich, 3 jährlich; rechtlich freigeben |
| TOM | Verschlüsselung vor Übertragung, Prüfsummen, Zugriffsschlüssel getrennt, Restore-Drill |

### 8. CI/CD und Softwarebetrieb

| Merkmal | Beschreibung |
|---|---|
| Zweck | Entwicklung, Test, Deployment, Sicherheitsprüfungen |
| Betroffene | grundsätzlich keine Produktivkundendaten im Repository; Administratoren/Entwickler |
| Daten | Quellcode, Commit-/Deployment-Metadaten, Secrets als geschützte Variablen |
| Rechtsgrundlage | berechtigtes Interesse/Vertrag |
| Empfänger | GitHub, STRATO |
| Löschung | Workflow-/Artefaktfristen festlegen |
| TOM | privates Repository, Least Privilege, SSH-Key, Secret-Scanning, Dependency Audit |

## C. Freigabe und Pflege

Das Verzeichnis ist mindestens bei folgenden Änderungen zu prüfen:

- neuer Dienstleister oder neue Datenregion;
- neue Akzeptanzstelle oder Zahlungsfunktion;
- neue Marketing- oder Analysefunktion;
- Änderung der Rechtsgrundlage;
- Sicherheitsvorfall;
- Änderung der Aufbewahrungsfristen;
- Einführung von Profiling oder automatisierter Entscheidung.

| Rolle | Name | Datum | Freigabe |
|---|---|---|---|
| Verantwortlicher |  |  |  |
| Datenschutzberatung/DSB |  |  |  |
| Technische Leitung |  |  |  |
