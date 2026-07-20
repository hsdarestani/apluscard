# A+ Card MVP

A mobile-first, API-ready customer card and stored-value wallet for cafés, lounges and similar businesses.

## Included in the first draft

- Customer dashboard with balance, QR card and transaction history
- Staff checkout flow with QR scanning and purchase deductions
- Manager dashboard for customer cards, top-ups, refunds and blocking
- Immutable ledger-style transaction records with before/after balances
- Audit events for sensitive wallet operations
- Role-based access: Owner, Manager, Staff and Customer
- REST API foundation for future iOS and Android apps
- Installable Progressive Web App (PWA)
- Docker deployment with PostgreSQL

## Architecture

- Django 5.2 LTS
- Django REST Framework 3.16
- PostgreSQL
- Gunicorn + WhiteNoise
- Mobile-first server-rendered PWA
- Optional Caddy or existing Nginx reverse proxy

The web interface and future native applications share the same backend and wallet ledger. Native iOS/Android apps can later be built in Flutter, React Native or Capacitor without replacing the backend.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# For local SQLite, remove or comment DATABASE_URL from .env.
export DJANGO_DEBUG=1
export DJANGO_SECURE_COOKIES=0
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Demo accounts created by `seed_demo`:

- `owner / ChangeMe123!`
- `staff / ChangeMe123!`
- `customer / ChangeMe123!`

Change these passwords immediately outside a local demo.

## Production deployment on Hetzner

Target:

- Server: `91.107.145.196`
- Domain: `cards.smarbiz.sbs`
- App port on host: `127.0.0.1:8010`

### 1. DNS

Create an `A` record:

```text
cards.smarbiz.sbs -> 91.107.145.196
```

### 2. Clone and configure

```bash
sudo mkdir -p /opt/apluscard
sudo chown "$USER":"$USER" /opt/apluscard
git clone https://github.com/hsdarestani/apluscard.git /opt/apluscard
cd /opt/apluscard
cp .env.example .env
nano .env
```

Generate a secret key and database password before starting.

### 3A. Existing Nginx on the server

```bash
docker compose up -d --build
sudo cp deploy/nginx/cards.smarbiz.sbs.conf /etc/nginx/sites-available/cards.smarbiz.sbs
sudo ln -s /etc/nginx/sites-available/cards.smarbiz.sbs /etc/nginx/sites-enabled/cards.smarbiz.sbs
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d cards.smarbiz.sbs
```

After HTTPS is active, set `DJANGO_HSTS_SECONDS=31536000` in `.env` and restart the web container.

### 3B. No existing web server: Caddy with automatic HTTPS

Only use this option when ports 80 and 443 are free:

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

### 4. Create initial users

For a temporary demo:

```bash
docker compose exec web python manage.py seed_demo
```

For a clean production owner account:

```bash
docker compose exec web python manage.py createsuperuser
```

Use `/admin/` to create the business, memberships and initial customer cards.

## API endpoints

- `GET /api/v1/me/`
- `GET /api/v1/wallet/`
- `GET /api/v1/wallet/transactions/`
- `POST /api/v1/staff/charge/`
- `POST /api/v1/manager/topup/`
- `POST /api/v1/manager/refund/`

Session authentication works for the current PWA. Token authentication is enabled for future native clients and POS integrations.

## Next modules

1. Customer onboarding and wallet claim flow
2. Loyalty points, tiers and rewards
3. Reservations and events
4. POS connector with idempotent payment requests
5. Push notifications and promotions
6. Native iOS/Android client using the existing API

## Important product/legal note

Keep the balance usable only inside the issuing business, non-transferable and normally non-withdrawable until the German legal and tax treatment has been reviewed. POS/tax integration should store the external receipt or order reference in every wallet transaction.
