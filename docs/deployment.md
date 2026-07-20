# Automated production deployment

The `Test and Deploy` GitHub Actions workflow runs the Django test suite for pull requests. After a successful push or merge to `main`, it connects to the Hetzner server over SSH, updates the repository, uploads the production `.env`, rebuilds the Docker services and verifies `/health/`.

## Required GitHub Actions secrets

Create these under:

`Repository Settings -> Secrets and variables -> Actions -> New repository secret`

| Secret | Value |
|---|---|
| `HETZNER_HOST` | `91.107.145.196` |
| `HETZNER_PORT` | SSH port, normally `22` |
| `HETZNER_USER` | Recommended: `deploy`; `root` also works but is less desirable |
| `HETZNER_SSH_KEY` | Complete private SSH key, including the BEGIN/END lines |
| `HETZNER_KNOWN_HOSTS` | Output of `ssh-keyscan -H -p 22 91.107.145.196` |
| `APP_ENV_B64` | Base64-encoded production `.env` file |

The workflow uses the GitHub `production` environment. Repository secrets work as configured; environment-level secrets can also be used later for approvals and tighter access control.

## One-time server preparation

Run these commands on the Hetzner server as `root`:

```bash
apt-get update
apt-get install -y git curl docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
systemctl enable --now docker nginx

adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
```

Log out and back in after adding `deploy` to the Docker group.

## Create a dedicated deployment SSH key

Run on your own trusted computer:

```bash
ssh-keygen -t ed25519 -C "github-actions-apluscard" -f ./apluscard_deploy
ssh-copy-id -i ./apluscard_deploy.pub deploy@91.107.145.196
```

Set the full content of `apluscard_deploy` as `HETZNER_SSH_KEY`.

Generate the host-key secret from a trusted connection:

```bash
ssh-keyscan -H -p 22 91.107.145.196 > apluscard_known_hosts
cat apluscard_known_hosts
```

Verify the fingerprint against the server before saving the output as `HETZNER_KNOWN_HOSTS`.

## Build the production environment secret

Create a local file named `.env.production` that is never committed:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-value
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=cards.smarbiz.sbs,91.107.145.196,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://cards.smarbiz.sbs
DJANGO_TIME_ZONE=Europe/Berlin
DJANGO_SECURE_COOKIES=1
DJANGO_HSTS_SECONDS=0
DATABASE_URL=postgresql://apluscard:replace-db-password@db:5432/apluscard
POSTGRES_DB=apluscard
POSTGRES_USER=apluscard
POSTGRES_PASSWORD=replace-db-password
```

Generate safe values:

```bash
openssl rand -base64 48   # Django secret key
openssl rand -hex 24      # PostgreSQL password
```

Encode the complete file as one line.

Linux:

```bash
base64 -w 0 .env.production
```

macOS:

```bash
base64 < .env.production | tr -d '\n'
```

Save that output as `APP_ENV_B64`. Base64 is only an encoding; GitHub Secrets provides the actual encrypted storage.

## One-time Nginx and HTTPS setup

After the first successful deployment, run on the server:

```bash
sudo cp "$HOME/apluscard/deploy/nginx/cards.smarbiz.sbs.conf" \
  /etc/nginx/sites-available/cards.smarbiz.sbs
sudo ln -sfn /etc/nginx/sites-available/cards.smarbiz.sbs \
  /etc/nginx/sites-enabled/cards.smarbiz.sbs
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d cards.smarbiz.sbs
```

Confirm the DNS `A` record points to `91.107.145.196` before requesting the certificate.

After HTTPS is working, change `DJANGO_HSTS_SECONDS` in `.env.production` to `31536000`, regenerate `APP_ENV_B64`, and run the workflow again.

## Deployment behavior

- Pull request: tests only
- Push/merge to `main`: tests, then production deployment
- Manual run: Actions -> Test and Deploy -> Run workflow on `main`
- Remote application directory: `$HOME/apluscard`
- Internal application address: `127.0.0.1:8010`
- Health endpoint: `http://127.0.0.1:8010/health/`

The public repository is cloned over HTTPS, so the server does not need a GitHub deploy key. The SSH key stored in GitHub is used only for GitHub Actions to access the Hetzner server.
