#!/usr/bin/env bash
# One-shot setup for running HomeUtil locally on a Mac (Apple Silicon or
# Intel) -- either the home server Mac you want up and running quickly, or
# a second Macbook you're developing on. This does NOT install a systemd
# service (that's Ubuntu-only, see deploy/install.sh) -- on a Mac this just
# gets dependencies installed and runs the dev server in the foreground,
# matching the "Running locally" instructions in CLAUDE.md.
#
# Usage:
#   ./deploy/setup_mac.sh                 # set up (if needed) and start the server
#   ./deploy/setup_mac.sh --setup-only     # just install deps, don't start the server
#   PORT=9000 ./deploy/setup_mac.sh        # start on a different port
#
# Safe to re-run any time -- skips steps that are already done.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

SETUP_ONLY=false
if [[ "${1:-}" == "--setup-only" ]]; then
    SETUP_ONLY=true
fi

echo "==> HomeUtil setup in $APP_DIR"

# --- Homebrew ---
if ! command -v brew &>/dev/null; then
    echo "Homebrew is required but not installed." >&2
    echo "Install it from https://brew.sh, then re-run this script." >&2
    exit 1
fi

# --- System packages ---
# python3 for the venv; tesseract + poppler for the free/OCR receipt-scanning
# path (routes/expenses.py's "Free (local OCR)" option and PDF support --
# see CLAUDE.md's "Running locally" section for why these are needed).
echo "==> Checking system packages (python3, tesseract, poppler)"
for formula in python3 tesseract poppler; do
    if brew list "$formula" &>/dev/null; then
        echo "    $formula already installed"
    else
        echo "    installing $formula..."
        brew install "$formula"
    fi
done

# --- Python virtualenv ---
if [[ ! -d ".venv" ]]; then
    echo "==> Creating virtualenv"
    python3 -m venv .venv
else
    echo "==> Virtualenv already exists"
fi

echo "==> Installing Python dependencies"
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# --- Data directory ---
mkdir -p data/receipts

# --- API key reminder ---
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo
    echo "NOTE: ANTHROPIC_API_KEY is not set in this shell."
    echo "Receipt scanning will fall back to blank fields (or use the Free/OCR"
    echo "option instead) until you export it, e.g. in ~/.zshrc:"
    echo '    export ANTHROPIC_API_KEY="sk-ant-..."'
fi

echo
echo "==> Setup complete."

if [[ "$SETUP_ONLY" == true ]]; then
    echo "Run it yourself with:"
    echo "    source .venv/bin/activate && python main.py"
    exit 0
fi

echo "==> Starting HomeUtil (Ctrl+C to stop)"
exec .venv/bin/python main.py
