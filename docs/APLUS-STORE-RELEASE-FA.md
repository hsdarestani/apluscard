# وضعیت آماده‌سازی انتشار A+ Card

## هویت نهایی انتخاب‌شده

| مورد | مقدار |
|---|---|
| نام عمومی اپ | A+ Card |
| ناشر | A+Solution GmbH |
| ایمیل پشتیبانی و ارسال | app@aplus-solution.de |
| Android Package Name | de.aplussolution.apluscard |
| iOS Bundle ID | de.aplussolution.apluscard |
| زبان اولیه Store | آلمانی |
| قیمت | رایگان |
| دامنه فعلی | cards.smarbiz.sbs |
| دامنه هدف پیشنهادی | app.aplus-solution.de |

نام شعب، خدمات و اطلاعات حقوقی هر شریک می‌تواند داخل A+ Card نمایش داده شود، اما هویت خود اپ، ناشر، آیکن، ایمیل، صفحه Store و فایل Wallet تحت برند A+ است.

## کارهای فنی انجام‌شده در این شاخه

- هویت مرکزی A+ Card در Django
- ناشر A+Solution GmbH
- فرستنده و Reply-To ایمیل `app@aplus-solution.de`
- آماده‌سازی SMTP امن STRATO با `smtp.strato.de:465` و SSL
- قالب ایمیل تأیید با برند A+
- برند A+ در هدر، فوتر و Django Admin
- برند A+ در Apple Wallet Pass
- آیکن A+ در SVG و PNGهای 192 و 512
- Web App Manifest مناسب Store
- مسیر Android Digital Asset Links
- مسیر Apple App Site Association
- متن آلمانی Google Play و App Store
- راهنمای Android/TWA و iOS/TestFlight
- تست خودکار برای Manifest، آیکن‌ها، Asset Links، AASA و ایمیل

## ورودی‌هایی که مالک حساب باید تکمیل کند

### ۱. ایمیل STRATO

صندوق `app@aplus-solution.de` باید Mailbox واقعی و دارای رمز SMTP باشد، نه صرفاً Forwarding Alias.

رمز در چت، Issue یا فایل Repository فرستاده نشود. فقط در GitHub Actions Secret زیر ثبت شود:

```text
EMAIL_SMTP_PASSWORD
```

مقادیر پیش‌فرض آماده‌اند:

```text
EMAIL_SMTP_HOST=smtp.strato.de
EMAIL_SMTP_PORT=465
EMAIL_SMTP_USE_SSL=1
```

بعد از Merge، Workflow دستی `Configure Production Email` اجرا می‌شود و یک ایمیل واقعی به `app@aplus-solution.de` می‌فرستد.

### ۲. دامنه A+

برای اینکه Store و لینک‌های اپ کاملاً A+ باشند، در STRATO DNS این رکورد پیشنهاد می‌شود:

```text
Type: A
Host/Name: app
Value: 91.107.145.196
TTL: Standard / 3600
```

بعد از انتشار DNS باید:

- SSL برای `app.aplus-solution.de` صادر شود.
- Reverse proxy دامنه را به سرویس روی `127.0.0.1:8010` متصل کند.
- Django Allowed Hosts و CSRF Origins شامل دامنه جدید شوند.
- Apple Service ID Return URL شامل دامنه جدید شود.
- Store URLها از دامنه قدیمی به دامنه A+ منتقل شوند.
- دامنه قبلی برای سازگاری Redirect یا Alias باقی بماند.

### ۳. Google Play

- تکمیل تأیید حساب Organization متعلق به A+Solution GmbH
- دعوت توسعه‌دهنده/Release Manager
- ساخت App با Package Name ثابت `de.aplussolution.apluscard`
- آپلود اولین AAB
- ارسال SHA-256 بخش Play App Signing برای ثبت در `ANDROID_APP_SIGNING_SHA256`
- تکمیل Data Safety، App Access و Content Rating

### ۴. Apple App Store

- عضویت فعال Apple Developer متعلق به A+Solution GmbH
- دسترسی App Store Connect
- Apple Team ID
- ساخت App ID با Bundle ID ثابت `de.aplussolution.apluscard`
- Signing، TestFlight و App Privacy

### ۵. محتوای Store

- لوگوی رسمی A+ در صورت وجود فایل برند نهایی
- تصاویر واقعی شعب
- اسکرین‌شات‌های نهایی Android و iPhone
- شماره پشتیبانی عمومی در صورت نیاز
- بازبینی حقوقی AGB، Datenschutz و Impressum

## موارد امنیتی

- Repository باید Private شود؛ کد در Repository عمومی قابل مشاهده است.
- رمز Mailbox، Upload Key، Keystore و Apple Certificate هرگز در Git ثبت نشوند.
- Upload Key اندروید حداقل دو Backup رمزنگاری‌شده داشته باشد.
- SHA-256 مورد استفاده در `assetlinks.json` باید App Signing Key گوگل باشد، نه فقط Upload Key محلی.

## ترتیب ادامه کار

1. Merge و Deploy تغییرات A+
2. ثبت Secret رمز STRATO و اجرای تست SMTP
3. ساخت DNS دامنه `app.aplus-solution.de`
4. فعال‌سازی SSL و انتقال Public Base URL
5. تکمیل Google Play Organization Account
6. تولید و Upload فایل AAB
7. ثبت Play App Signing SHA-256 روی سرور
8. ساخت iOS App و Upload به TestFlight
9. تهیه Store Graphics و Screenshots
10. تکمیل فرم‌های Privacy و ارسال برای Review
