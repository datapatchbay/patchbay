from collections.abc import Callable
from pathlib import Path

import pytest

from datapatchbay.validation import validate_repo

Writer = Callable[[str, str], Path]

DP = "dataproducts/sa_ilab_orders"
SOURCE_PORT = "schema_version: 1\nkind: schema\nsource: s\nschedule: '0 5 * * *'\n"
OUTPUT_PORT = "schema_version: 1\nkind: schema\n"
TABLE = """\
schema_version: 1
name: orders
columns:
  - name: order_id
    type: text
build:
  executor: python
  entrypoint: src/o.py:build
"""


@pytest.fixture
def write(tmp_path: Path) -> Writer:
    def write_file(relative: str, text: str) -> Path:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    write_file("datapatchbay.yaml", "schema_version: 1\n")
    return write_file


def product_yaml(name: str = "ilab_orders", kind: str = "source-aligned", extra: str = "") -> str:
    return f"schema_version: 1\nname: {name}\nkind: {kind}\nowner: o\n{extra}"


def problems(root: Path) -> list[tuple[str, int | None, str]]:
    return [(str(p.file), p.line, p.message) for p in validate_repo(root).problems]


def has_problem(root: Path, file: str, line: int | None, text: str) -> bool:
    return any(f == file and ln == line and text in message for f, ln, message in problems(root))


def test_conforming_data_product_passes(tmp_path: Path, write: Writer):
    write(
        f"{DP}/dataproduct.yaml",
        product_yaml(extra="inputs: [sa_ilab_orders_private]\noutputs: [sa_ilab_orders, sa_ilab_orders_extra]\n"),
    )
    write(f"{DP}/inputs/sa_ilab_orders_private/port.yaml", SOURCE_PORT)
    write(f"{DP}/outputs/sa_ilab_orders/port.yaml", OUTPUT_PORT)
    write(f"{DP}/outputs/sa_ilab_orders_extra/port.yaml", OUTPUT_PORT)
    assert problems(tmp_path) == []


def test_unknown_kind_fails_listing_declared_kinds(tmp_path: Path, write: Writer):
    write("dataproducts/x/dataproduct.yaml", product_yaml(kind="raw"))
    assert has_problem(tmp_path, "dataproducts/x/dataproduct.yaml", 3, "kind 'raw' is not one of the kinds")
    assert has_problem(tmp_path, "dataproducts/x/dataproduct.yaml", 3, "source-aligned, aggregate, consumer-aligned")


def test_domain_must_be_in_declared_list(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", "schema_version: 1\nconventions:\n  domains: [finance, sales]\n")
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="domain: lab\n"))
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 5, "domain 'lab'")


def test_declared_domain_is_accepted(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", "schema_version: 1\nconventions:\n  domains: [finance, sales]\n")
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="domain: sales\n"))
    assert problems(tmp_path) == []


def test_any_domain_is_accepted_when_the_list_is_empty(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="domain: anything at all\n"))
    assert problems(tmp_path) == []


def test_folder_name_must_equal_the_derived_name(tmp_path: Path, write: Writer):
    write("dataproducts/ilab_orders/dataproduct.yaml", product_yaml())
    assert has_problem(tmp_path, "dataproducts/ilab_orders/dataproduct.yaml", 2, "must be named 'sa_ilab_orders'")


def test_default_output_port_must_be_the_derived_name(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="outputs: [orders]\n"))
    write(f"{DP}/outputs/orders/port.yaml", OUTPUT_PORT)
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 5, "port 'orders' must be")


def test_private_port_must_be_the_derived_name_or_start_with_it(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="inputs: [landing]\n"))
    write(f"{DP}/inputs/landing/port.yaml", SOURCE_PORT)
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 5, "private port 'sa_ilab_orders_private'")


def test_input_port_reading_another_data_product_keeps_its_name(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="outputs: [sa_ilab_orders]\n"))
    write(f"{DP}/outputs/sa_ilab_orders/port.yaml", OUTPUT_PORT + "access:\n  readers:\n    - product: agg_report\n")
    write(
        "dataproducts/agg_report/dataproduct.yaml",
        product_yaml(name="report", kind="aggregate", extra="inputs: [sa_ilab_orders]\n"),
    )
    write("dataproducts/agg_report/inputs/sa_ilab_orders/port.yaml", "schema_version: 1\nfrom: sa_ilab_orders\n")
    assert problems(tmp_path) == []


