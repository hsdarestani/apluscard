# SAMS Club Lounge – Prüfpaket für Steuerberatung und Kassenintegration

**Status:** Technischer Arbeitsentwurf  
**Stand:** 06.08.2026  
**Keine steuerliche Beratung.** Die endgültige Kontierung, Umsatzsteuerbehandlung und Kasseneinbindung muss durch den Steuerberater und gegebenenfalls Kassenanbieter schriftlich freigegeben werden.

## 1. Zu klärende Grunddaten

Bitte vollständig beantworten:

| Frage | Antwort/Freigabe |
|---|---|
| Welche juristische Person gibt das Kundenguthaben aus? |  |
| Auf welches Bank-/Kassenkonto fließen Aufladungen? |  |
| Welche juristische Person betreibt Standort 1? |  |
| Welche juristische Person betreibt Standort 2? |  |
| Welche juristische Person betreibt Standort 3? |  |
| Welche Leistungen können mit dem Guthaben erworben werden? |  |
| Gelten überall derselbe Steuersatz und dasselbe Leistungsland? |  |
| Kann Guthaben ausgezahlt, übertragen oder extern genutzt werden? | Nein vorgesehen / bestätigen |
| Verfällt Guthaben? Falls ja: wann und auf welcher Grundlage? |  |
| Wie werden Bonusguthaben behandelt? |  |
| Wie wird Trinkgeld vereinnahmt und weitergegeben? |  |
| Welche Registrierkasse/POS wird eingesetzt? |  |
| Welche TSE und welches DSFinV-K-Exportverfahren werden eingesetzt? |  |

## 2. Technischer Buchungsfluss

### Aufladung

1. Kunde zahlt bar oder über einen externen Zahlungsweg.
2. Inhaber erfasst die Aufladung mit Betrag, Standort und Referenz.
3. Das System schreibt einen Ledger-Eintrag `TOPUP`.
4. Saldo vorher und nachher werden unveränderlich gespeichert.
5. Der Vorgang erhält Zeitstempel, ausführenden Benutzer und Audit-Ereignis.

### Zahlung

1. Mitarbeiter oder Inhaber scannt einen kurzlebigen, signierten QR-Code.
2. Betrag, Standort, Beschreibung und Kassenreferenz werden erfasst.
3. Das System sperrt die Wallet-Zeile in einer Datenbanktransaktion.
4. Der Betrag wird nur bei ausreichendem Guthaben abgezogen.
5. Es entstehen eindeutiger Beleg, Ledger-Eintrag und Audit-Nachweis.

### Trinkgeld

- wird als eigener Ledger-Eintrag `TIP` geführt;
- darf nicht mit Waren-/Leistungsumsatz vermischt werden;
- Empfänger, arbeits-/lohnsteuerliche Behandlung und Kassenprozess müssen festgelegt werden.

### Erstattung/Korrektur

- Originalbuchungen werden nicht gelöscht oder überschrieben;
- Korrekturen erfolgen als nachvollziehbare Gegenbuchung;
- Prüffall, Referenz und Begründung bleiben erhalten.

## 3. Gutschein-Einordnung

Der Steuerberater muss anhand der endgültigen Leistungs- und Betreiberstruktur entscheiden, ob das Guthaben als Einzweck- oder Mehrzweck-Gutschein oder anders einzuordnen ist.

### Prüffragen Einzweck-Gutschein

- Steht der Ort der Leistung bei Ausgabe fest?
- Steht die geschuldete Umsatzsteuer bei Ausgabe fest?
- Sind alle einlösbaren Leistungen demselben Steuersatz unterworfen?
- Ist der Leistende beziehungsweise die Leistungsbeziehung ausreichend bestimmt?

### Prüffragen Mehrzweck-Gutschein

- Können Leistungen mit unterschiedlichen Steuersätzen erworben werden?
- Ist die steuerliche Behandlung bei Ausgabe noch nicht eindeutig?
- Entsteht die Umsatzsteuer erst bei Einlösung?

### Benötigte schriftliche Entscheidung

- Steuerzeitpunkt bei Aufladung
- Steuerzeitpunkt bei Einlösung
- Behandlung nicht eingelösten Guthabens
- Behandlung von Erstattungen
- Behandlung von Rabatt- und Bonusguthaben
- Behandlung standortübergreifender Einlösung
- erforderliche Rechnungs-/Belegangaben

Offizielle BMF-Unterlagen sind anhand des konkreten Modells in ihrer jeweils aktuellen Fassung zu prüfen.

## 4. Vorgeschlagene technische Kontentrennung

Die folgende Tabelle ist nur ein Mapping-Entwurf und keine Kontierungsempfehlung:

