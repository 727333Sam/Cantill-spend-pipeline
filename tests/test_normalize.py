from cantill_pipeline.normalize import parse_amount, parse_date, parse_vat


def test_amount_formats():
    assert parse_amount("5,266.63")[0] == 5266.63
    assert parse_amount("-13827.64")[0] == -13827.64
    assert parse_amount("")[1] == "BLANK_AMOUNT"


def test_date_formats():
    assert parse_date("27-Mar-24")[0] is not None
    assert parse_date("04/06/2023")[0] is not None
    assert parse_date("")[1] == "BLANK_DATE"


def test_vat_formats():
    assert parse_vat("15%", 0.15) == 0.15
    assert parse_vat("0.15", 0.15) == 0.15
    assert parse_vat("", 0.15) == 0.15
