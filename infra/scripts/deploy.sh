#!/usr/bin/env bash
# =============================================================================
# ScaleMyPrints workers deploy script (Hetzner VPS)
# =============================================================================
# Run from repo root on the VPS, after `git pull`.
# Idempotent — safe to re-run.
#
# Required env vars:
#   COMPOSE_FILE — defaults to infra/docker/docker-compose.yml
#   IMAGE_TAG    — defaults to latest
# =============================================================================

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-compose.yml}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

cd "$(dirname "$0")/../.."

echo "▶ Pulling latest from git..."
git pull origin main

echo "▶ Building workers image (tag: $IMAGE_TAG)..."
docker build \
    -f infra/docker/Dockerfile.workers \
    -t "scalemyprints-workers:$IMAGE_TAG" \
    -t "scalemyprints-workers:latest" \
    .

echo "▶ Restarting services..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate workers

echo "▶ Waiting for health check..."
for i in {1..30}; do
    if curl -fsS http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Workers healthy"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "✗ Health check failed after 30 attempts"
        docker compose -f "$COMPOSE_FILE" logs workers --tail=50
        exit 1
    fi
    sleep 2
done

echo "▶ Pruning old images..."
docker image prune -f --filter "until=168h" || true

echo ""
echo "✓ Deploy complete"
echo "  API:    http://$(hostname):8000"
echo "  Health: http://$(hostname):8000/health"
echo "  Docs:   http://$(hostname):8000/docs"