| App-Ereignis | Technischer Typ | Steuer-/Fibu-Ziel durch Berater festlegen |
|---|---|---|
| Kunde zahlt Guthaben ein | `TOPUP` | Verbindlichkeit/Gutschein/Umsatz? |
| Kunde bezahlt Leistung | `PURCHASE` | Umsatzerlös, USt-Schlüssel, Standort |
| Trinkgeld | `TIP` | durchlaufend, Arbeitnehmer/Team, Lohnsteuer? |
| Rückgabe | `REFUND` | Gegenbuchung zur Ursprungstransaktion |
| kostenloser Bonus | `BONUS` | Rabatt/Marketingaufwand/sonstige Behandlung |
| technische Korrektur | `ADJUSTMENT` | nur nach dokumentierter Freigabe |

## 5. POS- und Kassenabstimmung

Für den Produktivbetrieb sollte jeder App-Vorgang mit einer externen Kassenreferenz verknüpft werden.

Mindestens täglich abzustimmen:

- Summe Aufladungen je Standort und Zahlungsart;
- Summe Einlösungen je Standort;
- Summe Trinkgeld;
- Summe Erstattungen;
- offene oder fehlende Kassenreferenzen;
- App-Saldo aller Wallets gegen Fibu-/Gutscheinverbindlichkeit;
- Abweichungen und dokumentierte Korrekturfreigaben.

### Empfohlene Kontrollnummern

- eindeutige App-Belegnummer;
- POS-/Kassenbonnummer;
- Standort;
- Buchungszeitpunkt;
- Betrag;
- Steuersatz/Steuerschlüssel aus dem POS;
- Benutzer beziehungsweise Kassierer;
- Referenz zur Ursprungstransaktion bei Erstattung.

## 6. KassenSichV, TSE und DSFinV-K

Die App ersetzt nicht automatisch eine zertifizierte Registrierkasse oder TSE. Zu prüfen ist:

1. Welches System ist das führende Aufzeichnungssystem?
2. Wann wird der Geschäftsvorfall in der TSE-fähigen Kasse erfasst?
3. Ist die App nur Nebenbuch/CRM oder selbst Teil des Kassensystems?
4. Wie werden App-Aufladung und App-Einlösung im DSFinV-K-Export dargestellt?
5. Wie werden Storno, Trinkgeld und Gutscheinbewegungen abgebildet?
6. Werden Belegpflicht und Kassenbonnummer eingehalten?
7. Wie wird eine lückenlose Verfahrensdokumentation hergestellt?

## 7. GoBD-Verfahrensdokumentation

Technisch umgesetzt beziehungsweise vorbereitet:

- unveränderliche Ledger-Einträge;
- Gegenbuchung statt Löschung;
- eindeutige Belegnummern;
- Saldo vor/nach jeder Buchung;
- Rollen und ausführender Benutzer;
- Zeitstempel, Standort und Referenzen;
- verkettete Audit-Hashes zur Manipulationserkennung;
- verschlüsselte Backups mit Prüfsummen;
- regelmäßiger Restore-Test;
- dokumentierte Deployment- und Änderungsnachweise.

Noch organisatorisch zu ergänzen:

- freigegebene Prozessbeschreibung pro Standort;
- Kassieranweisungen;
- Berechtigungsmatrix mit Namen;
- Änderungs- und Freigabeverfahren;
- monatliche Abstimmung und Verantwortliche;
- Exportverfahren für Betriebsprüfung;
- finale Aufbewahrungsfristen.

## 8. Berater-Entscheidungsmatrix

| Thema | Entscheidung | Verantwortlicher | Datum |
|---|---|---|---|
| Einzweck-/Mehrzweck-Gutschein |  |  |  |
| Umsatzsteuer bei Aufladung |  |  |  |
| Umsatzsteuer bei Einlösung |  |  |  |
| Bonusguthaben |  |  |  |
| Trinkgeld |  |  |  |
| Breakage/nicht eingelöstes Guthaben |  |  |  |
| Standortübergreifende Verrechnung |  |  |  |
| POS/TSE-Führung |  |  |  |
| DSFinV-K-Mapping |  |  |  |
| Fibu-Konten und Steuerschlüssel |  |  |  |
| Aufbewahrungsfristen |  |  |  |

## 9. Offizielle Referenzen

- BMF – GoBD: https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Weitere_Steuerthemen/Abgabenordnung/GoBD/gobd.html
- BMF – Umsatzsteuer-Anwendungserlass und Schreiben zu Gutscheinen: https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuerarten/Umsatzsteuer/umsatzsteuer.html
- Bundesfinanzministerium – Kassensicherungsverordnung/elektronische Aufzeichnungssysteme: https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuerliche_Themengebiete/Kassensysteme/kassensysteme.html

## 10. Freigabe

| Rolle | Name | Datum | Unterschrift/Freigabe |
|---|---|---|---|
| Steuerberater |  |  |  |
| Betreiber/Wallet-Issuer |  |  |  |
| Kassenanbieter |  |  |  |
| Technische Leitung |  |  |  |
