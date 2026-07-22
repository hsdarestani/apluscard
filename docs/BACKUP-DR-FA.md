# فرایند استاندارد Backup و Disaster Recovery اپ A+

## هدف

این فرایند برای خرابی کامل سرور، حذف Docker Volume، Corruption دیتابیس، اشتباه انسانی یا انتقال اضطراری به سرور جدید طراحی شده است.

کد پروژه در GitHub است. موارد زیر جداگانه Backup می‌شوند:

1. دیتابیس PostgreSQL
2. فایل‌های `media` شامل تصاویر شعبه‌ها و آپلودهای آینده
3. فایل `.env` واقعی Production برای بازیابی تنظیمات و Secretهای سرویس

تمام داده‌ها **قبل از خروج از سرور** با Restic رمزنگاری می‌شوند.

## سطح سرویس

- **RPO فعلی:** حداکثر ۲۴ ساعت
- **RTO هدف:** کمتر از ۶۰ دقیقه روی یک سرور آماده
- Backup روزانه: حدود ساعت 03:20 سرور با تأخیر تصادفی حداکثر ۱۵ دقیقه
- Restore Drill: هر یکشنبه حدود ساعت 05:10

در صورت افزایش تراکنش‌ها می‌توان Backup را به هر ۶ ساعت تغییر داد.

## معماری فعلی و 3-2-1

مرحله‌ای که این PR راه‌اندازی می‌کند شامل دو محل مستقل است:

- نسخه اصلی روی PostgreSQL و Media Volume سرور Production
- Snapshotهای تاریخی رمزنگاری‌شده روی Object Storage خارج از سرور

این ساختار خرابی کامل سرور را پوشش می‌دهد، اما برای تعریف **سخت‌گیرانه 3-2-1** یک کپی مستقل سوم هم لازم است. بعد از فعال‌شدن مقصد اول، یکی از این دو گزینه اضافه می‌شود:

- مقصد Restic دوم روی Provider دیگری؛ یا
- Backup/Snapshot مستقل Hetzner در کنار Object Storage متعلق به Provider دیگر

Object Storage اول بهتر است متعلق به Provider دیگری غیر از سرور اصلی باشد؛ مثلاً Cloudflare R2 یا Backblaze B2 در کنار سرور Hetzner.

## Retention

- ۱۴ نسخه روزانه
- ۸ نسخه هفتگی
- ۱۲ نسخه ماهانه
- ۳ نسخه سالانه

Prune فقط هفته‌ای یک‌بار اجرا می‌شود تا فشار I/O روزانه ایجاد نشود.

## Secretهای GitHub

در مسیر زیر:

```text
Repository → Settings → Secrets and variables → Actions
```

این Secretها ایجاد می‌شوند:

```text
BACKUP_RESTIC_REPOSITORY
BACKUP_RESTIC_PASSWORD
BACKUP_AWS_ACCESS_KEY_ID
BACKUP_AWS_SECRET_ACCESS_KEY
BACKUP_AWS_DEFAULT_REGION
```

نمونه مقصد:

```text
s3:https://S3-ENDPOINT/apluscard-production-backups
```

`BACKUP_RESTIC_PASSWORD` باید حداقل ۲۴ کاراکتر تصادفی داشته باشد. این رمز Recovery Key اصلی Repository است و باید علاوه بر GitHub Secrets در Password Manager مالک کسب‌وکار نیز نگهداری شود.

هیچ مقدار Secret نباید در Repository، Issue، پیام عمومی یا `.env.example` قرار بگیرد.

## راه‌اندازی اولیه

بعد از ساخت Bucket خصوصی و Secretها:

```text
GitHub → Actions → Configure Production Backups → Run workflow
```

Workflow به‌صورت خودکار:

1. Secretها را بدون چاپ مقدار بررسی می‌کند.
2. Restic و ابزارها را روی سرور نصب می‌کند.
3. فایل root-only به نام `/root/apluscard/.backup.env` می‌سازد.
4. Systemd Timerهای Backup و Restore Drill را فعال می‌کند.
5. اولین Backup واقعی را می‌گیرد.
6. همان Backup را در دیتابیس موقت Restore می‌کند.
7. Migrationها و Walletها را Query می‌کند.
8. نتیجه را در Issue شماره 25 ثبت می‌کند.

## محتوای Snapshot

```text
database.dump
media.tar.gz
production.env
metadata.json
SHA256SUMS
```

