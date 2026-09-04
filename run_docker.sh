#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[DuctBot Docker] Enabling local X11 display permissions..."
xhost +local:root 2>/dev/null || true

# Determine if docker requires sudo privileges
DOCKER_CMD="docker"
if ! docker info >/dev/null 2>&1; then
    echo "[DuctBot Docker] Regular user cannot access docker.sock, escalating with sudo..."
    DOCKER_CMD="sudo docker"
fi

echo "[DuctBot Docker] Starting container via Docker Compose..."
if command -v docker-compose &> /dev/null && [ "$DOCKER_CMD" = "docker" ]; then
    docker-compose up "$@"
else
    $DOCKER_CMD compose up "$@"
fi
