HomeUtil -- Mac Setup & Quick Start
====================================

This file covers running a STANDALONE local copy of HomeUtil on a Mac --
e.g. to quickly try it out, or test something fully offline.

For actual development, don't use this -- the home server (towmater) is
now the primary dev environment. Connect to it via VSCode Remote-SSH and
edit the live dev copy at /winix/homeutil-dev directly; see README.md's
"Where the code lives" section and CLAUDE.md for the full setup. This
file's standalone-Mac setup is a separate, disconnected copy with its
own local data/ -- it won't see your real expenses/vehicles/chores, and
changes here don't sync anywhere.


QUICK START (one command)
--------------------------

From the project root:

    ./deploy/setup_mac.sh

This will (safely, and it's fine to re-run any time):
  1. Check for Homebrew (tells you to install it from https://brew.sh
     if it's missing -- this script won't install Homebrew itself).
  2. Install system packages via brew if not already present:
       - python3
       - tesseract   (needed for the free/OCR receipt-scanning option)
       - poppler     (needed for scanning PDF receipts)
  3. Create a Python virtualenv at .venv/ if one doesn't exist yet.
  4. Install/update everything in requirements.txt into that venv.
  5. Create the data/ and data/receipts/ folders.
  6. Warn you if ANTHROPIC_API_KEY isn't set (see below).
  7. Start the app in the foreground: python main.py

Once it's running, open:

    http://localhost:8000


SETUP ONLY, DON'T START THE SERVER (for a dev machine)
-------------------------------------------------------

If you're setting up a second Macbook for development and want to run
the app yourself (e.g. from your editor, or with a debugger attached)
instead of letting the script launch it:

    ./deploy/setup_mac.sh --setup-only

Then start it yourself whenever you want:

    source .venv/bin/activate
    python main.py


CHANGING THE PORT
------------------

    PORT=9000 ./deploy/setup_mac.sh


ENABLING RECEIPT SCANNING VIA THE CLAUDE API
----------------------------------------------

Receipt scanning works two ways (chosen per-upload on the Scan Receipt
page):
  - "Claude API" (accurate) -- needs an Anthropic API key.
  - "Free (local OCR)" -- no key needed, uses tesseract locally, less
    accurate (vendor/amount/date only, no category or line items).

To enable the Claude API option, export your key before running the
script (or before running `python main.py` yourself), e.g. add this to
~/.zshrc:

    export ANTHROPIC_API_KEY="sk-ant-..."

Without it, receipt uploads still work -- vendor/amount/date/category
just come back blank for you to fill in by hand, same as the OCR path.


WHERE YOUR DATA LIVES
-----------------------

- Database: data/homeutil.db (SQLite -- a single file)
- Uploaded receipt photos/PDFs: data/receipts/

Both are gitignored and excluded from the Ubuntu deploy script's
rsync, so they're safe local/server-side state -- back them up
yourself if you care about them (e.g. copy the data/ folder).


TROUBLESHOOTING
-----------------

"Homebrew is required but not installed"
    Install it from https://brew.sh, then re-run ./deploy/setup_mac.sh

App starts but a page 500s after you've pulled newer code
    A model field may have been added that needs a matching database
    column. The app checks for this at startup (see
    database.py: check_schema_is_current()) and will refuse to start
    with a message telling you exactly which `ALTER TABLE ...` to run
    against data/homeutil.db. Run that, then start the app again.

Receipt scanning (Free/OCR option) doesn't work
    Make sure tesseract is installed: brew list tesseract
    If missing: brew install tesseract

PDF receipts don't scan
    Make sure poppler is installed: brew list poppler
    If missing: brew install poppler


SEE ALSO
---------

- README.md    -- feature overview, config reference, Ubuntu deploy steps
- CLAUDE.md    -- codebase architecture notes (for AI-assisted development)
