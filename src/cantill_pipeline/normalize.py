import re
from datetime import datetime

import pandas as pd


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_amount(value: object) -> tuple[float | None, str | None]:
    text = clean_text(value)
    if not text:
        return None, "BLANK_AMOUNT"
    text = text.strip()
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^\d,.\-()]", "", text)
    text = text.replace("(", "").replace(")", "")
    if "," in text and "." not in text:
        text = text.replace(",", "")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    try:
        amount = float(text)
        if negative:
            amount = -abs(amount)
        return amount, None
    except ValueError:
        return None, "INVALID_AMOUNT"


def parse_vat(value: object, default: float) -> float:
    text = clean_text(value).strip().replace("%", "")
    if not text:
        return default
    try:
        rate = float(text.replace(",", "."))
        return rate / 100.0 if rate > 1 else rate
    except ValueError:
        return default


def parse_date(value: object) -> tuple[pd.Timestamp | None, str | None]:
    text = clean_text(value)
    if not text:
        return None, "BLANK_DATE"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).__class__ and pd.to_datetime(datetime.strptime(text, fmt)), None
        except (ValueError, TypeError):
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        return parsed, None
    except (ValueError, TypeError, OverflowError):
        return None, "INVALID_DATE"


def normalize_invoice_number(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean_text(value).upper())


def extract_po(value: object) -> str:
    text = clean_text(value)
    matches = re.findall(r"\d+", text)
    if not matches:
        return ""
    return max(matches, key=len)


def normalize_po_item(value: object) -> str:
    text = clean_text(value)
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return ""
    return str(float(match.group(0).replace(",", "."))).replace(".0", "")
