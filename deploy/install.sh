#!/usr/bin/env bash
# HomeUtil installer for Ubuntu/Debian (apt) or RHEL/CentOS/Fedora/Rocky (dnf/yum).
# Sets up a venv, installs deps, registers a systemd service, and opens the
# firewall port. Run from the repo root as root or via sudo:
#
#   sudo ./deploy/install.sh
#   sudo PORT=9000 ./deploy/install.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="homeutil"
PORT="${PORT:-8000}"
APP_USER="${APP_USER:-${SUDO_USER:-$(whoami)}}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root (e.g. with sudo)." >&2
    exit 1
fi

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
else
    echo "Cannot detect OS (no /etc/os-release)." >&2
    exit 1
fi

case "$ID ${ID_LIKE:-}" in
    *ubuntu*|*debian*)
        OS_FAMILY="debian"
        ;;
    *rhel*|*centos*|*fedora*|*rocky*|*almalinux*)
        OS_FAMILY="rhel"
        ;;
    *)
        echo "Unsupported OS: $ID. This script supports Ubuntu/Debian and RHEL/CentOS/Fedora/Rocky." >&2
        exit 1
        ;;
esac

echo "==> Detected OS family: $OS_FAMILY (installing as user: $APP_USER, port: $PORT)"

echo "==> Installing system packages"
if [[ "$OS_FAMILY" == "debian" ]]; then
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip ufw tesseract-ocr poppler-utils
else
    PKG_MGR=$(command -v dnf || command -v yum)
    # python3.11 alongside the system python3 -- RHEL/Rocky/CentOS's default
    # python3 is frequently 3.9 (see below), which is too old for this
    # codebase's `str | None` (PEP 604) type hints.
    "$PKG_MGR" install -y python3 python3-pip python3.11 firewalld tesseract poppler-utils
    systemctl enable --now firewalld
fi

echo "==> Creating virtualenv and installing Python dependencies"
if [[ -d "$APP_DIR/.venv" ]]; then
    echo "    Removing existing .venv (a venv copied from another machine/OS won't run here)"
    rm -rf "$APP_DIR/.venv"
fi

# Pick the newest available Python 3.10+ interpreter -- this codebase uses
# `str | None` union-type syntax (PEP 604), which 3.9 can't parse at all
# (hard TypeError at import time, not just a lint warning). Plain `python3`
# on RHEL/Rocky/CentOS commonly still resolves to 3.9, so check newest-first
# rather than assuming `python3` is new enough.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c 'import sys; print(sys.version_info[:2] >= (3, 10))')
        if [[ "$version" == "True" ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: no Python 3.10+ interpreter found (checked python3.13/3.12/3.11/3.10/python3)." >&2
    echo "This codebase requires 3.10+ for 'str | None' type hints. Install one (e.g. 'dnf install python3.11') and re-run." >&2
    exit 1
fi
echo "    Using $PYTHON_BIN ($("$PYTHON_BIN" --version))"

sudo -u "$APP_USER" "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Preparing data directory"
mkdir -p "$APP_DIR/data"
chown "$APP_USER":"$APP_USER" "$APP_DIR/data"

echo "==> Installing systemd service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
sed -e "s|{{APP_DIR}}|$APP_DIR|g" \
    -e "s|{{APP_USER}}|$APP_USER|g" \
    -e "s|{{PORT}}|$PORT|g" \
    "$APP_DIR/deploy/homeutil.service.template" > "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "==> Opening firewall port $PORT/tcp"
if [[ "$OS_FAMILY" == "debian" ]]; then
    ufw allow "${PORT}/tcp" || true
else
    firewall-cmd --permanent --add-port="${PORT}/tcp"
    firewall-cmd --reload
fi

echo
echo "HomeUtil installed and running as '$APP_USER' on port $PORT."
echo "Status:  systemctl status $SERVICE_NAME"
echo "Logs:    journalctl -u $SERVICE_NAME -f"
echo "URL:     http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
