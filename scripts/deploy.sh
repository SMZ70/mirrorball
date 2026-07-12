#!/usr/bin/env bash
# Ship mirrorball to a host (a Raspberry Pi, say) and rebuild there.
#
#   MIRRORBALL_SSH=pi ./scripts/deploy.sh
#
# bridge.json is rsynced but never committed or baked into the image -- it is
# mounted in at runtime, which is what keeps this repo publishable.
set -euo pipefail

HOST="${MIRRORBALL_SSH:-}"
DIR="${MIRRORBALL_DIR:-mirrorball}"

if [ -z "$HOST" ]; then
    echo "set MIRRORBALL_SSH to an ssh host, e.g. MIRRORBALL_SSH=pi $0" >&2
    exit 2
fi

cd "$(dirname "$0")/.."

# shows/ is excluded from --delete on purpose: it is the user's saved work, it
# lives only on the host, and a laptop that has never saved a show would
# otherwise delete every one of them.
rsync -az --delete \
    --exclude '.venv/' --exclude '.git/' --exclude '.pytest_cache/' \
    --exclude '.ruff_cache/' --exclude '__pycache__/' \
    --exclude 'shows/' --exclude 'node_modules/' \
    ./ "$HOST:~/$DIR/"

ssh "$HOST" "mkdir -p ~/$DIR/shows && cd ~/$DIR && docker compose up -d --build"
ssh "$HOST" "docker compose -f ~/$DIR/docker-compose.yml ps"
