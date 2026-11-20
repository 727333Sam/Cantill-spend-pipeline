from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable
from difflib import SequenceMatcher

import pandas as pd

from .classify import RuntimeTaxonomyClassifier
from .deduplicate import canonical_supplier, item_key, supplier_key
from .io import read_csv
from .normalize import (
    clean_text,
    extract_po,
    normalize_invoice_number,
    normalize_po_item,
    parse_amount,
    parse_date,
    parse_vat,
)

OUTPUT_COLUMNS = [
    "record_id", "include", "exclusion_reason", "supplier_key", "item_key",
    "spend", "l1", "l2", "l3", "l4", "confidence",
]


def lookup_fx_rate(
    fx: pd.DataFrame,
    config: dict,
    currency: str,
    invoice_month: str,
) -> tuple[float, str]:
    currency_column = config["fx"]["currency"]
    month_column = config["fx"]["month"]
    rate_column = config["fx"]["units_per_usd"]
    candidates = fx[fx[currency_column].map(clean_text).str.upper() == currency.upper()].copy()
    candidates["_rate"] = pd.to_numeric(candidates[rate_column], errors="coerce")
    candidates["_period"] = pd.PeriodIndex(candidates[month_column].map(clean_text), freq="M")
    candidates = candidates[candidates["_rate"].notna() & (candidates["_rate"] > 0)]
    if candidates.empty:
        raise ValueError(f"No valid FX rate exists for {currency} in the supplied FX dataset")

    exact = candidates[candidates["_period"] == pd.Period(invoice_month, freq="M")]
    if not exact.empty:
        return float(exact.iloc[0]["_rate"]), invoice_month

    target = pd.Period(invoice_month, freq="M")
    candidates["_distance"] = candidates["_period"].map(
        lambda period: abs(period.ordinal - target.ordinal)
    )
    nearest = candidates.sort_values(["_distance", "_period"]).iloc[0]
    return float(nearest["_rate"]), str(nearest[month_column])


def is_cancelled(status: object) -> bool:
    return clean_text(status).lower() in {"cancelled", "canceled", "void", "voided"}


def is_not_approved(status: object) -> bool:
    value = clean_text(status).lower()
    return value in {"rejected", "on hold", "hold", "submitted", "disputed", "pending"}


def non_procurement(row: dict, gl_column: str = "", description_column: str = "") -> bool:
    gl = clean_text(row.get(gl_column, "")).lower()
    desc = clean_text(row.get(description_column, "")).lower()
    document = clean_text(row.get("document_type", "")).lower()
    text = f"{gl} {desc}"
    keywords = [
        "intercompany", "inter company", "i/c", "ic pay", "ic06", "ic05",
        "sales tax", "tax expense", "tax payable", "revenue", "royalty",
        "partner billing", "financing", "finance cost", "interest", "fx ",
    ]
    if any(keyword in text for keyword in keywords):
        return True
    if document in {"CA", "CN"}:
        return True
    return False


def taxonomy_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].fillna("").copy()


def prepare_categories(taxonomy_columns: list[str], parts: list[str]) -> dict[str, str]:
    return {f"l{i + 1}": (parts[i] if i < len(parts) else "") for i in range(4)}


