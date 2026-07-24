# انتشار SAMS Card در Android / Google Play

## هویت ثابت

- App Name: `SAMS Card`
- Publisher: `A+ Solution GmbH`
- Package Name: `de.aplussolution.samscard`
- Backend: `https://cards.smarbiz.sbs`
- Support: `app@aplus-solution.de`
- Target SDK: Android 16 / API 36

Package Name بعد از اولین آپلود در Google Play قابل تغییر نیست.

## وضعیت فعلی

نسخه Native با Capacitor 8 ساخته شده و Push واقعی FCM روی دستگاه Android تست شده است. ساخت Release به‌صورت تکرارپذیر از Workflow زیر انجام می‌شود:

```text
Actions → Build Android Release
```

Workflow پروژه Android را از `mobile/capacitor.config.ts` تولید می‌کند، Firebase را اضافه می‌کند، AAB را با Upload Key امضا می‌کند و فایل نهایی را به‌عنوان Workflow Artifact تحویل می‌دهد.

## GitHub Secrets لازم

```text
GOOGLE_SERVICES_JSON_BASE64
ANDROID_KEYSTORE_BASE64
ANDROID_KEYSTORE_PASSWORD
ANDROID_KEY_ALIAS
ANDROID_KEY_PASSWORD
```

`GOOGLE_SERVICES_JSON_BASE64` مربوط به فایل Android App یعنی `google-services.json` است و با Service Account JSON سرور فرق دارد.

## ساخت Upload Key روی Windows

در PowerShell:

```powershell
$Keytool = "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
& $Keytool -genkeypair -v `
  -keystore "$env:USERPROFILE\Downloads\sams-card-upload.jks" `
  -alias "sams-card-upload" `
  -keyalg RSA `
  -keysize 4096 `
  -validity 10000
```

Alias پیشنهادی:

```text
sams-card-upload
```

Keystore و هر دو Password باید حداقل در دو محل رمزگذاری‌شده و جدا نگهداری شوند. فایل Keystore هرگز داخل Git قرار نمی‌گیرد.

## تبدیل فایل‌ها به Base64

Keystore:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\sams-card-upload.jks")
) | Set-Clipboard
```

Firebase Android config:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\google-services.json")
) | Set-Clipboard
```

مقادیر Base64 فقط داخل GitHub Secrets ثبت می‌شوند و نباید در چت، Issue یا Commit قرار بگیرند.

## ساخت AAB

در GitHub:

```text
Actions
→ Build Android Release
→ Run workflow
```

ورودی اولین Build:

```text
version_name: 1.0.0
version_code: 1
```

برای هر Upload جدید، `version_code` باید افزایش پیدا کند. خروجی Workflow:

```text
SAMS-Card-Android-1.0.0-1
└── app-release.aab
```

## Google Play Internal Testing

```text
Play Console
→ SAMS Card
→ Testing and release
→ Internal testing
→ Create new release
→ Upload app-release.aab
```

برای انتشار Android App Bundle باید Play App Signing فعال باشد. AAB با Upload Key شرکت امضا می‌شود و Google Play نسخه تحویلی به کاربران را با App Signing Key امضا می‌کند.

بعد از اولین Upload:

1. وارد `App integrity / App signing` شوید.
2. SHA-256 مربوط به **App signing key certificate** را بردارید.
3. آن را در Production به‌عنوان `ANDROID_APP_SIGNING_SHA256` ثبت کنید.
4. سایت را Deploy کنید تا `assetlinks.json` با کلید Google Play هماهنگ شود.

## چک‌لیست تست داخلی

- نصب و Update از Google Play
- Login و Registration
- دریافت Push در پس‌زمینه و Lock Screen
- QR و Membership Card
- Wallet، پرداخت، شارژ و رسید
- Mitteilungen
- Back Button و External Links
- Privacy، Terms و Account Deletion
