import json
from pathlib import Path

import pandas as pd
import pytest

from cantill_pipeline.pipeline import (
    OUTPUT_COLUMNS,
    build_a,
    build_b,
    lookup_fx_rate,
    write_outputs,
)


def test_output_schema(tmp_path):
    output = tmp_path / "A.csv"
    frame = write_outputs([{
        "record_id": "ERP:1", "include": 1, "exclusion_reason": "",
        "supplier_key": "vendor:1", "item_key": "item:1", "spend": 10.0,
        "l1": "Mining", "l2": "", "l3": "", "l4": "", "confidence": 0.5,
    }], output)
    assert list(frame.columns) == OUTPUT_COLUMNS
    assert pd.read_csv(output, dtype=str).columns.tolist() == OUTPUT_COLUMNS


def test_configs_have_external_files():
    root = Path(__file__).resolve().parents[1]
    for name in ("company_a.json", "company_b.json", "company_c.example.json"):
        config = json.loads((root / "configs" / name).read_text(encoding="utf-8"))
        assert config["company"]
        assert config["taxonomy"]["columns"]


def test_a_repeated_tool_export_keeps_first_copy(tmp_path):
    (tmp_path / "company_A").mkdir()
    pd.DataFrame([{
        "line_id": "A1", "posting_date": "2024-01-01", "value_zar": "100",
        "document_currency": "ZAR", "supplier_name": "Supplier One",
        "vendor_id": "V1", "material_short_text": "Bolt", "service_short_text": "",
        "po_number": "PO-ERP", "po_item": "10",
    }]).to_csv(tmp_path / "company_A" / "erp.csv", index=False)
    pd.DataFrame([
        {"tool_record_id": "T1", "invoice_number": "INV-1", "invoice_date": "2024-01-01",
         "supplier_name_as_captured": "Different Supplier", "po_reference": "",
         "line_text": "Consulting", "gross_amount": "115", "vat_rate": "15%",
         "currency": "ZAR", "status": "Paid"},
        {"tool_record_id": "T2", "invoice_number": "INV-1", "invoice_date": "2024-01-01",
         "supplier_name_as_captured": "Different Supplier", "po_reference": "",
         "line_text": "Consulting", "gross_amount": "115", "vat_rate": "15%",
         "currency": "ZAR", "status": "Paid"},
    ]).to_csv(tmp_path / "company_A" / "tool.csv", index=False)
    pd.DataFrame([{
        "record_id": "ERP:A1", "category_l1": "MRO", "category_l2": "Hardware",
        "category_l3": "Bolts", "supplier_key": "SG-1", "item_key": "IG-1",
    }]).to_csv(tmp_path / "company_A" / "labels.csv", index=False)
    pd.DataFrame([{
        "category_l1": "MRO", "category_l2": "Hardware", "category_l3": "Bolts",
    }]).to_csv(tmp_path / "company_A" / "taxonomy.csv", index=False)
    config = {
        "company": "A", "erp": {"file": "company_A/erp.csv", "record_prefix": "ERP",
        "id": "line_id", "date": "posting_date", "amount": "value_zar",
        "currency": "document_currency", "supplier": "supplier_name", "supplier_id": "vendor_id",
        "description": "material_short_text", "service_description": "service_short_text",
        "po_number": "po_number", "po_item": "po_item"},
        "tool": {"file": "company_A/tool.csv", "record_prefix": "TOOL", "id": "tool_record_id",
        "date": "invoice_date", "amount": "gross_amount", "currency": "currency",
        "supplier": "supplier_name_as_captured", "description": "line_text",
        "po_number": "po_reference", "invoice_number": "invoice_number", "status": "status",
        "vat_rate": "vat_rate", "default_vat_rate": 0.15},
        "labels": {"file": "company_A/labels.csv", "id": "record_id", "erp_prefix": "ERP:",
        "supplier_key": "supplier_key", "item_key": "item_key"},
        "taxonomy": {"file": "company_A/taxonomy.csv", "columns": ["category_l1", "category_l2", "category_l3"]},
    }
    frame, _ = build_a(tmp_path, config)
    tool = frame[frame.record_id.str.startswith("TOOL:")].sort_values("record_id")
    assert tool.iloc[0].include == 1
    assert tool.iloc[1].exclusion_reason == "DUPLICATE"


