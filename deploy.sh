#!/bin/bash
# Deploy / update script for VPS
# Usage on VPS: cd /opt/mealie && ./deploy.sh

set -e

echo "==> Pulling latest code..."
git pull origin main

echo "==> Building images..."
docker compose -f docker-compose.prod.yml build

echo "==> Restarting services..."
docker compose -f docker-compose.prod.yml up -d

echo "==> Cleaning up old images..."
docker image prune -f

echo "==> Status:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "==> Done! Logs: docker compose -f docker-compose.prod.yml logs -f"
