# HomeUtil

A personal home management dashboard: vehicle maintenance tracking, household chore scheduling, and expense tracking via receipt-photo scanning.

**Primary development happens on the home server itself**, not a Mac — see "Where the code lives" below. This README still covers running a standalone copy locally (e.g. on a Mac, for a quick look or fully offline testing); see **README.txt** for that quick-start.

## Features

- **Vehicles** — track vehicles, log service history, and set maintenance reminders (due by date and/or mileage, with overdue/due-soon status).
- **Chores** — recurring household chores with frequency-based scheduling (daily, weekly, etc.) and completion logs.
- **Expenses** — snap a photo of a receipt and Claude reads the vendor, total, date, category, and individual line items (each with its own category) automatically. Works without an API key too — you just fill the fields in by hand.

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/settings/keys) (optional — only needed for automatic receipt scanning)

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The app runs on `http://0.0.0.0:8000` by default. Set `ANTHROPIC_API_KEY` in your environment to enable receipt scanning:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

On a Mac, `./deploy/setup_mac.sh` automates all of the above (plus installing `tesseract`/`poppler` for the free/OCR and PDF receipt-scanning paths) — see **README.txt** for the full quick-start and troubleshooting guide.

Data is stored in a local SQLite file at `data/homeutil.db`; uploaded receipt photos go in `data/receipts/`.

## Where the code lives

The home server (`towmater`) is the primary dev environment — not a Mac. It runs two sibling copies, each its own systemd service:

- `/winix/homeutil-dev` (`homeutil-dev` service, port 8001) — development
- `/winix/homeutil` (`homeutil` service, port 8000) — production, the live app

Edit the dev copy via **VSCode Remote-SSH** from any Mac (`Cmd+Shift+P` → "Remote-SSH: Connect to Host" → open `/winix/homeutil-dev`), rather than cloning the repo locally — no sync step, you're editing the real files directly. GitHub (`git@github.com:diptimanbasak/homeUtil.git`) is the git remote, kept for history/backup rather than as the main edit→deploy loop. See `CLAUDE.md` for the full architecture/workflow notes.

A small local LLM (Qwen3-8B-Q4, text-only — no image/vision support) also runs on towmater for other home-automation experiments; it's not currently wired into HomeUtil itself.

## Configuration

All environment variables (with defaults) live in `config.py`:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/homeutil.db` | Database connection string |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `DEBUG` | `false` | Flask debug mode |
| `ANTHROPIC_API_KEY` | unset | Enables automatic receipt analysis |
| `REMINDER_DUE_SOON_DAYS` | `30` | Days-out threshold for "due soon" vehicle reminders |
| `REMINDER_DUE_SOON_MILES` | `500` | Mileage threshold for "due soon" vehicle reminders |

## Deploying (dev → prod, both on towmater)

Scripts in `deploy/` handle installing this as a systemd service and promoting a dev change to production. Both dev and prod live on the same box (see "Where the code lives" above), so this is a local operation on towmater, not a Mac-to-server push:

```bash
# One-off / rebuild a venv + systemd service, run from either directory:
sudo SERVICE_NAME=homeutil-dev PORT=8001 ./deploy/install.sh   # dev
sudo ./deploy/install.sh                                        # prod (defaults: homeutil, 8000)

# Ship a dev change to prod, run from the dev directory:
sudo ./deploy/promote_to_prod.sh
```

`promote_to_prod.sh` rsyncs dev → prod (never touching prod's `data/homeutil.db` or `data/receipts/` — those are server-side state, not code) then re-runs `install.sh` against prod.

`deploy/deploy_to_ubuntu.sh user@host [remote_dir]` still exists for the (now rare) case of deploying to a genuinely different machine over SSH.

To set `ANTHROPIC_API_KEY` persistently (survives future `install.sh` runs), use a systemd override rather than editing the generated service file directly:

```bash
sudo mkdir -p /etc/systemd/system/homeutil.service.d
sudo tee /etc/systemd/system/homeutil.service.d/override.conf <<'EOF'
[Service]
Environment=ANTHROPIC_API_KEY=sk-ant-...
EOF
sudo systemctl daemon-reload && sudo systemctl restart homeutil
```

Useful commands on the server (swap `homeutil` for `homeutil-dev` for the dev instance):

```bash
sudo systemctl status homeutil
sudo journalctl -u homeutil -f      # tail logs
sudo systemctl restart homeutil
```

## Backups

`deploy/backup.sh`, run as root on towmater (e.g. via cron), tars up `data/homeutil.db`, `data/receipts/`, and the systemd override above into a dated archive under `/winix/homeutil-backups` (14-day retention by default). Writes locally only — copy it off-box periodically. See `CLAUDE.md` for details.
