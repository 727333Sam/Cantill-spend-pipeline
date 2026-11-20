from cantill_pipeline.pipeline import is_cancelled, is_not_approved, non_procurement


def test_status_exclusions():
    assert is_cancelled("Cancelled")
    assert is_not_approved("Rejected")
    assert is_not_approved("On Hold")
    assert not is_not_approved("Paid")


def test_non_procurement_patterns():
    row = {
        "gl_account_description": "IC Payables",
        "line_description": "",
        "document_type": "PV",
    }
    assert non_procurement(row, "gl_account_description", "line_description")
    row = {
        "gl_account_description": "Raw materials",
        "line_description": "Ball bearing",
        "document_type": "PV",
    }
    assert not non_procurement(row, "gl_account_description", "line_description")
