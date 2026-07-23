# A+ Card für Android / Google Play

## Feste Identität

- App-Name: `A+ Card`
- Publisher: `A+Solution GmbH`
- Package Name: `de.aplussolution.apluscard`
- Web-App: `https://cards.smarbiz.sbs/`
- Manifest: `https://cards.smarbiz.sbs/manifest.webmanifest`
- Digital Asset Links: `https://cards.smarbiz.sbs/.well-known/assetlinks.json`
- Support: `app@aplus-solution.de`
- Target SDK: Android 16 / API 36

Der Package Name darf nach der ersten Veröffentlichung nicht mehr geändert werden.

## Voraussetzungen

- bestätigtes Google-Play-Organisationskonto der A+Solution GmbH
- Node.js LTS
- Java/JDK und Android SDK
- Bubblewrap CLI
- sicher gespeicherter Upload Key
- Zugriff auf Play Console und Produktions-Domain

## Projekt mit Bubblewrap erzeugen

```bash
npm install --global @bubblewrap/cli
mkdir -p mobile/android/generated
cd mobile/android/generated
bubblewrap init --manifest=https://cards.smarbiz.sbs/manifest.webmanifest
```

Bei den Rückfragen diese Werte verwenden:

```text
Application name: A+ Card
Short name: A+ Card
Package ID: de.aplussolution.apluscard
Start URL: /
Display mode: standalone
Theme color: #09050f
Background color: #05030b
App version name: 1.0.0
App version code: 1
```

Danach in der erzeugten Bubblewrap-Konfiguration sicherstellen:

```json
{
  "packageId": "de.aplussolution.apluscard",
  "appVersionName": "1.0.0",
  "appVersionCode": 1,
  "targetSdkVersion": 36
}
```

## Upload Key

Der Upload Key darf nie in Git eingecheckt werden. Er wird lokal oder in einem geschützten Secret Store erzeugt und gesichert.

Beispiel:

```bash
keytool -genkeypair \
  -alias apluscard-upload \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000 \
  -keystore apluscard-upload.jks
```

Mindestens zwei verschlüsselte Backups von Keystore, Alias und Passwort an getrennten Orten aufbewahren.

## AAB bauen

```bash
cd mobile/android/generated
bubblewrap build
```

Für Google Play wird das signierte Android App Bundle (`.aab`) hochgeladen. APK-Dateien dienen nur der lokalen Installation und Prüfung.

## Play App Signing und Digital Asset Links

Nach dem ersten AAB-Upload:

1. Play Console → App integrity / App-Signatur öffnen.
2. SHA-256 des **App-Signaturschlüssels von Google Play** kopieren.
3. Den Wert in Production als `ANDROID_APP_SIGNING_SHA256` eintragen.
4. App neu deployen.
5. Prüfen, dass `/.well-known/assetlinks.json` Package Name und SHA-256 ausgibt.
6. Die Deep-Link-/Domain-Prüfung in Play Console erneut ausführen.

Nicht nur den lokalen Upload-Key-Fingerprint verwenden. Die an Nutzer ausgelieferte App wird von Google Play mit dem App-Signaturschlüssel signiert.

## Interner Test

Vor Production mindestens prüfen:

- Installation und Update
- Start ohne Browserleiste
- Login und Apple Login
- Registrierung und E-Mail-Bestätigung
- Standortauswahl
- QR-Code
- Guthaben, Zahlung, Beleg und Transaktionsfall
- In-App-Mitteilungen
- Datenschutz- und Löschseiten
- Zurück-Taste und externe Links
- Hintergrundbetrieb, Akku und Wärmeentwicklung

## Noch extern erforderlich

- vollständige Aktivierung des Play-Console-Kontos
- Upload-Key-Erzeugung
- erster AAB-Upload
- SHA-256 aus Play App Signing
- Store-Grafiken und Screenshots
- Data-Safety-Formular und App-Access-Zugang
