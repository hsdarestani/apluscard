# راه‌اندازی Backup رایگان روی Google Drive

این روش برای زمانی است که کارت بانکی یا روش پرداخت بین‌المللی در دسترس نیست.

- هر Google Account تا ۱۵ گیگابایت فضای رایگان دارد.
- هیچ اطلاعات پرداختی برای استفاده از فضای رایگان لازم نیست.
- Restic قبل از آپلود، دیتابیس، Media و تنظیمات Production را رمزنگاری می‌کند.
- Google Drive فقط فایل‌های رمز‌شده و غیرقابل‌خواندن را دریافت می‌کند.

## پیشنهاد حساب

بهتر است یک Gmail جدا فقط برای Backup ساخته شود؛ مثلاً:

```text
apluscard.backup@gmail.com
```

از این حساب برای Gmail، Google Photos یا فایل‌های شخصی استفاده نشود تا تمام ظرفیت آن برای Backup باقی بماند.

## مرحله ۱: دانلود rclone روی Windows

از سایت رسمی rclone نسخه Windows 64-bit را دانلود و ZIP را Extract کن.

مثلاً فایل‌ها را در این مسیر قرار بده:

```text
C:\rclone
```

PowerShell را باز کن:

```powershell
cd C:\rclone
.\rclone.exe version
```

## مرحله ۲: اتصال rclone به Google Drive

در PowerShell اجرا کن:

```powershell
.\rclone.exe config
```

پاسخ‌ها:

```text
n                   # New remote
name> gdrive
Storage> drive      # یا شماره Google Drive در لیست
client_id>          # خالی، Enter
client_secret>      # خالی، Enter
scope> 1            # دسترسی کامل به فایل‌های ساخته‌شده برای Backup
service_account_file>  # خالی، Enter
Edit advanced config? n
Use web browser to automatically authenticate? y
```

مرورگر باز می‌شود. با حساب Google مخصوص Backup وارد شو و دسترسی را تأیید کن.

در ادامه:

```text
Configure this as a Shared Drive? n
Keep this "gdrive" remote? y
q
```

## مرحله ۳: تست اتصال

```powershell
.\rclone.exe lsd gdrive:
```

اگر بدون خطای Authentication اجرا شد، اتصال سالم است. خالی‌بودن خروجی مشکلی ندارد.

## مرحله ۴: پیداکردن فایل تنظیمات

```powershell
.\rclone.exe config file
```

معمولاً مسیر شبیه این است:

```text
C:\Users\USERNAME\AppData\Roaming\rclone\rclone.conf
```

این فایل شامل OAuth Token است و نباید داخل Repository، Issue یا پیام عمومی فرستاده شود.

## مرحله ۵: تبدیل rclone.conf به Base64

مسیر واقعی فایل را در دستور زیر قرار بده:

```powershell
$configPath = "$env:APPDATA\rclone\rclone.conf"
[Convert]::ToBase64String([IO.File]::ReadAllBytes($configPath)) |
  Set-Content -NoNewline "C:\rclone\rclone.conf.base64.txt"
```

فایل زیر ساخته می‌شود:

```text
C:\rclone\rclone.conf.base64.txt
```

## مرحله ۶: ساخت رمز Recovery برای Restic

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

خروجی را در دو جای امن نگه دار:

1. GitHub Secret
2. Password Manager یا فایل رمزنگاری‌شده خارج از سرور

بدون این رمز، Backupها قابل بازیابی نیستند.

## مرحله ۷: تعریف GitHub Secrets

مسیر:

```text
Repository
→ Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

فقط این سه Secret لازم‌اند:

### BACKUP_RESTIC_REPOSITORY

```text
rclone:gdrive:apluscard-production-backups
```

### BACKUP_RESTIC_PASSWORD

رمز تصادفی مرحله قبل.

### BACKUP_RCLONE_CONFIG_BASE64

کل محتوای یک‌خطی فایل:

```text
C:\rclone\rclone.conf.base64.txt
```

Secretهای AWS برای Google Drive لازم نیستند.

## مرحله ۸: اجرای راه‌اندازی

```text
GitHub
→ Actions
→ Configure Production Backups
→ Run workflow
```

Workflow به‌صورت خودکار:

1. rclone و Restic را روی سرور نصب می‌کند.
2. OAuth Config را فقط با دسترسی root ذخیره می‌کند.
3. اولین Backup رمزنگاری‌شده را در Google Drive قرار می‌دهد.
4. همان Backup را دانلود می‌کند.
5. دیتابیس را داخل PostgreSQL موقت Restore می‌کند.
6. Migrationها و Walletها را بررسی می‌کند.
7. Timer هر شش ساعت را فعال می‌کند.

## فایل‌های قابل مشاهده در Google Drive

پوشه‌ای به نام زیر ساخته می‌شود:

```text
apluscard-production-backups
```

محتوای آن فایل‌های داخلی Restic است و فایل‌هایی مثل `database.dump` به‌صورت مستقیم و خوانا دیده نمی‌شوند. این طبیعی و بخش اصلی امنیت Backup است.

## ظرفیت

فضای رایگان Google Account بین Drive، Gmail و Photos مشترک است. برای همین حساب Backup بهتر است کاملاً خالی و اختصاصی باشد.

مانیتور Backup در صورت پرشدن فضا یا شکست آپلود خطا ثبت می‌کند. با افزایش حجم داده، مقصد پولی یا یک دیسک/Provider دوم باید اضافه شود.
