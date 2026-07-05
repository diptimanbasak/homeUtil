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
    "$PKG_MGR" install -y python3 python3-pip firewalld tesseract poppler-utils
    systemctl enable --now firewalld
fi

echo "==> Creating virtualenv and installing Python dependencies"
if [[ -d "$APP_DIR/.venv" ]]; then
    echo "    Removing existing .venv (a venv copied from another machine/OS won't run here)"
    rm -rf "$APP_DIR/.venv"
fi
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
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
