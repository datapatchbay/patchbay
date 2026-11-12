import datetime

import pytest
from ruamel.yaml import YAML

from datapatchbay.plugins.codegen.literals import python_literal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "None"),
        (True, "True"),
        (3, "3"),
        (0.5, "0.5"),
        ('it\'s "quoted"\n', '"it\'s \\"quoted\\"\\n"'),
        ("café", '"café"'),
        ([1, "a"], '[1, "a"]'),
        ({"b": 1, "a": {"c": []}}, '{"b": 1, "a": {"c": []}}'),
    ],
)
def test_python_literal_writes_plain_values(value, expected):
    assert python_literal(value) == expected


def test_python_literal_writes_values_from_the_yaml_reader_as_plain_values():
    data = YAML(typ="rt").load("a: 1.50\nb: 0x10\nc: 'text'\nd: [1, 2]\n")
    assert python_literal(data) == '{"a": 1.5, "b": 16, "c": "text", "d": [1, 2]}'


@pytest.mark.parametrize("value", [datetime.date(2025, 1, 1), float("nan"), float("inf"), {1: "a"}, {"a": {1, 2}}])
def test_python_literal_rejects_values_that_are_not_plain(value):
    with pytest.raises(ValueError, match=r"."):
        python_literal(value)
