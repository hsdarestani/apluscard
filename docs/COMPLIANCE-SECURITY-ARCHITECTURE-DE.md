# SAMS Club Lounge – System-, Sicherheits- und Compliance-Dokumentation

**Stand:** 06.08.2026  
**Betreiber-/Vertragsdaten:** vor Produktivfreigabe durch Rechtsanwalt, Datenschutzberatung und Steuerberatung zu vervollständigen  
**Hinweis:** Dieses Dokument beschreibt die technische Umsetzung und ersetzt keine Rechts- oder Steuerberatung.

## 1. Zweck und Systemgrenze

SAMS Club Lounge stellt eine digitale Mitgliedskarte, ein geschlossenes Prepaid-Guthaben, standortbezogene Angebote, Transaktionsbelege, Benachrichtigungen und rollenbasierte Kassenfunktionen bereit. Das Guthaben ist technisch auf die konfigurierten SAMS-Standorte begrenzt. Eine Auszahlung, Verzinsung, Übertragung zwischen Kunden oder Nutzung bei beliebigen externen Akzeptanzstellen ist nicht vorgesehen.

Die aufsichtsrechtliche Einordnung nach ZAG sowie die steuerliche Einordnung als Einzweck- oder Mehrzweck-Gutschein müssen anhand der endgültigen Betreiber-, Akzeptanzstellen- und Leistungsstruktur schriftlich geprüft werden.

## 2. Architektur

### 2.1 Komponenten

- Native iOS- und Android-Hülle auf Basis von Capacitor
- Django 5.2 Web- und API-Anwendung
- PostgreSQL als produktive relationale Datenbank
- Nginx als Reverse Proxy und TLS-Endpunkt
- Docker Compose für reproduzierbare Deployments
- STRATO-Server als vorgesehene produktive Infrastruktur
- Apple Sign in with Apple, APNs und Apple Wallet
- Firebase Cloud Messaging für Android-Push
- SMTP für transaktionale E-Mails
- Restic mit verschlüsseltem externem Backup-Ziel
- GitHub Actions für Tests, Build, Deployment und betriebliche Konfiguration

### 2.2 Vertrauensgrenzen

1. Kunden- oder Mitarbeitergerät zum HTTPS-Endpunkt
2. Reverse Proxy zur internen Django-Anwendung
3. Django zur PostgreSQL-Datenbank
4. Django zu Apple, Firebase und SMTP
5. Produktionsserver zum verschlüsselten externen Backup-Ziel
6. GitHub Actions zum Produktionsserver über SSH

Secrets werden nicht im Repository gespeichert. Private Schlüssel, Zertifikate, SMTP-Zugangsdaten, Datenbankzugänge und Backup-Schlüssel werden über geschützte Umgebungsvariablen beziehungsweise GitHub Secrets bereitgestellt.

## 3. Datenkategorien

### 3.1 Kontodaten

- Vorname und Nachname
- E-Mail-Adresse
- optional Mobilnummer
- optional Geburtsdatum
- Altersbestätigung
- Anmelde- und Verifizierungsstatus

### 3.2 Mitgliedschaft und Wallet

- interne Wallet-ID
- achtstellige Mitgliedsnummer
- Status und Treuestufe
- aktueller Saldo
- monatliche Aufladesumme
- Standortbezug

### 3.3 Finanz- und Nachweisdaten

- eindeutige Belegnummer
- Transaktionsart
- Betrag
- Saldo vor und nach der Buchung
- Standort
- ausführende Person
- Zeitstempel
- Bestell- oder Kassenreferenz
- Beschreibung
- Idempotenzschlüssel
- verbundene Zahlungsanfrage, Erstattung oder Prüffall

### 3.4 Sicherheits- und Nachweisdaten

- Rollen und Berechtigungen
- Audit-Ereignisse
- IP-Adresse bei relevanten Vorgängen
- Einwilligungs- und Rechtsdokumentversionen
- Push-Geräte und Zustellstatus
- Lösch- und Auskunftsvorgänge

## 4. Rollen- und Berechtigungskonzept

### Kunde

- Einsicht in das eigene Wallet
- Einsicht in eigene Transaktionen und Belege
- Anzeige eines kurzlebigen Zahlungs-QR-Codes
- Bestätigung ausdrücklich angeforderter Zahlungen
- Verwaltung freiwilliger Marketing-Einwilligungen
- Datenexport und Kontolöschungsantrag

### Mitarbeiter

