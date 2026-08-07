# Lösch- und Aufbewahrungsmatrix – SAMS Club Lounge

**Status:** Entwurf zur Freigabe durch Rechts- und Steuerberatung  
**Stand:** 06.08.2026  
Die Tabelle definiert technische Zielprozesse, aber keine verbindliche rechtliche Frist. Finanz- und Steuerdaten dürfen erst nach schriftlicher Freigabe automatisch gelöscht oder anonymisiert werden.

## Grundsätze

1. Daten werden nur so lange personenbezogen gespeichert, wie Zweck oder Pflicht bestehen.
2. Produktive Ledger- und Auditdaten werden nicht in der Bedienoberfläche hart gelöscht.
3. Fehler werden durch Gegenbuchung, Berichtigung oder ergänzendes Audit-Ereignis korrigiert.
4. Nach Ende der Personenbeziehbarkeit können gesetzlich erforderliche Nachweise pseudonymisiert/anonymisiert aufbewahrt werden.
5. Backups folgen eigener Rotation; Löschung im Livesystem wirkt zeitverzögert in Backups.
6. Legal Hold, Prüfung oder Incident kann eine reguläre Löschung dokumentiert aussetzen.

## Fristenmatrix

| Datenkategorie | Zweck | Ereignis für Fristbeginn | Vorgeschlagener technischer Prozess | Finale Frist/Freigabe |
|---|---|---|---|---|
| unbestätigte Registrierung | Kontoanlage | Registrierung ohne Bestätigung | automatisiert löschen/anonymisieren | `[OFFEN, z. B. kurze Frist]` |
| aktives Kundenkonto | Vertrag | Vertrags-/Kontolaufzeit | aktiv halten | Vertragsdauer |
| direkt identifizierende Profildaten | Mitgliedschaft | genehmigte Kontolöschung/Vertragsende | Name, E-Mail, Telefon, Geburtsdatum löschen oder anonymisieren | `[OFFEN]` |
| Apple Login Refresh Token | Login/Widerruf | Löschabschluss/Trennung | widerrufen und löschen | unverzüglich nach Prozess |
| Push-Token | Benachrichtigung | Abmeldung, Unzustellbarkeit, Löschung | deaktivieren und anschließend löschen | `[OFFEN]` |
| Marketing-Einwilligung | Nachweis/Widerruf | Widerruf oder Ende Marketing | Marketing stoppen, Nachweis minimal weiterführen | `[OFFEN]` |
| In-App-Mitteilungen | Kommunikation | Erstellung/Lesen | nach Frist löschen, Pflichtnachweise ggf. erhalten | `[OFFEN]` |
| Wallet-Stammdaten | Vertrag/Abrechnung | Schließung | Identifikatoren anonymisieren, Finanzreferenz erhalten | `[OFFEN]` |
| Ledger/Transaktionen/Belege | Steuer, Vertrag, Nachweis | Ende Geschäftsjahr/Vorgang | unveränderlich archivieren, danach freigegebene Löschung | `[Steuerberater festlegen]` |
| Trinkgeld- und Erstattungsdaten | Abrechnung/Steuer | Geschäftsjahr | wie Finanzdaten | `[Steuerberater festlegen]` |
| Prüffälle/Reklamationen | Rechtsverteidigung/Support | Fallabschluss | nach Verjährungs-/Pflichtfrist löschen/anonymisieren | `[Rechtsanwalt festlegen]` |
| Audit-Ereignisse | Sicherheit/Nachweis | Ereignis/Fallabschluss | verkettet, schreibgeschützt, danach kontrollierte Archivlöschung | `[DSB/Rechtsanwalt festlegen]` |
| IP-Adressen in Audit | Sicherheit | Ereignis | nach kürzerer Frist anonymisieren, falls Nachweis nicht mehr nötig | `[OFFEN]` |
| Datenexport-Datei | Betroffenenrecht | Erstellung/Download | nicht serverseitig dauerhaft speichern; no-store | sofort/keine Persistenz |
| Löschantrag und Bearbeitungsnachweis | DSGVO-Nachweis | Abschluss | minimalen Nachweis ohne unnötige Identifikatoren erhalten | `[OFFEN]` |
| Support-E-Mail | Support/Nachweis | Ticketabschluss | Postfach-/Ticketsystemfrist | `[OFFEN]` |
| CI/CD-Logs | Betrieb/Sicherheit | Workflow-Ende | automatische GitHub-Retention | `[OFFEN]` |
| Deployment-Artefakte | Release/Rollback | Release | begrenzte Artefakt-Retention | `[OFFEN]` |
| Sicherheitsincident-Daten | Incident/Nachweis | Incident-Abschluss | Legal Hold, danach freigegebene Frist | `[OFFEN]` |
| Backup-Snapshots | Verfügbarkeit | Snapshot | Restic-Rotation | technisch 7d/30 daily/12 weekly/12 monthly/3 yearly; rechtlich freigeben |
| Testkonten/Testtransaktionen | Qualitätssicherung | Testende | nur markierte Testkonten in Testmodus löschen | nach Testabschluss |
| MFA-TOTP-Secret | Zugangsschutz | 2FA-Reset/Kontolöschung | verschlüsseltes Secret löschen | unverzüglich nach Reset/Löschung |
| MFA-Recovery-Code-Hashes | Zugangsschutz | Nutzung/Neuerzeugung | verwendeten Hash entfernen; alte Liste ersetzen | sofort bei Nutzung/Rotation |

## Löschprozess

1. Antrag oder Fristablauf wird erfasst.
2. Identität und Berechtigung werden geprüft.
3. Legal Hold, offene Forderung, Prüffall und Aufbewahrungspflicht werden geprüft.
4. Direkte Identifikatoren werden gelöscht oder durch nicht rückführbare Kennung ersetzt.
5. externe Systeme und Push-/Login-Token werden widerrufen.
6. Vorgang wird im Audit protokolliert.
7. Backup-Ablauf und verbleibende Wiederherstellbarkeit werden dokumentiert.
8. Betroffener erhält Abschlussinformation, soweit vorgesehen.

## Legal Hold

Ein Legal Hold muss enthalten:

- Anlass und Rechtsgrund;
- betroffene Datenkategorien;
- verantwortliche Person;
- Beginn und Prüftermin;
- Ende und Freigabe;
- Audit-Referenz.

Ein Legal Hold darf keine pauschale unbegrenzte Vorratsspeicherung ersetzen.

## Freigabematrix

| Datenkategorie | Rechtsanwalt/DSB | Steuerberater | Betreiber | Freigegebene Frist |
|---|---|---|---|---|
| Profile/Konten |  | n/a |  |  |
| Finanzdaten/Belege |  |  |  |  |
| Audit/IP |  | n/a |  |  |
| Marketing/Push |  | n/a |  |  |
| Support/Prüffälle |  | ggf. |  |  |
| Backups |  |  |  |  |
| CI/CD-Logs |  | n/a |  |  |
