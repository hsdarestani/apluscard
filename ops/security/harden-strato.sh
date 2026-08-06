#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_HOST="${EXPECTED_HOST:-217.160.50.71}"
SSH_PORT="${SSH_PORT:-22}"
APP_DIR="${APP_DIR:-/root/apluscard}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Dieses Script muss als root ausgeführt werden." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ufw \
  fail2ban \
  unattended-upgrades \
  apt-listchanges \
  auditd \
  audispd-plugins \
  jq

# Persistent, size-bounded system logs for incident response.
install -d -m 2755 /var/log/journal
install -d -m 755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/99-sams-security.conf <<'EOF'
[Journal]
Storage=persistent
Compress=yes
Seal=yes
SystemMaxUse=1G
RuntimeMaxUse=256M
MaxRetentionSec=2592000
EOF
systemctl restart systemd-journald

# Key-only SSH. Root remains available with a key because the deployment system
# currently uses it; password and interactive authentication are disabled.
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-sams-hardening.conf <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password
PermitEmptyPasswords no
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
EOF
sshd -t

# Firewall: only SSH and public web traffic are exposed.
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw limit "${SSH_PORT}/tcp" comment "Rate-limited SSH"
ufw allow 80/tcp comment "HTTP for redirect and ACME"
ufw allow 443/tcp comment "HTTPS production"
ufw --force enable

# Brute-force protection for SSH and Nginx authentication patterns.
cat > /etc/fail2ban/jail.d/sams.local <<EOF
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = ${SSH_PORT}
mode = aggressive

[nginx-http-auth]
enabled = true

[nginx-botsearch]
enabled = true
EOF
systemctl enable --now fail2ban
fail2ban-client reload

# Security updates install automatically; reboots remain a controlled action.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52sams-unattended-upgrades <<'EOF'
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
systemctl enable --now unattended-upgrades.service

# Audit changes to the highest-risk configuration locations. Secrets are never
# logged; only metadata about access and modification is recorded.
AUDIT_RULES=/etc/audit/rules.d/sams.rules
: > "$AUDIT_RULES"
add_watch() {
  local path="$1"
  local key="$2"
  if [[ -e "$path" ]]; then
    printf -- '-w %s -p wa -k %s\n' "$path" "$key" >> "$AUDIT_RULES"
  fi
}
add_watch "$APP_DIR/.env" sams_production_env
add_watch "$APP_DIR/.backup.env" sams_backup_env
add_watch /etc/ssh/ ssh_configuration
add_watch /etc/nginx/ nginx_configuration
add_watch /etc/systemd/system/ systemd_configuration
add_watch /root/.ssh/authorized_keys privileged_ssh_keys
chmod 600 "$AUDIT_RULES"
augenrules --load
systemctl enable --now auditd

# Restrict sensitive local files when present.
for path in \
  "$APP_DIR/.env" \
  "$APP_DIR/.backup.env" \
  "$APP_DIR/.initial-credentials"; do
  if [[ -f "$path" ]]; then
    chown root:root "$path"
    chmod 600 "$path"
  fi
done
if [[ -d /root/.ssh ]]; then
  chmod 700 /root/.ssh
fi
if [[ -f /root/.ssh/authorized_keys ]]; then
  chmod 600 /root/.ssh/authorized_keys
fi

systemctl reload ssh

# Machine-readable evidence for the compliance package.
install -d -m 700 /var/lib/apluscard-security
STATUS_FILE="/var/lib/apluscard-security/last-hardening.json"
cat > "$STATUS_FILE" <<JSON
{
  "status": "success",
  "completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "host": "$EXPECTED_HOST",
  "ssh_port": $SSH_PORT,
  "password_authentication": false,
  "root_login": "prohibit-password",
  "ufw": "$(ufw status | head -n 1 | sed 's/.*: //')",
  "fail2ban": "$(systemctl is-active fail2ban)",
  "unattended_upgrades": "$(systemctl is-active unattended-upgrades)",
  "auditd": "$(systemctl is-active auditd)",
  "persistent_journal": true
}
JSON
chmod 600 "$STATUS_FILE"

sshd -t
ufw status verbose
fail2ban-client status sshd
auditctl -s
jq -e '.status == "success"' "$STATUS_FILE" >/dev/null

echo "STRATO-Hardening erfolgreich. Ein kontrollierter Kernel-Reboot kann bei Bedarf separat geplant werden."
