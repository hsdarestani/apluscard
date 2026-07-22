# فرایند استاندارد Backup و Disaster Recovery اپ A+

## هدف

این فرایند برای حالتی طراحی شده که یکی از اتفاق‌های زیر رخ دهد:

- خراب‌شدن کامل سرور Hetzner
- حذف یا Corruptشدن Docker Volume دیتابیس
- حذف فایل‌های Media
- اشتباه انسانی در دیتابیس
- نیاز به انتقال فوری سرویس به سرور جدید

کد پروژه در GitHub نگهداری می‌شود. مواردی که جداگانه Backup می‌شوند:

1. دیتابیس PostgreSQL
2. فایل‌های `media` شامل عکس شعبه‌ها و آپلودهای آینده
3. فایل `.env` واقعی Production شامل تنظیمات لازم برای بازیابی سرویس

تمام این داده‌ها قبل از خروج از سرور توسط Restic رمزنگاری می‌شوند.

## سطح سرویس مورد انتظار

- **RPO:** حداکثر ۲۴ ساعت از دست‌دادن داده در خرابی کامل سرور
- **RTO هدف:** بازگشت سرویس روی سرور جدید در کمتر از ۶۰ دقیقه
- Backup روزانه: حدود ساعت 03:20 به وقت سرور، با تأخیر تصادفی حداکثر ۱۵ دقیقه
- Restore Drill: هر یکشنبه حدود ساعت 05:10

برای تراکنش‌های مالی پرتعداد می‌توان در آینده Backup را به هر ۶ ساعت افزایش داد.

## معماری 3-2-1

- نسخه اصلی: PostgreSQL و Media روی سرور Production
- نسخه دوم: Snapshotهای رمزنگاری‌شده در Object Storage
- نسخه سوم: چند نسل تاریخی در همان Repository با Retention و رمزنگاری Restic

برای مقاومت بیشتر در برابر خرابی یا مسدودشدن یک Provider، بهتر است Object Storage متعلق به Provider دیگری غیر از سرور اصلی باشد؛ مثلاً Cloudflare R2 یا Backblaze B2 در کنار سرور Hetzner.

## Retention

Restic به‌صورت خودکار این نسخه‌ها را نگه می‌دارد:

- ۱۴ نسخه روزانه
- ۸ نسخه هفتگی
- ۱۲ نسخه ماهانه
- ۳ نسخه سالانه

Prune فقط هفته‌ای یک‌بار اجرا می‌شود تا فشار I/O روزانه ایجاد نشود.

## Secretهای لازم در GitHub

در مسیر زیر:

```text
Repository → Settings → Secrets and variables → Actions
```

این Secretها باید ایجاد شوند:

```text
BACKUP_RESTIC_REPOSITORY
BACKUP_RESTIC_PASSWORD
BACKUP_AWS_ACCESS_KEY_ID
BACKUP_AWS_SECRET_ACCESS_KEY
BACKUP_AWS_DEFAULT_REGION
```

نمونه Repository برای یک مقصد S3-compatible:

```text
s3:https://S3-ENDPOINT/apluscard-production-backups
```

`BACKUP_RESTIC_PASSWORD` باید یک رمز کاملاً تصادفی حداقل ۲۴ کاراکتری باشد. این رمز کل Backup Repository را رمزگشایی می‌کند و باید خارج از سرور هم نگهداری شود. GitHub Secret محل اصلی نگهداری Recovery Key است.

هیچ‌کدام از این مقادیر نباید داخل Repository، Issue، پیام عمومی یا فایل `.env.example` قرار بگیرند.

## راه‌اندازی اولیه

بعد از ایجاد Bucket و Secretها:

```text
GitHub → Actions → Configure Production Backups → Run workflow
```

Workflow به‌صورت خودکار:

1. Secretها را بدون چاپ مقدار بررسی می‌کند.
2. Restic و ابزارهای لازم را روی سرور نصب می‌کند.
3. فایل محافظت‌شده `/root/apluscard/.backup.env` را ایجاد می‌کند.
4. دو Systemd Timer را فعال می‌کند.
5. اولین Backup واقعی را می‌گیرد.
6. همان Backup را در یک دیتابیس موقت Restore می‌کند.
7. تعداد Migrationها و Walletها را بررسی می‌کند.
8. نتیجه را در GitHub Issue شماره 25 ثبت می‌کند.

## محتوای هر Snapshot

هر Snapshot شامل این فایل‌هاست:

```text
database.dump
media.tar.gz
production.env
metadata.json
SHA256SUMS
```

- `database.dump`: خروجی قابل انتقال PostgreSQL با فرمت Custom
- `media.tar.gz`: محتوای Docker Volume فایل‌های Media
- `production.env`: تنظیمات کامل Production، فقط داخل Repository رمزنگاری‌شده Restic
- `metadata.json`: تاریخ، Commit کد و نوع محتوا
- `SHA256SUMS`: تشخیص Corruption یا ناقص‌شدن فایل‌ها

## تست بازگردانی هفتگی

فایل زیر اجرا می‌شود:

```text
ops/backup/restore-drill.sh
```