- Zugriff ausschließlich auf den zugewiesenen Betrieb
- Zahlung nur nach erfolgreicher Prüfung eines aktuellen, signierten Zahlungs-QR-Codes
- Einsicht in eigene Buchungen und zulässige Prüffälle
- keine Aufladung, Erstattung oder Konfigurationsänderung

### Leitung

- betriebsbezogene Kunden- und Transaktionsübersicht
- Prüfung von Transaktionsfällen entsprechend der hinterlegten Rolle
- keine endgültige Löschung produktiver Finanzdaten

### Inhaber

- Aufladung, Zahlung und dokumentierte Gegenbuchung
- Konfiguration betrieblicher Einstellungen
- Freigabe von Erstattungen
- Verwaltung von Rollen und rechtlichen Stammdaten
- keine endgültige Löschung produktiver Finanzdaten

### Superuser

Django-Superuser sind ausschließlich für technischen Notfallzugriff vorgesehen. Administrative Finanzmodelle sind schreibgeschützt und besitzen keine Löschfunktion im Admin-Bereich.

## 5. Authentifizierung und Passwörter

- Passwörter werden nie im Klartext gespeichert.
- Neue Passwörter werden bevorzugt mit Argon2 gehasht.
- Vorhandene PBKDF2-Hashes bleiben lesbar und werden bei erfolgreicher Anmeldung automatisch auf den bevorzugten Hasher aktualisiert.
- Django-Passwortvalidierung verhindert triviale und häufig verwendete Passwörter.
- Sign in with Apple verwendet getrennte private Schlüssel und die offizielle Tokenprüfung.
- Apple-Refresh-Tokens werden verschlüsselt gespeichert und beim Abschluss einer Kontolöschung widerrufen.
- Kritische Authentifizierungs- und QR-Endpunkte besitzen eine anwendungsseitige Ratenbegrenzung. Zusätzlich sind Reverse-Proxy- beziehungsweise Cloudflare-Regeln zu betreiben.
- MFA für Inhaber und Leitung ist als kontrollierter Rollout vor umfangreichem Produktivbetrieb einzuplanen, damit kein bestehender Betreiberzugang unbeabsichtigt gesperrt wird.

## 6. Transport- und Anwendungssicherheit

- ausschließlicher produktiver Zugriff über HTTPS/TLS
- Secure-, HttpOnly- und SameSite-Cookies
- CSRF-Schutz für zustandsändernde Browseranfragen
- HSTS nach erfolgreicher Domain- und TLS-Abnahme
- Content Security Policy
- Schutz vor Clickjacking und MIME-Sniffing
- serverseitige Validierung aller Geldbeträge und Rollen
- Django ORM statt dynamisch zusammengesetzter SQL-Abfragen
- transaktionale Datenbankoperationen und Zeilensperren bei Saldoänderungen
- Idempotenzschlüssel gegen doppelte Buchungen
- eingeschränkte Dateiarten, Größenprüfung und Bildnormalisierung bei Uploads
- selbst gehostete und checksum-geprüfte QR-Scanner-Bibliothek

## 7. Wallet- und Ledger-Konzept

Der Wallet-Saldo wird nicht aus frei editierbaren Feldern abgeleitet, sondern bei jeder Buchung innerhalb einer Datenbanktransaktion aktualisiert. Jeder Ledger-Eintrag enthält den Saldo vor und nach der Buchung.

Vorgesehene Buchungsarten:

- Aufladung
- Zahlung
- Trinkgeld
- Erstattung beziehungsweise Gegenbuchung
- Bonus
- dokumentierte Korrektur

Produktive Ledger-Einträge und Audit-Ereignisse dürfen nicht endgültig gelöscht werden. Fehler werden durch einen Prüffall und eine nachvollziehbare Gegenbuchung korrigiert. Historische Originaldaten bleiben erhalten.

Eine technische Testdaten-Löschung ist nur möglich, wenn gleichzeitig:

1. die Umgebung `ALLOW_TEST_DATA_PURGE=1` gesetzt hat,
2. das konkrete Wallet ausdrücklich als Testkonto markiert wurde,
3. ein Inhaber die vorgeschriebene Bestätigung eingibt.

Die Produktivvorgabe ist `ALLOW_TEST_DATA_PURGE=0`. Abgewiesene Löschversuche werden protokolliert.

## 8. QR-Sicherheitskonzept

Der Zahlungs-QR-Code enthält nicht mehr nur eine dauerhafte Wallet-UUID. Die Anwendung erzeugt einen signierten, zeitgestempelten Token mit kurzer Gültigkeit. Der Kundenbildschirm erneuert den Code automatisch.

