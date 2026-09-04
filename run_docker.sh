#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[DuctBot Docker] Enabling local X11 display permissions..."
xhost +local:root 2>/dev/null || true

echo "[DuctBot Docker] Starting container via Docker Compose..."
if command -v docker-compose &> /dev/null; then
    docker-compose up "$@"
else
    docker compose up "$@"
fi
