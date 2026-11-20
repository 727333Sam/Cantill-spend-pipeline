from cantill_pipeline.deduplicate import canonical_supplier, item_key, supplier_key


def test_supplier_and_item_keys():
    assert canonical_supplier("Acme Mining (Pty) Ltd") == "ACME MINING"
    assert supplier_key("V500009", "").startswith("vendor:")
    assert supplier_key("", "Acme Mining").startswith("supplier:")
    assert item_key("MAT-1001", "").startswith("item:")
