# HomeUtil

A personal home management dashboard: vehicle maintenance tracking, household chore scheduling, and expense tracking via receipt-photo scanning.

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

Data is stored in a local SQLite file at `data/homeutil.db`; uploaded receipt photos go in `data/receipts/`.

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

## Deploying to a home server

Two scripts in `deploy/` handle installing this as a systemd service on Ubuntu/Debian or RHEL-family Linux:

```bash
# From your Mac/dev machine:
./deploy/deploy_to_ubuntu.sh user@your-server [remote_dir]
```

This rsyncs the code over and runs `deploy/install.sh` on the remote host, which sets up a Python venv, installs dependencies, and registers/starts a `homeutil` systemd service.

To set `ANTHROPIC_API_KEY` on the server persistently (survives future redeploys), use a systemd override rather than editing the generated service file directly:

```bash
sudo mkdir -p /etc/systemd/system/homeutil.service.d
sudo tee /etc/systemd/system/homeutil.service.d/override.conf <<'EOF'
[Service]
Environment=ANTHROPIC_API_KEY=sk-ant-...
EOF
sudo systemctl daemon-reload && sudo systemctl restart homeutil
```

Useful commands on the server:

```bash
sudo systemctl status homeutil
sudo journalctl -u homeutil -f      # tail logs
sudo systemctl restart homeutil
```