Der Zahlungsendpunkt akzeptiert ausschließlich:

- gültige Signatur,
- unterstützte Token-Version,
- nicht abgelaufenen Zeitstempel,
- übereinstimmende Wallet- und Karten-ID,
- aktives Wallet,
- passenden Betrieb.

Ein statischer Code oder Screenshot kann nach Ablauf nicht mehr für Zahlungen verwendet werden. Statische Mitgliedscodes, beispielsweise aus einem bestehenden Apple-Wallet-Pass, können nur zum Öffnen des Mitgliedsdatensatzes genutzt werden und autorisieren keine Zahlung.

## 9. Audit Trail

Audit-Ereignisse enthalten mindestens:

- Zeitpunkt
- handelnden Benutzer, soweit vorhanden
- Betrieb
- Aktion
- Objekttyp und Objekt-ID
- strukturierte Details
- IP-Adresse bei relevanten Vorgängen

Zu protokollieren sind insbesondere Registrierung, Rechtsdokumentbestätigung, Änderungen von Datenschutzpräferenzen, Aufladung, Zahlung, Trinkgeld, Erstattung, Saldoänderung, Statusänderung, Prüffälle, Datenexport, Löschungsablauf und abgewiesene Löschversuche.

Audit- und Finanzdaten sind im Django-Admin schreibgeschützt. Eine zusätzliche externe, manipulationsresistente Logsenke sollte vor größerem Produktionsvolumen ergänzt werden.

## 10. Datenschutzfunktionen

### 10.1 Datenminimierung

Mobilnummer und Geburtsdatum sind freiwillige Profilangaben. Die Altersbestätigung bleibt für den vorgesehenen Betriebszweck separat erforderlich. Marketing-Push und Marketing-E-Mail besitzen getrennte, freiwillige Einwilligungen.

### 10.2 Betroffenenrechte

- öffentlich erreichbare Datenschutzerklärung
- dokumentierte AGB- und Datenschutzhinweis-Versionen
- widerrufbare Marketing-Einwilligungen
- authentifizierter JSON-Datenexport
- Kontolöschungsantrag innerhalb der App und öffentlich
- Referenznummer und Bearbeitungsstatus
- Widerruf der Apple-Anmeldung beim Löschabschluss
- Löschung oder Anonymisierung direkter Identifikatoren
- getrennte Aufbewahrung gesetzlich erforderlicher Transaktionsnachweise

Jeder Datenexport wird als Audit-Ereignis erfasst und mit `no-store` ausgeliefert.

### 10.3 Noch vertraglich festzulegen

- Verantwortlicher gemäß Art. 4 Nr. 7 DSGVO
- Rolle von A+ Solution GmbH als Auftragsverarbeiter oder gemeinsam Verantwortlicher
- Auftragsverarbeitungsverträge
- Liste und Freigabe der Unterauftragsverarbeiter
- Lösch- und Aufbewahrungsfristen je Datenkategorie
- zuständige Aufsichtsbehörde
- Datenschutzbeauftragter, soweit erforderlich

## 11. Unterauftragsverarbeiter und externe Dienste

Mindestens zu prüfen und zu dokumentieren:

- STRATO
- Cloudflare, soweit eingesetzt
- Apple
- Google/Firebase
- SMTP-Anbieter
- externer Backup-Speicher
- GitHub

Für jeden Dienst sind Zweck, Datenkategorie, Region, Vertragsgrundlage, technische Maßnahmen und gegebenenfalls internationale Übermittlungsmechanismen festzuhalten.

## 12. Backup und Disaster Recovery

Vorgesehen ist:

- PostgreSQL-Backup im transportablen Format
- Sicherung der Media-Dateien
- verschlüsselte Sicherung produktiver Konfiguration
- Restic-Verschlüsselung vor Verlassen des Servers
- externes Backup-Ziel
- Backup alle sechs Stunden
- Aufbewahrung der letzten sieben Tage sowie gestaffelte tägliche, wöchentliche, monatliche und jährliche Snapshots
- regelmäßiger Restore-Drill in eine temporäre Datenbank
- Prüfung von Migrationen, Wallets und Ledger-Salden nach Restore
- Alarmierung bei veraltetem Backup oder fehlgeschlagenem Restore-Test

Vor Produktivfreigabe auf STRATO müssen Timer, Ziel, Verschlüsselung, erster Snapshot und ein echter Restore-Drill auf dem neuen Server nachweisbar erfolgreich sein. Das alte Serverziel darf danach nicht mehr als aktive Backup-Quelle geführt werden.

