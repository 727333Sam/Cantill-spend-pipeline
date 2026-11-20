import re
from hashlib import sha1

from .normalize import clean_text


def canonical_supplier(value: object) -> str:
    text = clean_text(value).upper()
    text = re.sub(r"\b(PTY\s+LTD|PTY|LIMITED|LTD|INC|LLC|SA|CORP|CORPORATION)\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def supplier_key(supplier_id: object = "", supplier_name: object = "") -> str:
    supplier_id = clean_text(supplier_id)
    if supplier_id:
        return f"vendor:{supplier_id.lower()}"
    canonical = canonical_supplier(supplier_name)
    if not canonical:
        return "supplier:unknown"
    digest = sha1(canonical.encode("utf-8")).hexdigest()[:12]
    return f"supplier:{digest}"


def canonical_item(value: object) -> str:
    text = clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\b(PART|ITEM|QTY|PCS|EA)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def item_key(material_id: object = "", description: object = "") -> str:
    material_id = clean_text(material_id)
    if material_id:
        return f"item:{material_id.lower()}"
    canonical = canonical_item(description)
    if not canonical:
        return "item:unknown"
    digest = sha1(canonical.encode("utf-8")).hexdigest()[:12]
    return f"item:{digest}"