def write_outputs(rows: Iterable[dict], output: str | Path) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=OUTPUT_COLUMNS)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def build_a(kit: str | Path, config: dict) -> tuple[pd.DataFrame, list[dict]]:
    erp = read_csv(kit, config["erp"]["file"])
    tool = read_csv(kit, config["tool"]["file"])
    labels = read_csv(kit, config["labels"]["file"])
    taxonomy = read_csv(kit, config["taxonomy"]["file"])
    label_columns = config["taxonomy"]["columns"]
    label_map = {}
    prefix = config["labels"]["erp_prefix"]
    for _, row in labels.iterrows():
        rid = clean_text(row[config["labels"]["id"]])
        if rid.startswith(prefix):
            rid = rid[len(prefix):]
        label_map[rid] = row

    erp["id"] = erp[config["erp"]["id"]].map(clean_text)
    supplier_keys = []
    item_keys = []
    for _, row in erp.iterrows():
        rid = clean_text(row["id"])
        if rid in label_map:
            supplier_key_value = clean_text(label_map[rid][config["labels"]["supplier_key"]])
            item_key_value = clean_text(label_map[rid][config["labels"]["item_key"]])
            supplier_keys.append(supplier_key_value or supplier_key(
                row.get(config["erp"].get("supplier_id", ""), ""),
                row.get(config["erp"].get("supplier", ""), ""),
            ))
            item_keys.append(item_key_value or item_key(
                row.get("material_number", ""),
                row.get(config["erp"]["description"], ""),
            ))
        else:
            supplier_keys.append(supplier_key(
                row.get(config["erp"].get("supplier_id", ""), ""),
                row.get(config["erp"].get("supplier", ""), ""),
            ))
            item_keys.append(item_key(
                row.get("material_number", ""),
                row.get(config["erp"]["description"], ""),
            ))
    erp["_supplier_key"] = supplier_keys
    erp["_item_key"] = item_keys

    training = []
    for _, row in erp.iterrows():
        rid = row["id"]
        if rid in label_map:
            lr = label_map[rid]
            training.append({
                "_text": clean_text(row[config["erp"]["description"]]) + " " + clean_text(row.get(config["erp"].get("service_description", ""), "")),
                **{column: clean_text(lr[column]) for column in label_columns},
            })
    train_frame = pd.DataFrame(training)

    classifier = RuntimeTaxonomyClassifier(taxonomy, label_columns)
    classifier.build_taxonomy_fallback()
    if not train_frame.empty:
        classifier.fit(train_frame.rename(columns={"_text": "_description"}), "_description")

    erp_lookup: dict[tuple[str, str], list[int]] = {}
    for index, row in erp.iterrows():
        po = extract_po(row[config["erp"]["po_number"]])
        item = normalize_po_item(row[config["erp"]["po_item"]])
        erp_lookup.setdefault((po, item), []).append(index)

    tool_rows = tool.to_dict("records")
    net_tool_keys: dict[str, list[dict]] = {}
    audit = []
    rows = []
    tool_duplicate_ids = set()
    seen_tool_keys = set()

    for row in tool_rows:
        invoice = normalize_invoice_number(row[config["tool"]["invoice_number"]])
        amount, amount_error = parse_amount(row[config["tool"]["amount"]])
        vat = parse_vat(row[config["tool"]["vat_rate"]], float(config["tool"]["default_vat_rate"]))
        net = (amount / (1.0 + vat)) if amount is not None else None
        key = f"{invoice}|{round(net or 0.0, 2)}|{clean_text(row[config['tool']['description']]).lower()}"
        net_tool_keys.setdefault(key, []).append(row)
        if key in seen_tool_keys:
            tool_duplicate_ids.add(str(row[config["tool"]["id"]]))
        else:
            seen_tool_keys.add(key)

    for row in tool_rows:
        rid = clean_text(row[config["tool"]["id"]])
        record_id = f"TOOL:{rid}"
        status = clean_text(row[config["tool"]["status"]])
        amount, amount_error = parse_amount(row[config["tool"]["amount"]])
        vat = parse_vat(row[config["tool"]["vat_rate"]], float(config["tool"]["default_vat_rate"]))
        net = (amount / (1.0 + vat)) if amount is not None else None
        invoice_date, date_error = parse_date(row[config["tool"]["date"]])
        supplier = clean_text(row[config["tool"]["supplier"]])

        include = 1
        reason = ""
        matched_erp = None
        if is_cancelled(status):
            include, reason = 0, "CANCELLED"
        elif is_not_approved(status):
            include, reason = 0, "NOT_APPROVED"
        elif rid in tool_duplicate_ids:
            include, reason = 0, "DUPLICATE"
        else:
            po = extract_po(row[config["tool"]["po_number"]])
            item = normalize_po_item(row[config["tool"]["po_number"]].split("/")[-1] if "/" in row[config["tool"]["po_number"]] else "")
            candidates = erp_lookup.get((po, item), [])
            if not candidates and po:
                candidates = [i for (p, _), indexes in erp_lookup.items() if p == po for i in indexes]
            best = None
            best_distance = 1e9
            tool_supplier = canonical_supplier(supplier)
            for idx in candidates:
                erp_row = erp.loc[idx]
                erp_amount, _ = parse_amount(erp_row[config["erp"]["amount"]])
                if erp_amount is not None and net is not None:
                    distance = abs(abs(erp_amount) - abs(net)) / max(abs(erp_amount), 1.0)
                    erp_supplier = canonical_supplier(erp_row.get(config["erp"]["supplier"], ""))
                    if tool_supplier and erp_supplier and tool_supplier != erp_supplier:
                        supplier_similarity = SequenceMatcher(None, tool_supplier, erp_supplier).ratio()
                        if supplier_similarity < 0.55:
                            continue
                    if distance < best_distance:
                        best_distance, best = distance, idx
            if best is not None and best_distance <= 0.08:
                matched_erp = erp.loc[best]
                include, reason = 0, "DUPLICATE"

        if include:
            sk = matched_erp["_supplier_key"] if matched_erp is not None else supplier_key(supplier_name=supplier)
            ik = matched_erp["_item_key"] if matched_erp is not None else item_key(description=row[config["tool"]["description"]])
            spend = net if net is not None else 0.0
            text = clean_text(row[config["tool"]["description"]])
            parts, confidence = classifier.predict(text)
        else:
            sk = matched_erp["_supplier_key"] if matched_erp is not None else supplier_key(supplier_name=supplier)
            ik = matched_erp["_item_key"] if matched_erp is not None else item_key(description=row[config["tool"]["description"]])
            spend = 0.0
            parts = [""] * 4
            confidence = 0.95 if reason == "DUPLICATE" else 0.9
        output = {
            "record_id": record_id, "include": include, "exclusion_reason": reason,
            "supplier_key": sk, "item_key": ik, "spend": round(spend, 2),
            "l1": parts[0], "l2": parts[1], "l3": parts[2], "l4": parts[3],
            "confidence": round(confidence, 4),
        }
        audit.append({"record_id": record_id, "reason": reason, "date_error": date_error, "amount_error": amount_error,
                      "vat_rate": round(vat, 6), "net_amount": net})
        rows.append(output)

    for _, erp_row in erp.iterrows():
        rid = clean_text(erp_row["id"])
        record_id = f"ERP:{rid}"
        amount, amount_error = parse_amount(erp_row[config["erp"]["amount"]])
        date_value, date_error = parse_date(erp_row[config["erp"]["date"]])
        text = clean_text(erp_row[config["erp"]["description"]]) + " " + clean_text(erp_row.get(config["erp"].get("service_description", ""), ""))
        parts, confidence = classifier.predict(text)
        output = {
            "record_id": record_id, "include": 1, "exclusion_reason": "",
            "supplier_key": erp_row["_supplier_key"], "item_key": erp_row["_item_key"],
            "spend": round(amount or 0.0, 2), "l1": parts[0], "l2": parts[1], "l3": parts[2],
            "l4": parts[3], "confidence": round(confidence, 4),
        }
        audit.append({"record_id": record_id, "date_error": date_error, "amount_error": amount_error})
        rows.append(output)

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS), audit


