#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/aitopiahub}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.yml}"

cd "$STACK_DIR"
echo "=== host ==="
hostname
date


echo "=== docker compose ps ==="
docker compose -f "$COMPOSE_FILE" ps


echo "=== celery workers ==="
docker exec aitopiahub_worker_content celery -A aitopiahub.tasks.celery_app inspect ping || true


echo "=== recent production log ==="
tail -n 80 data/production.log || true
