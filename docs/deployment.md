# Automated production deployment

The `Test and Deploy` GitHub Actions workflow runs tests for pull requests. After a successful push or merge to `main`, it connects to the Hetzner server as `root`, updates the repository, rebuilds Docker and verifies `/health/`.

## Required GitHub Actions secret

Create this under:

`Repository Settings -> Secrets and variables -> Actions -> New repository secret`

| Secret | Value |
|---|---|
| `HETZNER_PASSWORD` | The SSH password for `root` on `91.107.145.196` |

The host, port and user are fixed in the workflow:

- Host: `91.107.145.196`
- Port: `22`
- User: `root`
- Application directory: `/root/apluscard`

## One-time server preparation

Run as `root`:

```bash
apt-get update
apt-get install -y git curl docker.io docker-compose-v2 nginx certbot python3-certbot-nginx openssl
systemctl enable --now docker nginx

docker --version
docker compose version
```

If `docker-compose-v2` is unavailable, enable Universe first:

```bash
apt-get install -y software-properties-common
add-apt-repository -y universe
apt-get update
apt-get install -y docker-compose-v2
```

## Root password SSH login

Only change this if root password login does not already work from another terminal.

Set or replace the root password:

```bash
passwd root
```

Enable root password authentication:

```bash
cat >/etc/ssh/sshd_config.d/99-apluscard-root-password.conf <<'EOF'
PasswordAuthentication yes
PermitRootLogin yes
EOF

sshd -t
systemctl reload ssh
```

Keep the current SSH session open and verify login from a second terminal before closing it.

## Create the application environment once on the server

```bash
mkdir -p /root/apluscard

DJANGO_KEY="$(openssl rand -base64 48 | tr -d '\n')"
DB_PASSWORD="$(openssl rand -hex 24)"

cat >/root/apluscard/.env <<EOF
DJANGO_SECRET_KEY=$DJANGO_KEY
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=cards.smarbiz.sbs,91.107.145.196,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://cards.smarbiz.sbs
DJANGO_TIME_ZONE=Europe/Berlin
DJANGO_SECURE_COOKIES=1
DJANGO_HSTS_SECONDS=0
DATABASE_URL=postgresql://apluscard:$DB_PASSWORD@db:5432/apluscard
POSTGRES_DB=apluscard
POSTGRES_USER=apluscard
POSTGRES_PASSWORD=$DB_PASSWORD
EOF

chmod 600 /root/apluscard/.env
```

The `.env` remains on the server and GitHub Actions does not overwrite it.

## One-time Nginx and HTTPS setup

After the first successful deployment:

```bash
cp /root/apluscard/deploy/nginx/cards.smarbiz.sbs.conf \
  /etc/nginx/sites-available/cards.smarbiz.sbs

ln -sfn /etc/nginx/sites-available/cards.smarbiz.sbs \
  /etc/nginx/sites-enabled/cards.smarbiz.sbs

nginx -t
systemctl reload nginx
certbot --nginx -d cards.smarbiz.sbs
```

Confirm the DNS `A` record points to `91.107.145.196` before requesting the certificate.

After HTTPS works:

```bash
sed -i 's/^DJANGO_HSTS_SECONDS=.*/DJANGO_HSTS_SECONDS=31536000/' /root/apluscard/.env
cd /root/apluscard
docker compose restart web
```

## Deployment behavior

- Pull request: tests only
- Push/merge to `main`: tests, then production deployment
- Manual run: Actions -> Test and Deploy -> Run workflow on `main`
- Remote directory: `/root/apluscard`
- Internal application address: `127.0.0.1:8010`
- Health endpoint: `http://127.0.0.1:8010/health/`

## Security note

Password-based root deployment is intentionally simpler, but less secure than a dedicated non-root user with an SSH key. Use a long unique root password, keep it only in GitHub Secrets and avoid printing it in commands or logs.