def test_changing_a_kind_prefix_changes_what_validate_expects(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", "schema_version: 1\nconventions:\n  kinds:\n    source-aligned: {prefix: src}\n")
    write(f"{DP}/dataproduct.yaml", product_yaml())
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 2, "must be named 'src_ilab_orders'")


def test_changing_a_template_changes_what_validate_expects(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dataproduct: "dp_{name}"\n')
    write(f"{DP}/dataproduct.yaml", product_yaml())
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 2, "must be named 'dp_ilab_orders'")


def test_template_with_unknown_placeholder_fails_listing_available_ones(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    output_port: "{prefix}_{name}"\n')
    write(f"{DP}/dataproduct.yaml", product_yaml())
    found = problems(tmp_path)
    assert len(found) == 1
    file, line, message = found[0]
    assert (file, line) == ("datapatchbay.yaml", 4)
    assert "{prefix}" in message
    assert "{name}, {kind.prefix}, {kind.name}" in message


@pytest.mark.parametrize("name", ["IlabOrders", "ilab-orders"])
def test_data_product_name_must_be_snake_case(tmp_path: Path, write: Writer, name: str):
    write(f"dataproducts/sa_{name}/dataproduct.yaml", product_yaml(name=name))
    assert has_problem(tmp_path, f"dataproducts/sa_{name}/dataproduct.yaml", 2, "must be snake_case")


def test_port_table_and_column_names_must_be_snake_case(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="outputs: [sa_ilab_orders_Extra]\n"))
    write(f"{DP}/outputs/sa_ilab_orders_Extra/port.yaml", OUTPUT_PORT)
    write(
        f"{DP}/outputs/sa_ilab_orders_Extra/t.yaml",
        TABLE.replace("name: orders", "name: Orders").replace("name: order_id", "name: orderId"),
    )
    write(f"{DP}/src/o.py", "")
    table = f"{DP}/outputs/sa_ilab_orders_Extra/t.yaml"
    assert has_problem(tmp_path, f"{DP}/dataproduct.yaml", 5, "port name 'sa_ilab_orders_Extra' must be snake_case")
    assert has_problem(tmp_path, table, 2, "table name 'Orders' must be snake_case")
    assert has_problem(tmp_path, table, 4, "column name 'orderId' must be snake_case")


def test_derived_data_product_names_are_unique_across_the_repo(tmp_path: Path, write: Writer):
    write("dataproducts/a/sa_ilab_orders/dataproduct.yaml", product_yaml())
    write("dataproducts/b/sa_ilab_orders/dataproduct.yaml", product_yaml())
    assert has_problem(
        tmp_path, "dataproducts/b/sa_ilab_orders/dataproduct.yaml", 2, "'sa_ilab_orders' is already used by"
    )


def test_port_names_are_unique_across_the_repo(tmp_path: Path, write: Writer):
    write(f"{DP}/dataproduct.yaml", product_yaml(extra="outputs: [sa_ilab_orders_x]\n"))
    write(f"{DP}/outputs/sa_ilab_orders_x/port.yaml", OUTPUT_PORT)
    other = "dataproducts/sa_ilab_orders_x"
    write(f"{other}/dataproduct.yaml", product_yaml(name="ilab_orders_x", extra="outputs: [sa_ilab_orders_x]\n"))
    write(f"{other}/outputs/sa_ilab_orders_x/port.yaml", OUTPUT_PORT)
    assert has_problem(tmp_path, f"{other}/dataproduct.yaml", 5, "port name 'sa_ilab_orders_x' is already used")


def test_conventions_are_skipped_when_the_root_file_is_invalid(tmp_path: Path, write: Writer):
    write("datapatchbay.yaml", "schema_version: 1\nbogus: 1\n")
    write("dataproducts/x/dataproduct.yaml", product_yaml(kind="raw"))
    assert [file for file, _, _ in problems(tmp_path)] == ["datapatchbay.yaml"]


@pytest.mark.parametrize("key", ["dataproduct", "output_port", "private_port", "role"])
def test_every_naming_template_is_checked_for_unknown_placeholders(tmp_path: Path, write: Writer, key: str):
    write("datapatchbay.yaml", f'schema_version: 1\nconventions:\n  names:\n    {key}: "{{bogus}}_{{name}}"\n')
    write(f"{DP}/dataproduct.yaml", product_yaml())
    assert has_problem(tmp_path, "datapatchbay.yaml", 4, f"conventions.names.{key}: naming template")

