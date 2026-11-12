import pytest

from datapatchbay.sqlquote import standard_identifier, standard_literal


@pytest.mark.parametrize(("name", "expected"), [("orders", '"orders"'), ('we"ird', '"we""ird"')])
def test_identifiers_are_double_quoted_with_embedded_quotes_doubled(name: str, expected: str):
    assert standard_identifier(name) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("it's", "'it''s'"), (True, "TRUE"), (False, "FALSE"), (3, "3"), (1.5, "1.5")],
)
def test_literals_quote_strings_and_leave_numbers_and_booleans_bare(value: str | int | float | bool, expected: str):
    assert standard_literal(value) == expected
