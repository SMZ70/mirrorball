#!/usr/bin/env bash
# Ship mmdj to the Pi and rebuild.
#
# bridge.json is rsynced but never committed or baked into the image -- it is
# mounted in at runtime, which is what keeps this repo publishable.
set -euo pipefail

HOST="${MMDJ_HOST_SSH:-pi}"
DIR="${MMDJ_DIR:-mmdj}"

cd "$(dirname "$0")/.."

rsync -az --delete \
    --exclude '.venv/' --exclude '.git/' --exclude '.pytest_cache/' \
    --exclude '.ruff_cache/' --exclude '__pycache__/' --exclude 'bridge.json.old' \
    ./ "$HOST:~/$DIR/"

ssh "$HOST" "mkdir -p ~/$DIR/shows && cd ~/$DIR && docker compose up -d --build"
ssh "$HOST" "docker compose -f ~/$DIR/docker-compose.yml ps"
