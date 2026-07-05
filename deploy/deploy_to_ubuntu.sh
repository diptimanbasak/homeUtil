#!/usr/bin/env bash
# Run this FROM YOUR MAC to ship HomeUtil to an Ubuntu box over SSH.
#
# Syncs the repo (rsync over ssh -- like scp, but incremental and can
# exclude files) to the remote host, then runs deploy/install.sh there
# to (re)install dependencies and restart the systemd service. Safe to
# re-run any time you want to push a new version.
#
# Requires: passwordless (key-based) SSH access to the remote host,
# and passwordless sudo there (or be ready to type your sudo password
# when prompted).
#
# Usage:
#   ./deploy/deploy_to_ubuntu.sh user@ubuntu-host [remote_dir]
#   PORT=9000 ./deploy/deploy_to_ubuntu.sh user@ubuntu-host
#
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 user@host [remote_dir]" >&2
    exit 1
fi

REMOTE="$1"
REMOTE_DIR="${2:-homeutil}"
PORT="${PORT:-8000}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Syncing code to $REMOTE:$REMOTE_DIR"
rsync -az --delete \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".git" \
    --exclude "data/*.db" \
    --exclude "data/receipts" \
    "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/"

echo "==> Installing/updating on $REMOTE (port $PORT)"
ssh -t "$REMOTE" "cd $REMOTE_DIR && sudo PORT=$PORT ./deploy/install.sh"

echo
echo "==> Done."
echo "Logs:   ssh $REMOTE journalctl -u homeutil -f"
echo "Status: ssh $REMOTE systemctl status homeutil"