def test_b_seed_exclusion_is_respected(tmp_path):
    (tmp_path / "company_B").mkdir()
    pd.DataFrame([{
        "line_id": "B1", "invoice_date": "2024-01-01", "line_amount": "10",
        "currency": "USD", "currency_rate": "", "vendor_id": "V1",
        "line_description": "Tax", "material_number": "M1",
        "gl_account_description": "Ordinary", "document_type": "PV",
    }]).to_csv(tmp_path / "company_B" / "invoice.csv", index=False)
    pd.DataFrame([{"line_id": "B1", "include": "0", "exclusion_reason": "NON_PROCUREMENT",
                   "category_l1": "", "category_l2": "", "category_l3": ""}]).to_csv(
        tmp_path / "company_B" / "seed.csv", index=False
    )
    pd.DataFrame([{"category_l1": "MRO", "category_l2": "Hardware", "category_l3": "Bolts"}]).to_csv(
        tmp_path / "company_B" / "taxonomy.csv", index=False
    )
    config = {
        "company": "B", "invoice": {"file": "company_B/invoice.csv", "id": "line_id",
        "date": "invoice_date", "amount": "line_amount", "currency": "currency",
        "currency_rate": "currency_rate", "supplier_id": "vendor_id",
        "description": "line_description", "material_id": "material_number",
        "gl_account_description": "gl_account_description", "document_type": "document_type"},
        "seed_labels": {"file": "company_B/seed.csv", "id": "line_id", "include": "include",
        "exclusion_reason": "exclusion_reason", "category_columns": ["category_l1", "category_l2", "category_l3"]},
        "taxonomy": {"file": "company_B/taxonomy.csv", "columns": ["category_l1", "category_l2", "category_l3"]},
    }
    frame, _ = build_b(tmp_path, config)
    assert frame.iloc[0].include == 0
    assert frame.iloc[0].exclusion_reason == "NON_PROCUREMENT"


def test_b_fx_conversion_rules_and_nearest_month_fallback():
    fx = pd.DataFrame([
        {"currency": "CAD", "month": "2022-12", "units_per_usd": "1.35"},
        {"currency": "EUR", "month": "2024-03", "units_per_usd": "2.0"},
    ])
    config = {"fx": {"currency": "currency", "month": "month", "units_per_usd": "units_per_usd"}}
    assert lookup_fx_rate(fx, config, "CAD", "2022-07") == (1.35, "2022-12")
    assert lookup_fx_rate(fx, config, "EUR", "2024-03") == (2.0, "2024-03")
    with pytest.raises(ValueError, match="No valid FX rate"):
        lookup_fx_rate(fx, config, "JPY", "2024-03")


def test_b_spend_preserves_usd_direct_rate_fallback_negative_and_excluded(tmp_path):
    (tmp_path / "company_B").mkdir()
    pd.DataFrame([
        {"line_id": "USD", "invoice_date": "2024-01-01", "line_amount": "10",
         "currency": "USD", "currency_rate": "", "vendor_id": "V1",
         "line_description": "Bolt", "material_number": "M1",
         "gl_account_description": "Ordinary", "document_type": "PV"},
        {"line_id": "DIRECT", "invoice_date": "2024-01-01", "line_amount": "-13.5",
         "currency": "CAD", "currency_rate": "1.35", "vendor_id": "V2",
         "line_description": "Bolt", "material_number": "M2",
         "gl_account_description": "Ordinary", "document_type": "PV"},
        {"line_id": "FALLBACK", "invoice_date": "2022-07-27", "line_amount": "-27",
         "currency": "CAD", "currency_rate": "", "vendor_id": "V3",
         "line_description": "Bolt", "material_number": "M3",
         "gl_account_description": "Ordinary", "document_type": "PV"},
        {"line_id": "EXCLUDED", "invoice_date": "2022-07-27", "line_amount": "99",
         "currency": "CAD", "currency_rate": "", "vendor_id": "V4",
         "line_description": "Tax", "material_number": "M4",
         "gl_account_description": "Ordinary", "document_type": "PV"},
    ]).to_csv(tmp_path / "company_B" / "invoice.csv", index=False)
    pd.DataFrame([{
        "line_id": "EXCLUDED", "include": "0", "exclusion_reason": "NON_PROCUREMENT",
        "category_l1": "", "category_l2": "", "category_l3": "",
    }]).to_csv(tmp_path / "company_B" / "seed.csv", index=False)
    pd.DataFrame([{"currency": "CAD", "month": "2022-12", "units_per_usd": "1.35"}]).to_csv(
        tmp_path / "company_B" / "fx.csv", index=False
    )
    pd.DataFrame([{"category_l1": "MRO", "category_l2": "Hardware", "category_l3": "Bolts"}]).to_csv(
        tmp_path / "company_B" / "taxonomy.csv", index=False
    )
    config = {
        "company": "B",
        "invoice": {
            "file": "company_B/invoice.csv", "id": "line_id", "date": "invoice_date",
            "amount": "line_amount", "currency": "currency", "currency_rate": "currency_rate",
            "supplier_id": "vendor_id", "description": "line_description",
            "material_id": "material_number", "gl_account_description": "gl_account_description",
            "document_type": "document_type",
        },
        "fx": {"file": "company_B/fx.csv", "currency": "currency", "month": "month",
               "units_per_usd": "units_per_usd"},
        "seed_labels": {"file": "company_B/seed.csv", "id": "line_id", "include": "include",
                        "exclusion_reason": "exclusion_reason"},
        "taxonomy": {"file": "company_B/taxonomy.csv",
                     "columns": ["category_l1", "category_l2", "category_l3"]},
    }
    frame, audit = build_b(tmp_path, config)
    spend = frame.set_index("record_id")["spend"]
    assert spend["USD"] == 10
    assert spend["DIRECT"] == -10
    assert spend["FALLBACK"] == -20
    assert spend["EXCLUDED"] == 0
    assert frame.set_index("record_id").loc["EXCLUDED", "include"] == 0
    assert next(item["fx_source_month"] for item in audit if item["record_id"] == "FALLBACK") == "2022-12"