def build_b(kit: str | Path, config: dict) -> tuple[pd.DataFrame, list[dict]]:
    invoice = read_csv(kit, config["invoice"]["file"])
    taxonomy = read_csv(kit, config["taxonomy"]["file"])
    label_columns = config["taxonomy"]["columns"]

    fx = None
    if "fx" in config:
        fx = read_csv(kit, config["fx"]["file"])
        fx["_month"] = fx[config["fx"]["month"]].map(clean_text)

    seed = pd.DataFrame()
    seed_excluded_ids = set()
    if "seed_labels" in config:
        seed = read_csv(kit, config["seed_labels"]["file"])
        seed_excluded_ids = set(
            seed.loc[
                seed[config["seed_labels"]["include"]].map(clean_text) == "0",
                config["seed_labels"]["id"],
            ].map(clean_text)
        )

    classifier = RuntimeTaxonomyClassifier(taxonomy, label_columns)
    classifier.build_taxonomy_fallback()
    training = seed.copy()
    if not training.empty:
        by_id = invoice.set_index(config["invoice"]["id"])
        training["_text"] = training[config["seed_labels"]["id"]].map(
            lambda rid: clean_text(by_id.loc[rid, config["invoice"]["description"]]) if rid in by_id.index else ""
        )
        included = training[training[config["seed_labels"]["include"]] == "1"]
        if not included.empty:
            classifier.fit(included.rename(columns={"_text": "_description"}), "_description")

    rows = []
    audit = []
    for _, row in invoice.iterrows():
        rid = clean_text(row[config["invoice"]["id"]])
        amount, amount_error = parse_amount(row[config["invoice"]["amount"]])
        date_value, date_error = parse_date(row[config["invoice"]["date"]])
        currency = clean_text(row[config["invoice"]["currency"]]).upper()
        gl_column = config["invoice"].get("gl_account_description", "")
        desc_column = config["invoice"].get("description", "")
        exclude = False
        reason = ""
        if rid in seed_excluded_ids:
            exclude, reason = True, "NON_PROCUREMENT"
        elif non_procurement({
            gl_column: row.get(gl_column, ""),
            desc_column: row.get(desc_column, ""),
            "document_type": row.get(config["invoice"].get("document_type", ""), ""),
        }, gl_column, desc_column):
            exclude, reason = True, "NON_PROCUREMENT"

        spend = amount
        fx_error = None
        fx_source_month = None
        if not exclude and spend is not None and currency and currency != "USD":
            explicit = clean_text(row.get(config["invoice"].get("currency_rate", ""), ""))
            rate = None
            if explicit:
                try:
                    parsed_rate = float(explicit)
                    if parsed_rate > 0:
                        rate = parsed_rate
                        fx_source_month = "row_currency_rate"
                except ValueError:
                    rate = None
            if rate is None:
                if fx is None or date_value is None:
                    raise ValueError(
                        f"Cannot convert included {rid}: no invoice month or FX dataset is available"
                    )
                rate, fx_source_month = lookup_fx_rate(
                    fx, config, currency, date_value.strftime("%Y-%m")
                )
            spend = spend / rate

        if not exclude:
            include = 1
            text = " ".join(filter(None, [
                clean_text(row.get(desc_column, "")),
                clean_text(row.get(config["invoice"].get("material_id", ""), "")),
                clean_text(row.get(gl_column, "")),
                clean_text(row.get(config["invoice"].get("supplier_id", ""), "")),
            ]))
            parts, confidence = classifier.predict(text)
            net_spend = spend if spend is not None and fx_error is None else 0.0
        else:
            include = 0
            parts = [""] * 4
            confidence = 0.95
            net_spend = 0.0

        rows.append({
            "record_id": rid, "include": include, "exclusion_reason": reason,
            "supplier_key": supplier_key(row.get(config["invoice"].get("supplier_id", ""), ""), row.get(config["invoice"].get("supplier", ""), "")),
            "item_key": item_key(row.get(config["invoice"].get("material_id", ""), ""), row.get(desc_column, "")),
            "spend": round(net_spend, 2),
            "l1": parts[0], "l2": parts[1], "l3": parts[2], "l4": parts[3],
            "confidence": round(confidence, 4),
        })
        audit.append({"record_id": rid, "date_error": date_error, "amount_error": amount_error,
                      "fx_error": fx_error, "fx_source_month": fx_source_month,
                      "currency": currency, "net_amount": net_spend})
    return pd.DataFrame(rows), audit