## 13. Incident Response

1. Ereignis erkennen und Zeitpunkt dokumentieren.
2. betroffene Systeme, Konten und Datenkategorien eingrenzen.
3. Zugangsdaten und Schlüssel bei Bedarf sperren oder rotieren.
4. Beweise und Logs schreibgeschützt sichern.
5. Ausbreitung stoppen und sicheren Dienst wiederherstellen.
6. Datenschutzverantwortliche und Geschäftsführung informieren.
7. Meldepflicht und 72-Stunden-Frist prüfen.
8. betroffene Personen bei hohem Risiko informieren.
9. Ursache beseitigen, Restore prüfen und Maßnahmen dokumentieren.
10. Abschlussbericht und Verbesserungsmaßnahmen freigeben.

Kontakt- und Eskalationsdaten sind vor Livebetrieb konkret einzutragen.

## 14. Steuer- und Kassenabstimmung

Technisch werden Kundenguthaben, Bonus, Umsatz, Trinkgeld, Erstattung und Korrektur getrennt erfasst. Die endgültige Kontierung ist vom Steuerberater festzulegen.

Zu entscheiden sind insbesondere:

- Einzweck- oder Mehrzweck-Gutschein
- Zeitpunkt der Umsatzsteuerentstehung
- Behandlung von nicht eingelöstem Guthaben
- Behandlung von Bonusguthaben
- getrennte Behandlung von Trinkgeld
- Abstimmung je Standort und Kasse
- Verhältnis zur eingesetzten Registrierkasse
- TSE-, KassenSichV-, DSFinV-K- und Belegpflichten
- Exportformat und Aufbewahrungsdauer für Betriebsprüfungen

Jede App-Buchung benötigt eine nachvollziehbare Zuordnung zur externen Kassen- oder Bestellreferenz, sobald die produktive POS-Abstimmung aktiv ist.

## 15. ZAG-/Limited-Network-Prüfung

Vor Ausweitung des Wallets sind schriftlich zu beantworten:

- Welche juristische Person gibt das Guthaben aus?
- Auf welches Konto fließt die Kundenzahlung?
- Welche juristischen Personen akzeptieren das Guthaben?
- Sind alle Standorte Teil desselben Unternehmens oder vertraglich gebundene Akzeptanzstellen?
- Bestehen Auszahlung, P2P-Transfer, Verzinsung oder externe Nutzung?
- Welche Saldo-, Auflade- und Umsatzgrenzen gelten?
- Wie wird die relevante Transaktionssumme über zwölf Monate überwacht?
- Ist eine Anzeige oder Abstimmung mit BaFin erforderlich?

Bis zur schriftlichen Beurteilung bleibt das System auf die definierte geschlossene SAMS-Struktur beschränkt.

## 16. Produktivfreigabe-Checkliste

- [ ] Repository auf Private gestellt
- [ ] Secret-Scanning und Credential-Rotation abgeschlossen
- [ ] STRATO-Domain und TLS vollständig aktiv
- [ ] HSTS nach erfolgreicher TLS-Abnahme aktiviert
- [ ] Backup auf STRATO erfolgreich ausgeführt
- [ ] Restore-Drill auf STRATO erfolgreich dokumentiert
- [ ] `ALLOW_TEST_DATA_PURGE=0` geprüft
- [ ] Betreiber und Wallet-Issuer schriftlich festgelegt
- [ ] AV-Verträge und Unterauftragsverarbeiter freigegeben
- [ ] Datenschutz- und Löschfristen freigegeben
- [ ] ZAG-/Limited-Network-Bewertung abgeschlossen
- [ ] Gutschein-, Umsatzsteuer- und Trinkgeldbehandlung freigegeben
- [ ] POS-/Kassenabstimmung dokumentiert
- [ ] MFA-Rollout für Inhaber und Leitung beschlossen
- [ ] Incident-Kontakte und Eskalationsweg eingetragen
- [ ] technische Abnahme mit aktuellen iOS- und Android-Versionen bestanden

## 17. Technische Nachweise im Repository

- automatisierte Django- und PostgreSQL-Tests
- Store-Release- und Privacy-Manifest-Tests
- QR- und Rollenprüfungen
- Backup- und Restore-Skripte
- Audit- und Ledger-Modelle
- Kontolöschungs- und Apple-Widerrufsprozess
- verschlüsselte Push-, Apple- und Backup-Secrets über GitHub Actions
- Compliance-Hardening-Tests für Argon2, rotierenden QR, Datenexport und Löschsperren
