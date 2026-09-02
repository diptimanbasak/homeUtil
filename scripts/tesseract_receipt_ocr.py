import cv2
import pytesseract
import re
import numpy as np
from pdf2image import convert_from_path

# ==========================================
# Category Keywords
# ==========================================
CATEGORIES = {
    "Grocery": ["milk", "bread", "egg", "cheese", "apple", "banana", "chicken", "beef", "water", "soda", "cereal", "produce", "butter"],
    "Medical": ["pharma", "rx", "pill", "tablet", "aspirin", "ibuprofen", "clinic", "health", "vitamin", "med"],
    "Auto": ["oil", "gas", "fuel", "tire", "brake", "wiper", "fluid", "wash", "unleaded", "service"],
    "Dining": ["burger", "pizza", "coffee", "latte", "cafe", "restaurant", "grill", "pasta", "taco", "fries", "drink"],
    "Shopping": ["shirt", "jeans", "shoes", "socks", "jacket", "book", "toy", "gift", "electronics", "home", "apparel"]
}

# A "price line" is the 2nd line of an item pair, e.g.:
#   2 @ $1.99ea.2/$3.00  F  $3.00
#   2.40 lb @ $4.99/lb   F  $11.98
#   1.22 lb @ $3.99/lb   F  $4.87
#   3 @ $1.99ea.         F  $5.97
#   1.61 lb @ $2.49/lb   F  $4.01
#   0.49 lb @ $3.99/lb   F  $1.96
# Identified by an "@" (qty/weight @ unit rate) followed somewhere by a
# trailing dollar amount, which is the line total we want -- everything
# else on the line (qty/weight, per-unit/per-lb rate, the "F" tax-status
# flag) is discarded. Tesseract frequently reads "$" as "S", so both are
# accepted. Item names never contain "@", so this can't false-match a
# name-only line.
PRICE_LINE_PATTERN = re.compile(r'@.*?[\$S]\s*(\d+[.,]\d{2})\s*$', re.IGNORECASE)

# Fallback: single-line "item ... price" layout (no "@"), for receipts that
# don't split item/price across two lines.
SINGLE_LINE_PATTERN = re.compile(r'^([A-Za-z][A-Za-z0-9\s\-\.]*?)\s+[\$S]\s*(\d+[.,]\d{2})\s*$')

# A price-only line (no item text, no "@") -- pairs with the item name on
# the line before it, e.g. "SWAD CHANA DAL 4LB F" followed by "$8.99".
PRICE_ONLY_PATTERN = re.compile(r'^[\$S]\s*(\d+[.,]\d{2})\s*$')

IGNORE_KEYWORDS = ['total', 'subtotal', 'tax', 'cash', 'change', 'visa', 'mastercard', 'balance', 'master']

# Strips a trailing tax-status flag letter (e.g. "F") that tesseract picks
# up as part of the item name when it sits at the end of a name line, e.g.
# "SWAD CHANA DAL 4LB F" -> "SWAD CHANA DAL 4LB".
_TRAILING_FLAG_RE = re.compile(r'\s+[A-Z]$')


def _clean_item_name(name):
    return _TRAILING_FLAG_RE.sub('', name).strip()


def categorize_item(item_name):
    item_lower = item_name.lower()
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in item_lower:
                return category
    return "Shopping"


def load_and_preprocess(file_path):
    """
    Loads a file (PDF or Image) and prepares it for Tesseract OCR.
    """
    if file_path.lower().endswith('.pdf'):
        pages = convert_from_path(file_path, first_page=1, last_page=1)
        if not pages:
            raise ValueError("Could not convert PDF page.")
        open_cv_image = np.array(pages[0])
        img = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
    else:
        img = cv2.imread(file_path)

    if img is None:
        raise FileNotFoundError(f"Could not load or find the file at: {file_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    return thresh


def parse_items_from_text(raw_text):
    """Pairs up two-line item/price entries (and single-line ones) from
    already-OCR'd receipt text. Split out from process_receipt() so callers
    that already have OCR text (e.g. receipts.py's OCR path) can reuse the
    parsing without re-running tesseract or the cv2 preprocessing here."""
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    extracted_items = []
    pending_item_name = None

    for line in lines:
        price_match = PRICE_LINE_PATTERN.search(line)
        if price_match:
            # This line is qty/weight/rate info for the item named on the
            # previous line, not an item itself.
            if pending_item_name:
                item_name = _clean_item_name(pending_item_name)
                price = price_match.group(1).replace(',', '.')
                if not any(k in item_name.lower() for k in IGNORE_KEYWORDS):
                    extracted_items.append({
                        "Item": item_name,
                        "Price": f"${price}",
                        "Category": categorize_item(item_name),
                    })
            pending_item_name = None
            continue

        single_match = SINGLE_LINE_PATTERN.search(line)
        if single_match:
            item_name = _clean_item_name(single_match.group(1))
            price = single_match.group(2).replace(',', '.')
            if not any(k in item_name.lower() for k in IGNORE_KEYWORDS):
                extracted_items.append({
                    "Item": item_name,
                    "Price": f"${price}",
                    "Category": categorize_item(item_name),
                })
            pending_item_name = None
            continue

        price_only_match = PRICE_ONLY_PATTERN.match(line)
        if price_only_match:
            if pending_item_name:
                item_name = _clean_item_name(pending_item_name)
                price = price_only_match.group(1).replace(',', '.')
                if not any(k in item_name.lower() for k in IGNORE_KEYWORDS):
                    extracted_items.append({
                        "Item": item_name,
                        "Price": f"${price}",
                        "Category": categorize_item(item_name),
                    })
            pending_item_name = None
            continue

        # No price on this line -- it's a candidate item name, held until
        # we see whether the next line is its price/weight line.
        if not any(k in line.lower() for k in IGNORE_KEYWORDS):
            pending_item_name = line

    return extracted_items


def process_receipt(file_path):
    processed_img = load_and_preprocess(file_path)

    custom_config = r'--psm 6'
    raw_text = pytesseract.image_to_string(processed_img, config=custom_config)

    return parse_items_from_text(raw_text)


if __name__ == "__main__":
    file_path = "receipt.pdf"

    try:
        items = process_receipt(file_path)

        print("\n--- Extracted & Categorized Items ---")
        if items:
            print(f"{'ITEM':<25} {'PRICE':<10} {'CATEGORY'}")
            print("-" * 50)
            for item in items:
                print(f"{item['Item']:<25} {item['Price']:<10} {item['Category']}")
        else:
            print("No items found.")

    except Exception as e:
        print(f"An error occurred: {e}")
