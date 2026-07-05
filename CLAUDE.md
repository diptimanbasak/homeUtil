# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HomeUtil — a small personal Flask app for tracking home-related stuff: vehicle maintenance, household chores, and expenses (via receipt-photo scanning, using either the Claude API or free local OCR). Runs on a home Ubuntu server via systemd, developed on a Mac. SQLite backend, server-rendered Jinja2 templates, no JS framework or build step.

Keep changes simple and readable — this is a small, human-maintained personal project, not a large team codebase. Prefer the existing patterns (plain Flask routes, hardcoded URL strings instead of `url_for`, direct SQLAlchemy queries) over introducing new abstractions.

## Running locally

```bash
source .venv/bin/activate
pip install -r requirements.txt
python main.py                    # runs on 0.0.0.0:8000 by default (config.py: HOST/PORT env vars)
```

There is no test suite, linter, or build step configured for this project.

The free/OCR receipt-scanning option (`routes/expenses.py`: "Free" radio choice) needs the `tesseract-ocr` system binary, not just the `pytesseract` pip package — `brew install tesseract` on the Mac, or `apt-get install tesseract-ocr` on the Ubuntu server (already added to `deploy/install.sh`). PDF support for that same OCR path additionally needs `poppler` (`brew install poppler` / `apt-get install poppler-utils`), used by `pdf2image` to rasterize the first page.

## Deploying

The app runs on a separate Ubuntu home server, not the dev machine. Two scripts in `deploy/`:

- `deploy/deploy_to_ubuntu.sh user@host [remote_dir]` — run **from the Mac**. Rsyncs the repo to the remote host (excluding `.venv`, `__pycache__`, `.git`, the sqlite db, and the uploaded receipt photos) and then SSHes in to run `install.sh`. The db and receipts are excluded because they're server-side state, not code — an `rsync --delete` without those excludes would wipe them on every redeploy.
- `deploy/install.sh` — run **on the Ubuntu box** (via the script above, or manually with sudo). (Re)creates the venv, installs `requirements.txt`, regenerates and restarts the `homeutil` systemd service, opens the firewall port.

**Important**: `install.sh` regenerates `/etc/systemd/system/homeutil.service` from `deploy/homeutil.service.template` on every run, so any manual edits to that file (e.g. adding `ANTHROPIC_API_KEY`) get wiped on redeploy. Persistent env vars belong in a systemd drop-in override instead, which survives redeploys:

```bash
sudo mkdir -p /etc/systemd/system/homeutil.service.d
sudo tee /etc/systemd/system/homeutil.service.d/override.conf <<'EOF'
[Service]
Environment=ANTHROPIC_API_KEY=sk-ant-...
EOF
sudo systemctl daemon-reload && sudo systemctl restart homeutil
```

