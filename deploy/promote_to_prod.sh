#!/usr/bin/env bash
# Promotes the dev instance to prod -- both on the SAME box (towmater),
# as two separate directories/systemd services (see CLAUDE.md's "Where
# the code actually lives" / "Deploying" sections). Run this ON THE
# SERVER, from the dev directory, once a change there is ready to ship:
#
#   cd /winix/homeutil-dev && sudo ./deploy/promote_to_prod.sh
#   sudo PROD_DIR=/winix/homeutil ./deploy/promote_to_prod.sh
#
# Rsyncs dev -> prod (same excludes as deploy_to_ubuntu.sh -- .venv,
# __pycache__, .git, the sqlite db, and uploaded receipts are never
# touched, since those are prod's own server-side state, not code) then
# re-runs install.sh against the prod directory to rebuild its venv and
# restart its systemd service.
#
# This does NOT touch git at all -- it promotes whatever's currently on
# disk in the dev directory (committed or not). Commit and push from dev
# first if you want prod's checkout to match what's on GitHub.
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROD_DIR="${PROD_DIR:-/winix/homeutil}"
PROD_SERVICE_NAME="${PROD_SERVICE_NAME:-homeutil}"
PROD_PORT="${PROD_PORT:-8000}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this as root (e.g. with sudo) -- install.sh needs it." >&2
    exit 1
fi

if [[ "$DEV_DIR" == "$PROD_DIR" ]]; then
    echo "ERROR: DEV_DIR and PROD_DIR are the same ($DEV_DIR) -- refusing to rsync a directory onto itself." >&2
    exit 1
fi

echo "==> Promoting $DEV_DIR -> $PROD_DIR"
rsync -az --delete \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".git" \
    --exclude "data/*.db" \
    --exclude "data/receipts" \
    "$DEV_DIR/" "$PROD_DIR/"

echo "==> Reinstalling prod (service: $PROD_SERVICE_NAME, port: $PROD_PORT)"
( cd "$PROD_DIR" && SERVICE_NAME="$PROD_SERVICE_NAME" PORT="$PROD_PORT" ./deploy/install.sh )

echo
echo "==> Done."
echo "Logs:   journalctl -u $PROD_SERVICE_NAME -f"
echo "Status: systemctl status $PROD_SERVICE_NAME"
