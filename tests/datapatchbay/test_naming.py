import pytest

from datapatchbay.models.root import KindConvention
from datapatchbay.naming import NamingTemplateError, derive_names, is_snake_case, render_name
from datapatchbay.settings import defaults_path, merge_settings
from datapatchbay.yamlio import load_mapping

KIND = KindConvention(prefix="sa")


def test_render_name_fills_name_and_kind_prefix():
    assert render_name("{kind.prefix}_{name}_private", name="jaffle_orders", kind_name="source-aligned", kind=KIND) == (
        "sa_jaffle_orders_private"
    )


def test_render_name_fills_kind_name():
    assert render_name("{kind.name}:{name}", name="x", kind_name="source-aligned", kind=KIND) == "source-aligned:x"


def test_unknown_placeholder_fails_listing_available_placeholders():
    with pytest.raises(NamingTemplateError) as error:
        render_name("{kind.prefx}_{name}", name="x", kind_name="k", kind=KIND)
    message = str(error.value)
    assert "{kind.prefx}" in message
    assert "{name}, {kind.prefix}, {kind.name}" in message


def test_unmatched_brace_fails():
    with pytest.raises(NamingTemplateError, match="unmatched brace"):
        render_name("{name", name="x", kind_name="k", kind=KIND)


def test_derive_names_uses_the_templates_of_the_defaults():
    conventions = merge_settings(load_mapping(defaults_path()), {}).values.conventions
    names = derive_names(conventions, name="jaffle_orders", kind_name="source-aligned")
    assert (names.dataproduct, names.output_port, names.private_port, names.role) == (
        "sa_jaffle_orders",
        "sa_jaffle_orders",
        "sa_jaffle_orders_private",
        "dp_sa_jaffle_orders",
    )


@pytest.mark.parametrize("text", ["orders", "jaffle_orders", "orders_2", "a1_b2"])
def test_snake_case_accepts(text: str):
    assert is_snake_case(text)


@pytest.mark.parametrize("text", ["Orders", "jaffle-orders", "_orders", "orders_", "a__b", "2orders", "", "ordersA"])
def test_snake_case_rejects(text: str):
    assert not is_snake_case(text)