**Schema changes require manual migration.** `Base.metadata.create_all()` (called on every app startup in `main.py`) only creates missing tables — it never alters existing ones. Adding a column to an existing model means running `ALTER TABLE ... ADD COLUMN ...` by hand against `data/homeutil.db` on the server (there's no migration framework/Alembic in this project — keep it that way unless the data volume genuinely justifies it). To catch a forgotten migration before it surfaces as a confusing 500 on some random route, `database.py: check_schema_is_current()` runs right after `create_all()` on every startup: it inspects each existing table's actual columns against what the model expects, and if any are missing it prints the exact `ALTER TABLE` statement(s) needed and exits with a non-zero code instead of starting the app.

## Architecture

**Layering**: `main.py` (app factory/entrypoint) → `routes/*.py` (one Flask Blueprint per feature area) → `models.py` (all SQLAlchemy ORM models in one file) → `database.py` (engine/session setup). `config.py` centralizes all environment-dependent settings (DB URL, host/port, API keys, thresholds) — always add new env-configurable values there, not scattered `os.getenv()` calls in routes.

**Database sessions**: Flask doesn't have a built-in per-request DB session, so `database.py` implements one via `flask.g`: call `get_db()` at the top of any route to get a session (opens one lazily, reused for the rest of the request), and `close_db()` is registered as an `app.teardown_appcontext` in `main.py` to close it after the response. Don't instantiate `SessionLocal()` directly in routes.

**Route module shape** (`routes/vehicles.py`, `routes/chores.py`, `routes/expenses.py`): each defines a `Blueprint` named `bp`, registered in `main.py`. Each follows the same CRUD pattern — `get_X_or_404` helper, list/detail/new/edit/delete routes, form data read via `request.form.get(..., type=...)`, validation errors re-render the same template with an `error` string and a 400 status. New feature areas should follow this shape rather than introducing a different pattern (e.g. class-based views, blueprints-per-file naming aside).

**Templates**: `templates/base.html` is the shared shell (sidebar nav, footer); each feature has its own subdirectory (`templates/vehicles/`, `templates/chores/`, `templates/expenses/`). URLs are hardcoded strings in both routes and templates (no `url_for`) — this is intentional for simplicity, keep it consistent when adding routes. Jinja custom filters (`number`, `currency`) are defined in `rendering.py` and registered onto `app.jinja_env.filters` in `main.py`.

**Expenses / receipt scanning** (`receipts.py` + `routes/expenses.py` + `models.py: Expense`/`ExpenseItem`): the extraction logic is isolated in `receipts.py` (`extract_receipt_data`) so it stays separate from the Flask route. The user picks the analysis method per upload via a radio button on `templates/expenses/add_expense.html` (`method` form field, "anthropic" or "ocr"):
- `anthropic` (default): sends the receipt to `claude-sonnet-5` with `output_config.format` (structured JSON schema output) to get vendor/amount/date/category plus a per-line-item breakdown (each item can have its own category, since one receipt can span multiple categories). Photos go as an `image` content block; PDFs go as a `document` content block instead (same base64 encoding either way — `media_type` decides which). Without `ANTHROPIC_API_KEY` set, this returns all-`None` fields gracefully rather than failing. API failures and malformed/truncated JSON responses are also caught and fall back to blank fields — don't let a bad external API response 500 the upload.
- `ocr` (free): `extract_receipt_data_ocr` runs local OCR via `pytesseract` (requires the `tesseract-ocr` system binary, see "Running locally" above) and regex-parses just the amount and date; vendor is a best-effort guess (first line of OCR text), category and line items are always left blank for manual entry since OCR text is too unstructured to parse those reliably. PDFs are rendered to an image first via `pdf2image` (requires the `poppler-utils` system package) — only the first page is OCR'd.

Receipt files are never shown inline in the UI (they can be large/numerous, and PDFs can't be `<img>`-embedded anyway) — `templates/expenses/detail.html` links to `/expenses/<id>/receipt` (`routes/expenses.py: expense_receipt`, served via `send_from_directory`) which opens in a new tab instead.

HEIC photos (default iPhone format) aren't accepted by Claude's vision API — `receipts.py: convert_heic_to_jpeg` converts them via `pillow-heif` before both the API call and disk storage, so stored receipts are always browser-viewable JPEGs regardless of source format. PDFs are stored and sent as-is (no conversion needed).

**Vehicles** (`models.py: Vehicle`/`MaintenanceRecord`/`MaintenanceReminder`): reminders are classified as `overdue` / `due_soon` / `ok` based on `REMINDER_DUE_SOON_DAYS` and `REMINDER_DUE_SOON_MILES` thresholds in `config.py`, computed in `routes/dashboard.py: _reminder_status` and reused by `routes/vehicles.py`. `MaintenanceReminder.last_service_date` is informational only (not used in the overdue/due-soon calculation, which is purely forward-looking off `due_date`/`due_mileage`) — it's just displayed so the user can see when the service was last done.

**Chores** (`models.py: Chore`/`ChoreLog`): recurrence is frequency-based (`CHORE_FREQUENCIES` maps a frequency string to an interval in days), with `next_due()`/`status()` computed as model methods on `Chore` rather than stored.
