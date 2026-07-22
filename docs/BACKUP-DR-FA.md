# فرایند استاندارد Backup و Disaster Recovery اپ A+

## هدف

این فرایند برای خرابی کامل سرور، حذف Docker Volume، Corruption دیتابیس، اشتباه انسانی یا انتقال اضطراری به سرور جدید طراحی شده است.

کد پروژه در GitHub است. موارد زیر جداگانه Backup می‌شوند:

1. دیتابیس PostgreSQL
2. فایل‌های `media` شامل تصاویر شعبه‌ها و آپلودهای آینده
3. فایل `.env` واقعی Production برای بازیابی تنظیمات و Secretهای سرویس

تمام داده‌ها **قبل از خروج از سرور** با Restic رمزنگاری می‌شوند.

## سطح سرویس

- **RPO فعلی:** حداکثر ۶ ساعت
- **RTO هدف:** کمتر از ۶۰ دقیقه روی یک سرور آماده
- Backup: چهار بار در روز، حدود ساعت‌های 00:20، 06:20، 12:20 و 18:20 سرور با تأخیر تصادفی حداکثر ۱۰ دقیقه
- Restore Drill: هر یکشنبه حدود ساعت 05:10

## مقصد فعلی بدون Payment

مقصد پیشنهادی فعلی یک Google Account اختصاصی با Google Drive رایگان است.

- Google Drive از طریق `rclone` متصل می‌شود.
- Restic از Backend رسمی `rclone:` استفاده می‌کند.
- Google فقط Chunkهای رمزنگاری‌شده Restic را می‌بیند.
- فایل خام دیتابیس یا `.env` به‌صورت خوانا وارد Drive نمی‌شود.
- حساب Google باید فقط برای Backup استفاده شود تا فضای Gmail و Photos ظرفیت Drive را مصرف نکنند.

راهنمای کامل راه‌اندازی Windows:

```text
docs/BACKUP-GOOGLE-DRIVE-SETUP-FA.md
```

زیرساخت همچنان از S3-compatible Storage هم پشتیبانی می‌کند تا در آینده بدون بازنویسی اسکریپت‌ها به مقصد پولی یا مقصد دوم منتقل شود.

## معماری فعلی و 3-2-1

بعد از فعال‌سازی Google Drive دو محل مستقل داریم:

- نسخه اصلی روی PostgreSQL و Media Volume سرور Production
- Snapshotهای تاریخی رمزنگاری‌شده در Google Drive خارج از سرور

این ساختار خرابی کامل سرور را پوشش می‌دهد، اما برای تعریف سخت‌گیرانه **3-2-1** یک کپی مستقل سوم هم لازم است. در آینده یکی از این گزینه‌ها اضافه می‌شود:

- هارد اکسترنال رمزنگاری‌شده که ماهانه Sync شود
- Google Account دوم
- Snapshot مستقل Hetzner
- Object Storage یک Provider دیگر

## Retention

- تمام Snapshotهای ۷ روز اخیر، تقریباً ۲۸ نقطه بازیابی شش‌ساعته
- ۳۰ نسخه روزانه
- ۱۲ نسخه هفتگی
- ۱۲ نسخه ماهانه
- ۳ نسخه سالانه

Retention واقعی تا زمانی قابل اجراست که ظرفیت Google Drive کافی باشد. Restic Deduplication باعث می‌شود فقط Blockهای تغییرکرده دوباره ذخیره شوند، ولی مانیتور پرشدن فضا همچنان ضروری است.

Prune فقط هفته‌ای یک‌بار اجرا می‌شود تا فشار I/O روزانه ایجاد نشود.

## Secretهای GitHub برای Google Drive

مسیر:

```text
Repository → Settings → Secrets and variables → Actions
```

این سه Secret لازم‌اند:

```text
BACKUP_RESTIC_REPOSITORY
BACKUP_RESTIC_PASSWORD
BACKUP_RCLONE_CONFIG_BASE64
```

مقدار Repository:

```text
rclone:gdrive:apluscard-production-backups
```

`BACKUP_RESTIC_PASSWORD` باید حداقل ۲۴ کاراکتر تصادفی داشته باشد. این رمز Recovery Key اصلی است و باید علاوه بر GitHub Secrets در Password Manager مالک کسب‌وکار نیز نگهداری شود.

`BACKUP_RCLONE_CONFIG_BASE64` نسخه Base64 فایل `rclone.conf` است. این فایل OAuth Token حساب Google را دارد و نباید در Repository یا پیام عمومی قرار بگیرد.

Secretهای زیر فقط برای مقصدهای S3 هستند و در حالت Google Drive لازم نیستند:

```text
BACKUP_AWS_ACCESS_KEY_ID
BACKUP_AWS_SECRET_ACCESS_KEY
BACKUP_AWS_DEFAULT_REGION
```

## راه‌اندازی اولیه

بعد از اتصال rclone و ایجاد سه Secret:

```text
GitHub → Actions → Configure Production Backups → Run workflow
```

Workflow به‌صورت خودکار:

1. Secretها را بدون چاپ مقدار بررسی می‌کند.
2. Restic، rclone و ابزارهای لازم را روی سرور نصب می‌کند.
3. OAuth Config را در `/root/.config/rclone/rclone.conf` با دسترسی root-only ذخیره می‌کند.
4. فایل `/root/apluscard/.backup.env` را با سطح دسترسی 600 می‌سازد.
5. Systemd Timerهای Backup و Restore Drill را فعال می‌کند.
6. اولین Backup واقعی را می‌گیرد.
7. همان Backup را در دیتابیس موقت Restore می‌کند.
8. Migrationها و Walletها را Query می‌کند.
9. نتیجه را در Issue شماره 25 ثبت می‌کند.

## محتوای منطقی هر Snapshot

قبل از رمزنگاری، Snapshot شامل این موارد است:

```text
database.dump
media.tar.gz
production.env
metadata.json
SHA256SUMS
```

- `database.dump`: خروجی PostgreSQL با فرمت Custom و قابل انتقال
- `media.tar.gz`: محتوای Media Volume
- `production.env`: تنظیمات کامل Production
- `metadata.json`: تاریخ، Commit کد و نوع Backend
- `SHA256SUMS`: تشخیص Corruption

Restic همه این فایل‌ها را به Chunkهای رمزنگاری‌شده تبدیل می‌کند. Backup خام دیتابیس یا `.env` هیچ‌وقت به GitHub Artifact یا Google Drive به‌صورت مستقیم و خوانا فرستاده نمی‌شود.

## Restore Drill هفتگی

```text
ops/backup/restore-drill.sh
```

این تست به دیتابیس اصلی دست نمی‌زند:

1. آخرین Snapshot را از Google Drive دانلود می‌کند.
2. Hash تمام فایل‌ها را بررسی می‌کند.
3. آرشیو Media را تست می‌کند.
4. یک PostgreSQL Database موقت می‌سازد.
5. Dump را کامل Restore می‌کند.
6. Migrationها و Walletها را Query می‌کند.
7. دیتابیس موقت را حذف می‌کند.

داشتن فایل Backup کافی نیست؛ Restore Drill اثبات می‌کند فایل واقعاً قابل بازیابی است.

## مانیتورینگ

Workflow `Monitor Production Backups` هر روز اجرا می‌شود و این موارد را کنترل می‌کند:

- آخرین Backup کمتر از ۸ ساعت عمر داشته باشد.
- آخرین Restore Drill کمتر از ۸ روز عمر داشته باشد.
- هر دو Timer فعال باشند.
- آخرین Backup و Drill وضعیت `success` داشته باشند.

خلاصه امن در Issue شماره 25 ثبت می‌شود و هیچ Secret یا داده مشتری در آن قرار نمی‌گیرد.

## دستورات وضعیت سرور

```bash
systemctl list-timers 'apluscard-*'
systemctl status apluscard-backup.timer
systemctl status apluscard-restore-drill.timer
cat /var/lib/apluscard-backup/last-backup.json
cat /var/lib/apluscard-backup/last-restore-drill.json
journalctl -u apluscard-backup.service --no-pager -n 150
```

تست مستقیم اتصال Google Drive:

```bash
rclone --config /root/.config/rclone/rclone.conf lsd gdrive:
```

اجرای دستی:

```bash
systemctl start apluscard-backup.service
systemctl start apluscard-restore-drill.service
```

## بازیابی کامل روی سرور جدید

### ۱. نصب پیش‌نیازها

Docker، Docker Compose، Git، Restic، rclone و jq نصب شوند.

### ۲. دریافت کد

```bash
git clone https://github.com/hsdarestani/apluscard.git /root/apluscard
cd /root/apluscard
```

Repository باید Private و Clone با دسترسی امن انجام شود.

### ۳. بازیابی تنظیمات rclone

محتوای Secret `BACKUP_RCLONE_CONFIG_BASE64` در یک متغیر موقت قرار گیرد و Decode شود:

```bash
install -m 700 -d /root/.config/rclone
printf '%s' 'BASE64_RCLONE_CONFIG' | base64 --decode > /root/.config/rclone/rclone.conf
chmod 600 /root/.config/rclone/rclone.conf
```

اتصال تست شود:

```bash
rclone --config /root/.config/rclone/rclone.conf lsd gdrive:
```

### ۴. ایجاد `.backup.env`

```bash
RESTIC_REPOSITORY='rclone:gdrive:apluscard-production-backups'
RESTIC_PASSWORD='RESTIC-RECOVERY-PASSWORD'
RCLONE_CONFIG='/root/.config/rclone/rclone.conf'
RESTIC_CACHE_DIR='/var/cache/restic'
BACKUP_HOST_TAG='apluscard-production'
```

فایل در مسیر زیر ذخیره شود:

```text
/root/apluscard/.backup.env
```

سطح دسترسی:

```bash
chmod 600 /root/apluscard/.backup.env
```

### ۵. Restore کامل

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

- حساب Google مخصوص Backup باشد.
- روی حساب Google، تأیید دومرحله‌ای فعال شود.
- فایل `rclone.conf` مثل Password نگهداری شود.
- Restic Password جدا از رمز Google باشد.
- Recovery Key در GitHub Secrets و یک Password Manager مستقل نگهداری شود.
- Repository روی Private باشد.
- حداقل سالی یک‌بار Restore کامل روی سرور جداگانه تمرین شود.
- قبل از تغییر یا حذف دسترسی Google، Restore Drill اجرا شود.