- `database.dump`: خروجی PostgreSQL با فرمت Custom و قابل انتقال
- `media.tar.gz`: محتوای Media Volume
- `production.env`: تنظیمات کامل Production داخل Repository رمزنگاری‌شده Restic
- `metadata.json`: تاریخ و Commit کد
- `SHA256SUMS`: تشخیص Corruption

Backup خام دیتابیس یا `.env` هیچ‌وقت به GitHub Artifact فرستاده نمی‌شود.

## Restore Drill هفتگی

```text
ops/backup/restore-drill.sh
```

این تست به دیتابیس اصلی دست نمی‌زند:

1. آخرین Snapshot را دانلود می‌کند.
2. Hash تمام فایل‌ها را بررسی می‌کند.
3. آرشیو Media را تست می‌کند.
4. یک PostgreSQL Database موقت می‌سازد.
5. Dump را کامل Restore می‌کند.
6. Migrationها و Walletها را Query می‌کند.
7. دیتابیس موقت را حذف می‌کند.

داشتن فایل Backup کافی نیست؛ Restore Drill اثبات می‌کند فایل واقعاً قابل بازیابی است.

## مانیتورینگ

Workflow `Monitor Production Backups` هر روز اجرا می‌شود و این موارد را کنترل می‌کند:

- آخرین Backup کمتر از ۳۶ ساعت عمر داشته باشد.
- آخرین Restore Drill کمتر از ۸ روز عمر داشته باشد.
- هر دو Timer فعال باشند.
- آخرین Backup و Drill وضعیت `success` داشته باشند.

خلاصه امن در Issue شماره 25 ثبت می‌شود.

## دستورات وضعیت سرور

```bash
systemctl list-timers 'apluscard-*'
systemctl status apluscard-backup.timer
systemctl status apluscard-restore-drill.timer
cat /var/lib/apluscard-backup/last-backup.json
cat /var/lib/apluscard-backup/last-restore-drill.json
journalctl -u apluscard-backup.service --no-pager -n 150
```

اجرای دستی:

```bash
systemctl start apluscard-backup.service
systemctl start apluscard-restore-drill.service
```

## بازیابی کامل روی سرور جدید

### ۱. نصب پیش‌نیازها

Docker، Docker Compose، Git، Restic و jq نصب شوند.

### ۲. دریافت کد

```bash
git clone https://github.com/hsdarestani/apluscard.git /root/apluscard
cd /root/apluscard
```

Repository باید Private و Clone با دسترسی امن انجام شود.

### ۳. ایجاد `.backup.env`

Recovery Secretها از GitHub Secrets و Password Manager گرفته شوند:

```bash
RESTIC_REPOSITORY='s3:https://S3-ENDPOINT/apluscard-production-backups'
RESTIC_PASSWORD='RESTIC-RECOVERY-PASSWORD'
AWS_ACCESS_KEY_ID='ACCESS-KEY'
AWS_SECRET_ACCESS_KEY='SECRET-KEY'
AWS_DEFAULT_REGION='auto'
RESTIC_CACHE_DIR='/var/cache/restic'
BACKUP_HOST_TAG='apluscard-production'
```

```bash
chmod 600 /root/apluscard/.backup.env
```

### ۴. Restore کامل

```bash
cd /root/apluscard
chmod 700 ops/backup/*.sh
RESTORE_PRODUCTION=YES ./ops/backup/restore-production.sh latest
```

Snapshot مشخص:

```bash
RESTORE_PRODUCTION=YES ./ops/backup/restore-production.sh SNAPSHOT_ID
```

اسکریپت Hashها را بررسی می‌کند، `.env`، دیتابیس و Media را بازیابی می‌کند، اپ را Build می‌کند و Health Check، Django Check و Migration Check اجرا می‌کند.

## بررسی بعد از Disaster Recovery

- Login ایمیل و Apple
- Dashboard مشتری و موجودی
- QR و Apple Wallet
- پنل Staff و Inhaber
- آخرین Belegها
- یک Top-up کوچک آزمایشی و اصلاح آن طبق Flow مالی

## قواعد امنیتی

- Bucket کاملاً Private باشد.
- Access Key فقط به Bucket مخصوص Backup دسترسی داشته باشد.
- Restic Password با رمز S3 متفاوت باشد.
- Recovery Key در GitHub Secrets و یک Password Manager مستقل نگهداری شود.
- حداقل سالی یک‌بار Restore کامل روی سرور جداگانه تمرین شود.
- قبل از Rotation کلیدهای Object Storage، دسترسی Restic تست شود.