این تست به دیتابیس اصلی دست نمی‌زند. مراحل آن:

1. آخرین Snapshot را از Object Storage دانلود می‌کند.
2. Hash تمام فایل‌ها را بررسی می‌کند.
3. آرشیو Media را تست می‌کند.
4. یک دیتابیس PostgreSQL موقت می‌سازد.
5. Dump را کامل داخل آن Restore می‌کند.
6. جدول Migrationها و Walletها را Query می‌کند.
7. دیتابیس موقت را حذف می‌کند.

صرفاً داشتن فایل Backup کافی نیست؛ موفق‌بودن Restore Drill اثبات می‌کند نسخه واقعاً قابل بازیابی است.

## مانیتورینگ

Workflow زیر هر روز اجرا می‌شود:

```text
Monitor Production Backups
```

شرایط سالم‌بودن:

- آخرین Backup کمتر از ۳۶ ساعت عمر داشته باشد.
- آخرین Restore Drill کمتر از ۸ روز عمر داشته باشد.
- هر دو Systemd Timer فعال باشند.
- آخرین Backup و Drill وضعیت `success` داشته باشند.

خلاصه وضعیت در Issue شماره 25 دیده می‌شود و هیچ داده مشتری یا Secret در گزارش نمایش داده نمی‌شود.

## مشاهده وضعیت روی سرور

```bash
systemctl list-timers 'apluscard-*'
systemctl status apluscard-backup.timer
systemctl status apluscard-restore-drill.timer
cat /var/lib/apluscard-backup/last-backup.json
cat /var/lib/apluscard-backup/last-restore-drill.json
```

مشاهده Log آخرین Backup:

```bash
journalctl -u apluscard-backup.service --no-pager -n 150
```

اجرای دستی Backup:

```bash
systemctl start apluscard-backup.service
```

اجرای دستی Restore Drill امن:

```bash
systemctl start apluscard-restore-drill.service
```

## بازیابی کامل روی سرور جدید

### ۱. آماده‌سازی سرور

Docker، Docker Compose، Git، Restic و jq نصب شوند.

### ۲. دریافت کد

```bash
git clone https://github.com/hsdarestani/apluscard.git /root/apluscard
cd /root/apluscard
```

Repository باید Private باشد و Clone با دسترسی امن انجام شود.

### ۳. ایجاد فایل `.backup.env`

Recovery Secretها از GitHub Secrets یا Password Manager برداشته و داخل فایل زیر قرار گیرند:

```text
/root/apluscard/.backup.env
```

ساختار:

```bash
RESTIC_REPOSITORY='s3:https://S3-ENDPOINT/apluscard-production-backups'
RESTIC_PASSWORD='RESTIC-RECOVERY-PASSWORD'
AWS_ACCESS_KEY_ID='ACCESS-KEY'
AWS_SECRET_ACCESS_KEY='SECRET-KEY'
AWS_DEFAULT_REGION='auto'
RESTIC_CACHE_DIR='/var/cache/restic'
BACKUP_HOST_TAG='apluscard-production'
```

سطح دسترسی:

```bash
chmod 600 /root/apluscard/.backup.env
```

### ۴. اجرای Restore کامل

```bash
cd /root/apluscard
chmod 700 ops/backup/*.sh
RESTORE_PRODUCTION=YES ./ops/backup/restore-production.sh latest
```

برای Restore یک Snapshot مشخص:

```bash
RESTORE_PRODUCTION=YES ./ops/backup/restore-production.sh SNAPSHOT_ID
```

اسکریپت به‌ترتیب:

1. Snapshot را دانلود و Hashها را بررسی می‌کند.
2. تنظیمات Production را بازیابی می‌کند.
3. PostgreSQL را بالا می‌آورد.
4. دیتابیس فعلی را با تأیید صریح جایگزین می‌کند.
5. Media Volume را بازیابی می‌کند.
6. Web App را Build و اجرا می‌کند.
7. Health Check، Django Check و Migration Check را اجرا می‌کند.

## بررسی دستی بعد از Disaster Recovery

بعد از Restore این Flowها تست شوند:

- Login با ایمیل
- Login با Apple
- بازشدن Dashboard مشتری
- نمایش موجودی و QR
- Apple Wallet Download
- پنل Staff
- پنل Inhaber
- بازشدن آخرین Belegها
- ثبت یک Top-up آزمایشی کوچک و سپس اصلاح آن طبق فرایند مالی

## قوانین امنیتی

- Backup خام دیتابیس هیچ‌وقت در GitHub Artifact یا Repository قرار نمی‌گیرد.
- `.env` فقط در Repository رمزنگاری‌شده Restic ذخیره می‌شود.
- Bucket نباید Public باشد.
- Access Key فقط اجازه دسترسی به Bucket مخصوص Backup را داشته باشد.
- Restic Password مستقل از رمز S3 باشد.
- حداقل سالی یک‌بار یک Disaster Recovery کامل روی سرور جداگانه تمرین شود.
- قبل از انقضا یا Rotation کلیدهای Object Storage، دسترسی Restic تست شود.
