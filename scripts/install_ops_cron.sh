#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/aitopiahub}"
LOGROTATE_PATH="/etc/logrotate.d/aitopiahub"
CRON_PATH="/etc/cron.d/aitopiahub-ops"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

cat > "$LOGROTATE_PATH" <<'EOF'
/opt/aitopiahub/data/*.log {
  daily
  rotate 14
  compress
  missingok
  notifempty
  copytruncate
}
EOF

cat > "$CRON_PATH" <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

*/10 * * * * root /opt/aitopiahub/scripts/watchdog.sh >> /opt/aitopiahub/data/watchdog.log 2>&1
0 8 * * * root /opt/aitopiahub/scripts/server_status.sh >> /opt/aitopiahub/data/heartbeat.log 2>&1
EOF
chmod 644 "$CRON_PATH"

service cron reload || systemctl restart cron || true

echo "Ops cron + logrotate installed"
