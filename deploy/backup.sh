#!/usr/bin/env bash
# Backs up everything that isn't reproducible from git + install.sh:
#   - data/homeutil.db   (the SQLite database -- expenses, vehicles, chores, etc.)
#   - data/receipts/     (uploaded receipt photos/PDFs)
#   - the systemd drop-in override (ANTHROPIC_API_KEY) -- easy to forget
#     since it lives outside the app directory entirely (see CLAUDE.md's
#     "Deploying" section for why it's not in the repo)
#
# Writes a dated tar.gz to BACKUP_DIR and prunes archives older than
# RETENTION_DAYS. Intended to run on the Ubuntu box itself (not the Mac),
# via cron -- see the crontab line in this file's header comment below.
#
# Usage:
#   sudo ./deploy/backup.sh
#   sudo BACKUP_DIR=/mnt/other/path RETENTION_DAYS=30 ./deploy/backup.sh
#
# Suggested crontab (as root, `sudo crontab -e`), nightly at 2am:
#   0 2 * * * /winix/homeutil/deploy/backup.sh >> /var/log/homeutil-backup.log 2>&1
#
# This only writes backups locally -- copy BACKUP_DIR off this machine
# periodically (another disk, your Mac, cloud storage) so a disk failure
# or a reformat like the one that prompted this script can't take out
# both the live data and its backup at once.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERRIDE_FILE="/etc/systemd/system/homeutil.service.d/override.conf"

BACKUP_DIR="${BACKUP_DIR:-/winix/homeutil-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this as root (e.g. with sudo) -- it needs to read the systemd override file." >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$BACKUP_DIR/homeutil-$STAMP.tar.gz"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "==> Staging backup contents"
mkdir -p "$STAGING/data"
cp -a "$APP_DIR/data/homeutil.db" "$STAGING/data/" 2>/dev/null || echo "    WARNING: data/homeutil.db not found, skipping"
if [[ -d "$APP_DIR/data/receipts" ]]; then
    cp -a "$APP_DIR/data/receipts" "$STAGING/data/"
else
    echo "    WARNING: data/receipts not found, skipping"
fi
if [[ -f "$OVERRIDE_FILE" ]]; then
    cp -a "$OVERRIDE_FILE" "$STAGING/override.conf"
else
    echo "    WARNING: $OVERRIDE_FILE not found, skipping (no API key override set?)"
fi

echo "==> Writing $ARCHIVE"
tar czf "$ARCHIVE" -C "$STAGING" .
chmod 600 "$ARCHIVE"

echo "==> Pruning archives older than $RETENTION_DAYS days in $BACKUP_DIR"
find "$BACKUP_DIR" -name 'homeutil-*.tar.gz' -mtime "+$RETENTION_DAYS" -print -delete

echo "==> Done: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
