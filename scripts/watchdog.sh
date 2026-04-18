#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/aitopiahub}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.yml}"

cd "$STACK_DIR"
services=(app worker_content worker_publish worker_trend beat redis postgres)
for s in "${services[@]}"; do
  if ! docker compose -f "$COMPOSE_FILE" ps --status running --services | grep -qx "$s"; then
    echo "[watchdog] restarting missing service: $s"
    docker compose -f "$COMPOSE_FILE" up -d "$s"
  fi
done
