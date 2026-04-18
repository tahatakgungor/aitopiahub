#!/usr/bin/env bash
set -euo pipefail

# Standard hardening profile for Ubuntu/Debian VPS.
# WARNING: Run as root over an existing SSH session.

SSH_PORT="${SSH_PORT:-22}"
DEPLOY_USER="${DEPLOY_USER:-aitopia}"
DEPLOY_PUBKEY="${DEPLOY_PUBKEY:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ufw fail2ban unattended-upgrades ca-certificates curl

if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  usermod -aG sudo "$DEPLOY_USER"
fi

if [[ -n "$DEPLOY_PUBKEY" ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
  grep -qxF "$DEPLOY_PUBKEY" "/home/$DEPLOY_USER/.ssh/authorized_keys" || echo "$DEPLOY_PUBKEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

# SSH hardening
cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.bak.$(date +%Y%m%d%H%M%S)"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
if ! grep -q '^PubkeyAuthentication yes' /etc/ssh/sshd_config; then
  echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config
fi
if ! grep -q '^ChallengeResponseAuthentication no' /etc/ssh/sshd_config; then
  echo 'ChallengeResponseAuthentication no' >> /etc/ssh/sshd_config
fi

# Firewall profile
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow "$SSH_PORT"/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Fail2ban defaults
cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
port = ssh
maxretry = 5
findtime = 10m
bantime = 1h
EOF

# Automatic security updates
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

systemctl restart fail2ban
systemctl restart ssh || systemctl restart sshd

echo "Hardening applied. Verify SSH key login before closing this session."
