"""
Receipt analysis: extracts vendor, amount, date, and category from a
receipt photo, either via the Claude API (accurate, costs API usage) or
local OCR (free, less accurate -- requires the `tesseract-ocr` system
package to be installed; see deploy/install.sh).
"""
import base64
import io
import json
import re

import anthropic
import pdf2image
import pillow_heif
import pytesseract
from PIL import Image

from config import ANTHROPIC_API_KEY
from models import EXPENSE_CATEGORIES

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": ["string", "null"]},
        "amount": {"type": ["number", "null"], "description": "Total amount paid"},
        "expense_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "category": {
            "anyOf": [
                {"type": "string", "enum": EXPENSE_CATEGORIES},
                {"type": "null"},
            ]
        },
        "line_items": {
            "type": "array",
            "description": "Each individual item purchased, with its price",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": ["number", "null"]},
                    "category": {
                        "anyOf": [
                            {"type": "string", "enum": EXPENSE_CATEGORIES},
                            {"type": "null"},
                        ]
                    },
                },
                "required": ["name", "price", "category"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["vendor", "amount", "expense_date", "category", "line_items"],
    "additionalProperties": False,
}


def convert_heic_to_jpeg(image_bytes: bytes) -> bytes:
    """iPhones save photos as HEIC, which Claude's vision API can't read. Convert to JPEG."""
    pillow_heif.register_heif_opener()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


EMPTY_RECEIPT = {"vendor": None, "amount": None, "expense_date": None, "category": None, "line_items": []}

_DATE_PATTERNS = [
    (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda m: f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"),
    (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", lambda m: f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"),
    (r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", lambda m: f"20{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"),
]
_AMOUNT_LINE_RE = re.compile(r"total\b(?!.*sub).*?\$?\s*(\d+\.\d{2})", re.IGNORECASE)
_ANY_AMOUNT_RE = re.compile(r"\$?\s*(\d+\.\d{2})\b")


def extract_receipt_data_ocr(image_bytes: bytes, media_type: str) -> dict:
    """Free fallback: local OCR text extraction with simple regex parsing.
    Much less reliable than the Claude API -- vendor/category/line items are
    left blank for manual entry, only amount and date are guessed at."""
    if media_type == "application/pdf":
        pages = pdf2image.convert_from_bytes(image_bytes, first_page=1, last_page=1)
        image = pages[0]
    else:
        image = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)

    expense_date = None
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            expense_date = fmt(match)
            break

    amount_match = _AMOUNT_LINE_RE.search(text)
    if not amount_match:
        amounts = [float(m) for m in _ANY_AMOUNT_RE.findall(text)]
        amount = max(amounts) if amounts else None
    else:
        amount = float(amount_match.group(1))

    vendor = next((line.strip() for line in text.splitlines() if line.strip()), None)

    return {**EMPTY_RECEIPT, "vendor": vendor, "amount": amount, "expense_date": expense_date}


def extract_receipt_data(image_bytes: bytes, media_type: str, method: str = "anthropic") -> dict:
    """Returns a dict with vendor/amount/expense_date/category, any of which may be None."""
    if method == "ocr":
        return extract_receipt_data_ocr(image_bytes, media_type)

    empty = EMPTY_RECEIPT
    if _client is None:
        return empty

    content_block_type = "document" if media_type == "application/pdf" else "image"
    try:
        response = _client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            output_config={"format": {"type": "json_schema", "schema": RECEIPT_SCHEMA}},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": content_block_type,
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
                        },
                    },
                    {"type": "text", "text": "Extract the vendor, total amount, date, overall expense category, and every individual line item from this receipt (name, price, and that item's own category -- items on one receipt can belong to different categories, e.g. a Target receipt might have both Groceries and Cleaning Supplies)."},
                ],
            }],
        )
    except anthropic.APIError as e:
        print(f"Receipt analysis failed, leaving fields blank: {e}")
        return empty

    if response.stop_reason == "refusal":
        print("Receipt analysis refused by Claude, leaving fields blank")
        return empty

    text = next((b.text for b in response.content if b.type == "text"), None)
    print(f"Receipt analysis response (stop_reason={response.stop_reason}): {text!r}")
    if not text:
        return empty

    try:
        return {**empty, **json.loads(text)}
    except json.JSONDecodeError as e:
        print(f"Receipt analysis returned malformed JSON, leaving fields blank: {e}")
        return empty
