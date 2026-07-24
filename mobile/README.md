# SAMS Card Native App

این پوشه Shell مشترک iOS و Android را با Capacitor نگه می‌دارد. محتوای اصلی از
`https://cards.smarbiz.sbs` بارگذاری می‌شود و قابلیت‌های Native، مخصوصاً Push
Notification، از طریق Capacitor در اختیار همان رابط قرار می‌گیرند.

## هویت ثابت

- App name: `SAMS Card`
- Android package: `de.aplussolution.apluscard`
- iOS Bundle ID: `de.aplussolution.apluscard`
- Backend: `https://cards.smarbiz.sbs`

بعد از اولین انتشار Package/Bundle ID را تغییر ندهید.

## ساخت پروژه‌های Native

```bash
cd mobile
npm install
npx cap add android
npx cap add ios
npx cap sync
```

پوشه iOS فقط روی macOS/Xcode قابل Build است.

## Android Push / Firebase

1. در Firebase Project متعلق به A+ Solution GmbH را باز کنید.
2. Android App با package `de.aplussolution.apluscard` اضافه کنید.
3. فایل `google-services.json` را فقط در `mobile/android/app/` قرار دهید.
4. در Firebase/Google Cloud یک Service Account محدود به ارسال FCM بسازید.
5. JSON آن را Base64 کنید و فقط در GitHub Secret زیر قرار دهید:

```text
FIREBASE_SERVICE_ACCOUNT_JSON_BASE64
```

فایل Service Account و `google-services.json` نباید در Git Commit شوند.

## iOS Push / APNs

1. در Apple Developer، App ID با Bundle ID بالا بسازید و Push Notifications را فعال کنید.
2. یک APNs Authentication Key (`.p8`) بسازید.
3. در Xcode برای Target اپ، قابلیت‌های `Push Notifications` و
   `Background Modes > Remote notifications` را فعال کنید.
4. این مقادیر را فقط در GitHub Secrets نگه دارید:

```text
APNS_KEY_ID
APNS_TEAM_ID
APNS_PRIVATE_KEY_BASE64
```

برای TestFlight و Production مقدار `APNS_USE_SANDBOX=0` استفاده می‌شود. Build مستقیم
Debug از Xcode معمولاً با Sandbox تست می‌شود.

## ثبت Token

کد وب هنگام اجرا داخل Shell Native، از پلاگین Push Notifications اجازه می‌گیرد و Token را
به endpoint زیر می‌فرستد:

```text
POST /api/v1/push-devices/
```

- Android: FCM registration token
- iOS: APNs device token

با Login حساب دیگری روی همان دستگاه، Token به کاربر جدید منتقل می‌شود.

## تست

پس از نصب Build روی دستگاه واقعی:

1. وارد حساب Member شوید.
2. بخش `Mitteilungen` را باز کنید.
3. `Push aktivieren` را بزنید.
4. با دستور زیر یک اعلان آزمایشی برای همان کاربر ایجاد و ارسال کنید:

```bash
docker compose exec web python manage.py send_test_push --username USERNAME
```

Simulator iOS برای آزمون نهایی Push کافی نیست؛ روی iPhone واقعی تست شود.
