# A+ Card für iOS / App Store

## Feste Identität

- App-Name: `A+ Card`
- Publisher: `A+Solution GmbH`
- Bundle ID: `de.aplussolution.apluscard`
- Support: `app@aplus-solution.de`
- Web-App: `https://cards.smarbiz.sbs/`
- Associated Domains Host: `cards.smarbiz.sbs`
- AASA-Datei: `https://cards.smarbiz.sbs/.well-known/apple-app-site-association`

Der Bundle Identifier darf nach der ersten Veröffentlichung nicht mehr geändert werden.

## Native Hülle

Die iOS-App wird nicht als unveränderte WebView veröffentlicht. Die erste Version soll mindestens enthalten:

- native Navigation und sichere Web-Sitzung
- Universal Links
- QR-Scanner-Zugriff mit klarer Berechtigungsbeschreibung
- Apple Login
- Öffnen und Hinzufügen der A+ Card zu Apple Wallet
- native Offline- und Fehlerzustände
- sichere Behandlung externer Links
- App-Version und Support-Zugang
- Push-Unterstützung, sobald APNs vollständig konfiguriert ist

## Apple Developer

Im Team der A+Solution GmbH anlegen:

```text
App ID / Bundle ID: de.aplussolution.apluscard
App Name: A+ Card
Associated Domains: applinks:cards.smarbiz.sbs
Web Credentials: webcredentials:cards.smarbiz.sbs
Sign in with Apple: aktiv
Push Notifications: aktiv, sobald eingesetzt
```

Production setzt `IOS_APP_TEAM_ID` auf die echte Apple Team ID. Dadurch stellt die Website automatisch eine passende `apple-app-site-association` bereit.

## App Store Connect

Anzulegen:

```text
Name: A+ Card
Primary Language: German
Bundle ID: de.aplussolution.apluscard
SKU: APLUSCARD-IOS-001
User Access: Full Access für das Release-Team
```

## TestFlight-Abnahme

Vor App Review mindestens prüfen:

- Installation und Versionsupdate
- Registrierung und E-Mail-Bestätigung
- Apple Login bei erstem und erneutem Login
- Standortauswahl
- persönliche Mitgliedskarte und QR-Code
- Apple-Wallet-Download
- Guthaben, Zahlung, Beleg und Transaktionsfall
- Mitteilungen
- Datenschutzerklärung, AGB, Impressum und Kontolöschung
- Universal Links
- Kamera-Berechtigung
- Offline-/Serverfehler
- iPhone Safe Areas, Tastatur und Zurücknavigation

## Noch extern erforderlich

- aktives Apple Developer Program der A+Solution GmbH
- Einladung mit App-Manager-/Developer-Zugriff in App Store Connect
- Team ID
- App-ID- und Signing-Einrichtung
- macOS/Xcode-Buildumgebung
- TestFlight-Testgeräte
- finale App-Store-Screenshots und Datenschutzangaben