def build_generic(kit: str | Path, config: dict) -> tuple[pd.DataFrame, list[dict]]:
    invoice = read_csv(kit, config["invoice"]["file"])
    taxonomy = read_csv(kit, config["taxonomy"]["file"])
    label_columns = config["taxonomy"]["columns"]
    fx = None
    if "fx" in config:
        fx = read_csv(kit, config["fx"]["file"])
    classifier = RuntimeTaxonomyClassifier(taxonomy, label_columns)
    classifier.build_taxonomy_fallback()

    rows = []
    audit = []
    for _, row in invoice.iterrows():
        rid = clean_text(row[config["invoice"]["id"]])
        amount, amount_error = parse_amount(row[config["invoice"]["amount"]])
        date_value, date_error = parse_date(row[config["invoice"]["date"]])
        status = clean_text(row.get(config["invoice"].get("status", ""), ""))
        text = " ".join(filter(None, [
            clean_text(row.get(config["invoice"]["description"], "")),
            clean_text(row.get(config["invoice"].get("material_id", ""), "")),
            clean_text(row.get(config["invoice"].get("gl_account_description", ""), "")),
            clean_text(row.get(config["invoice"].get("supplier_id", ""), "")),
        ]))
        gl_column = config["invoice"].get("gl_account_description", "")
        desc_column = config["invoice"].get("description", "")
        exclude_reason = ""
        if is_cancelled(status):
            exclude_reason = "CANCELLED"
        elif is_not_approved(status):
            exclude_reason = "NOT_APPROVED"
        elif non_procurement({
            gl_column: row.get(gl_column, ""),
            desc_column: row.get(desc_column, ""),
            "document_type": row.get(config["invoice"].get("document_type", ""), ""),
        }, gl_column, desc_column):
            exclude_reason = "NON_PROCUREMENT"

        currency = clean_text(row[config["invoice"]["currency"]]).upper()
        spend = amount
        fx_error = None
        if spend is not None and currency and currency != "USD":
            explicit = clean_text(row.get(config["invoice"].get("currency_rate", ""), ""))
            rate = None
            if explicit:
                try:
                    rate = float(explicit)
                except ValueError:
                    rate = None
            if rate is None and fx is not None and date_value is not None:
                month = date_value.strftime("%Y-%m")
                match = fx[(fx[config["fx"]["currency"]] == currency) & (fx[config["fx"]["month"]] == month)]
                if not match.empty:
                    try:
                        rate = float(match.iloc[0][config["fx"]["units_per_usd"]])
                    except ValueError:
                        rate = None
            if rate is not None and rate != 0:
                spend = spend / rate
            else:
                fx_error = "FX_RATE_NOT_FOUND"

        if not exclude_reason:
            parts, confidence = classifier.predict(text)
            net_spend = spend if spend is not None and fx_error is None else 0.0
            include = 1
            if fx_error:
                net_spend = 0.0
        else:
            parts = [""] * 4
            confidence = 0.9
            net_spend = 0.0
            include = 0

        rows.append({
            "record_id": rid, "include": include, "exclusion_reason": exclude_reason,
            "supplier_key": supplier_key(row.get(config["invoice"].get("supplier_id", ""), ""), row.get(config["invoice"].get("supplier", ""), "")),
            "item_key": item_key(row.get(config["invoice"].get("material_id", ""), ""), text),
            "spend": round(net_spend, 2),
            "l1": parts[0], "l2": parts[1], "l3": parts[2], "l4": parts[3],
            "confidence": round(confidence, 4),
        })
        audit.append({"record_id": rid, "date_error": date_error, "amount_error": amount_error,
                      "fx_error": fx_error, "net_amount": net_spend})
    return pd.DataFrame(rows), audit


def run_pipeline(kit: str | Path, config: dict) -> tuple[pd.DataFrame, list[dict]]:
    company = str(config["company"]).upper()
    if company == "A":
        return build_a(kit, config)
    if company == "B":
        return build_b(kit, config)
    return build_generic(kit, config)
