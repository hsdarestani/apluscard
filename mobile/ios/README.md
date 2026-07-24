# انتشار SAMS Card در iOS / TestFlight

## هویت ثابت

- App Name: `SAMS Card`
- Publisher: `A+ Solution GmbH`
- Bundle ID: `de.aplussolution.samscard`
- Team ID: `VHB87QGU46`
- Backend: `https://cards.smarbiz.sbs`
- Associated Domains: `cards.smarbiz.sbs`
- Support: `app@aplus-solution.de`

Bundle ID بعد از اولین Upload قابل تغییر نیست.

## وضعیت فعلی

Backend مربوط به APNs در Production فعال شده و کلید زیر برای ارسال Push سرور ثبت شده است:

```text
APNS_KEY_ID
APNS_TEAM_ID
APNS_PRIVATE_KEY_BASE64
```

این کلید فقط برای ارسال Push است و با کلید App Store Connect فرق دارد.

به‌دلیل نبود Mac محلی، Build امضاشده iOS روی GitHub-hosted macOS Runner انجام می‌شود:

```text
Actions → Build iOS TestFlight
```

Workflow پروژه Capacitor iOS را تولید می‌کند، Push Notifications و Remote Notifications را فعال می‌کند، IPA را با Apple Distribution Certificate امضا می‌کند و در صورت انتخاب، مستقیم به TestFlight می‌فرستد.

## پیش‌نیاز Apple Developer

App ID زیر باید Explicit و فعال باشد:

```text
de.aplussolution.samscard
```

Capabilities لازم:

```text
Push Notifications
Associated Domains
Sign in with Apple
```

برای App Store Connect یک App Record بسازید:

```text
Name: SAMS Card
Primary Language: German
Bundle ID: de.aplussolution.samscard
SKU: SAMS-CARD-IOS-001
User Access: Full Access
```

## GitHub Secrets لازم برای Signing

```text
IOS_DISTRIBUTION_CERT_P12_BASE64
IOS_DISTRIBUTION_CERT_PASSWORD
IOS_PROVISIONING_PROFILE_BASE64
```

Provisioning Profile باید از نوع **App Store Connect**، متعلق به Bundle ID بالا و بعد از فعال‌شدن Push Notifications ساخته شده باشد. Workflow وجود `aps-environment=production` را بررسی می‌کند.

## GitHub Secrets لازم برای Upload به TestFlight

```text
ASC_KEY_ID
ASC_ISSUER_ID
ASC_PRIVATE_KEY_BASE64
```

این مقادیر از این بخش ساخته می‌شوند:

```text
App Store Connect
→ Users and Access
→ Integrations
→ App Store Connect API
→ Team Keys
```

از **Team API Key** استفاده شود، نه Individual API Key و نه APNs Key. نقش پیشنهادی برای Release، `App Manager` است. فایل `.p8` فقط یک بار قابل دانلود است.

## ساخت Apple Distribution Certificate بدون Mac

Git for Windows شامل OpenSSL است. در PowerShell:

```powershell
$OpenSSL = "C:\Program Files\Git\usr\bin\openssl.exe"
$Work = "$env:USERPROFILE\Downloads\sams-ios-signing"
New-Item -ItemType Directory -Force $Work | Out-Null

& $OpenSSL genrsa -out "$Work\sams-ios-distribution.key" 2048
& $OpenSSL req -new `
  -key "$Work\sams-ios-distribution.key" `
  -out "$Work\sams-ios-distribution.csr" `
  -subj "/emailAddress=app@aplus-solution.de/CN=A+ Solution GmbH/C=DE"
```

فایل CSR را در Apple Developer آپلود کنید:

```text
Certificates
→ +
→ Apple Distribution
→ Upload CSR
→ Download Certificate
```

Certificate دانلودشده را کنار Private Key قرار دهید و P12 بسازید:

```powershell
& $OpenSSL x509 -inform DER `
  -in "$env:USERPROFILE\Downloads\distribution.cer" `
  -out "$Work\distribution.pem"

& $OpenSSL pkcs12 -export `
  -inkey "$Work\sams-ios-distribution.key" `
  -in "$Work\distribution.pem" `
  -out "$Work\sams-ios-distribution.p12" `
  -name "Apple Distribution: A+ Solution GmbH"
```

Password انتخاب‌شده برای P12 همان مقدار Secret زیر است:

```text
IOS_DISTRIBUTION_CERT_PASSWORD
```

## تبدیل فایل‌های Signing به Base64

P12:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\sams-ios-signing\sams-ios-distribution.p12")
) | Set-Clipboard
```

Provisioning Profile:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\SAMS_Card_AppStore.mobileprovision")
) | Set-Clipboard
```

App Store Connect Team API Key:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\AuthKey_XXXXXXXXXX.p8")
) | Set-Clipboard
```

هیچ فایل کلید یا مقدار Base64 نباید داخل Git یا چت قرار بگیرد.

## اجرای Build و TestFlight

```text
Actions
→ Build iOS TestFlight
→ Run workflow
```

اولین اجرا:

```text
version_name: 1.0.0
build_number: 1
upload_to_testflight: true
```

برای هر Upload جدید، `build_number` باید افزایش پیدا کند. Workflow ابتدا IPA و SHA-256 را به‌عنوان Artifact ذخیره می‌کند و سپس با Team API Key آن را Validate و Upload می‌کند.

پس از پردازش Apple:

```text
App Store Connect
→ SAMS Card
→ TestFlight
```

## چک‌لیست TestFlight

- نصب روی iPhone واقعی
- Login و Registration
- اجازه Push و دریافت اعلان روی Lock Screen
- Apple Login
- Apple Wallet
- Associated/Universal Links
- QR و Membership Card
- پرداخت، شارژ، رسید و Transaction Case
- Safe Area، Keyboard و Back Navigation
- Privacy، Terms و Account Deletion
