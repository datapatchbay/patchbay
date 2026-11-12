"""`dpb validate` on ports, tables and the links between them."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app

Writer = Callable[[str, str], Path]

DP = "dataproducts/sa_ilab_orders"
OUT = f"{DP}/outputs/sa_ilab_orders"
PRIVATE = f"{DP}/inputs/sa_ilab_orders_private"
READER_DP = "dataproducts/agg_lab_turnaround"
READER_PORT = f"{READER_DP}/inputs/sa_ilab_orders/port.yaml"

DATAPRODUCT = """\
schema_version: 1
name: ilab_orders
kind: source-aligned
owner: Jane Doe
inputs: [sa_ilab_orders_private]
outputs: [sa_ilab_orders]
"""
OUTPUT_PORT = """\
schema_version: 1
kind: schema
freshness: 24h
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
"""
SOURCE_PORT = """\
schema_version: 1
kind: schema
source: ilab
schedule: "0 5 * * *"
"""
READER_PRODUCT = "schema_version: 1\nname: lab_turnaround\nkind: aggregate\nowner: o\ninputs: [sa_ilab_orders]\n"
FROM_PORT = "schema_version: 1\nfrom: sa_ilab_orders\n"
INGESTED = """\
schema_version: 1
name: ingested_orders
columns:
  - name: order_id
    type: text
build:
  executor: python
  entrypoint: src/ingested_orders.py:build
"""
ORDERS = """\
schema_version: 1
name: orders
description: One row per lab order
columns:
  - name: order_id
    type: text
    rules: [not_null, unique]
  - name: patient_id
    type: text
    pii: true
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [open, closed]
        severity: warning
  - name: ordered_at
    type: timestamp
freshness_column: ordered_at
rules:
  - rule: primary_key
    columns: [order_id]
  - rule: row_count
    min: 1
  - rule: sql
    sql: select 1 where false
    severity: none
build:
  executor: python
  entrypoint: src/orders.py:build
  params: {mode: full}
  needs: [ingested_orders]
"""


@pytest.fixture
def product(write_file: Writer) -> None:
    """A valid data product with a private input port and a default output port."""
    write_file(f"{DP}/dataproduct.yaml", DATAPRODUCT)
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT)
    write_file(f"{PRIVATE}/ingested_orders.yaml", INGESTED)
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT)
    write_file(f"{OUT}/orders.yaml", ORDERS)
    write_file(f"{DP}/src/ingested_orders.py", "def build(): ...\n")
    write_file(f"{DP}/src/orders.py", "def build(): ...\n")


@pytest.fixture
def reader(product: None, write_file: Writer) -> None:
    """A second data product that reads the output port of the first."""
    write_file(f"{READER_DP}/dataproduct.yaml", READER_PRODUCT)
    write_file(READER_PORT, FROM_PORT)


def problems_of(runner: CliRunner) -> list[tuple[str, int | None, str]]:
    result = runner.invoke(app, ["validate", "--json"])
    return [(p["file"], p["line"], p["message"]) for p in json.loads(result.stdout)["problems"]]


def expect_problem(runner: CliRunner, file: str, line: int | None, text: str) -> None:
    found = problems_of(runner)
    assert any(f == file and ln == line and text in msg for f, ln, msg in found), found


def test_valid_product_passes(runner: CliRunner, product: None):
    assert problems_of(runner) == []


# --- port forms -------------------------------------------------------------------------------------------------


def test_input_port_reading_a_data_product_passes(runner: CliRunner, reader: None):
    assert problems_of(runner) == []


def test_freshness_on_input_port_fails_naming_the_other_form(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT + "freshness: 24h\n")
    expect_problem(runner, f"{PRIVATE}/port.yaml", 5, "'freshness' belongs to an output port")


def test_source_on_output_port_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT + "source: ilab\n")
    expect_problem(runner, f"{OUT}/port.yaml", 9, "'source' belongs to an input port")


def test_from_port_with_other_keys_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/port.yaml", "schema_version: 1\nfrom: sa_other\nkind: schema\n")
    expect_problem(runner, f"{PRIVATE}/port.yaml", 3, "'kind' belongs to")


def test_output_port_without_freshness_is_valid(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", "schema_version: 1\nkind: schema\n")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output


def test_source_input_port_requires_source_and_schedule(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/port.yaml", "schema_version: 1\nkind: schema\n")
    expect_problem(runner, f"{PRIVATE}/port.yaml", 1, "missing required key 'source'")
    expect_problem(runner, f"{PRIVATE}/port.yaml", 1, "missing required key 'schedule'")


def test_port_kind_must_be_schema_or_table(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("kind: schema", "kind: file"))
    expect_problem(runner, f"{OUT}/port.yaml", 2, "kind")


@pytest.mark.parametrize("value", ["24", "1.5h", "h", "0h", "7 days", "24H"])
def test_freshness_must_be_a_duration(runner: CliRunner, product: None, write_file: Writer, value: str):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("24h", f'"{value}"'))
    expect_problem(runner, f"{OUT}/port.yaml", 3, "freshness")


@pytest.mark.parametrize("value", ["30m", "24h", "7d"])
def test_freshness_accepts_minutes_hours_days(runner: CliRunner, product: None, write_file: Writer, value: str):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("24h", value))
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT.replace("0 5 * * *", "* * * * *"))  # delivers every minute
    assert problems_of(runner) == []


@pytest.mark.parametrize("cron", ["0 5 * * *", "*/15 0-6 1,15 jan-mar mon", "0 0 * * 7"])
def test_schedule_accepts_five_field_cron(runner: CliRunner, product: None, write_file: Writer, cron: str):
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT.replace("0 5 * * *", cron))
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("freshness: 24h\n", ""))  # syntax only: no freshness promise
    assert problems_of(runner) == []


@pytest.mark.parametrize(
    "cron", ["0 5 * *", "0 5 * * * *", "@daily", "61 5 * * *", "0 25 * * *", "a b c d e", "* * 0 * *"]
)
def test_schedule_must_be_five_field_cron(runner: CliRunner, product: None, write_file: Writer, cron: str):
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT.replace("0 5 * * *", cron))
    expect_problem(runner, f"{PRIVATE}/port.yaml", 4, "schedule")


def test_reader_entry_with_unknown_key_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("product:", "group:"))
    assert problems_of(runner)


# --- port lists and folders -------------------------------------------------------------------------------------


def test_listed_port_without_folder_fails_at_list_item(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{DP}/dataproduct.yaml", DATAPRODUCT.replace("[sa_ilab_orders]", "[sa_ilab_orders, sa_extra]"))
    expect_problem(runner, f"{DP}/dataproduct.yaml", 6, "'sa_extra'")


def test_folder_not_listed_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{DP}/outputs/sa_extra/port.yaml", OUTPUT_PORT)
    write_file(f"{DP}/outputs/sa_extra/t.yaml", ORDERS.replace("name: orders", "name: extra"))
    expect_problem(runner, f"{DP}/dataproduct.yaml", 6, "outputs/sa_extra")


def test_listed_port_folder_without_port_file_fails(runner: CliRunner, product: None):
    (Path.cwd() / OUT / "port.yaml").unlink()
    expect_problem(runner, f"{OUT}/port.yaml", None, "no port.yaml")


def test_duplicate_port_in_list_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{DP}/dataproduct.yaml", DATAPRODUCT.replace("[sa_ilab_orders]", "[sa_ilab_orders, sa_ilab_orders]"))
    expect_problem(runner, f"{DP}/dataproduct.yaml", 6, "more than once")


# --- table counts -----------------------------------------------------------------------------------------------


def test_table_port_with_two_table_files_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("kind: schema", "kind: table"))
    write_file(f"{OUT}/orders2.yaml", ORDERS.replace("name: orders", "name: orders2"))
    expect_problem(runner, f"{OUT}/port.yaml", 2, "exactly one table file")


def test_table_port_with_no_table_file_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("kind: schema", "kind: table"))
    (Path.cwd() / OUT / "orders.yaml").unlink()
    expect_problem(runner, f"{OUT}/port.yaml", 2, "exactly one table file")


def test_table_port_with_one_table_file_passes(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("kind: schema", "kind: table"))
    assert problems_of(runner) == []


def test_input_port_reading_a_product_with_table_file_fails(runner: CliRunner, reader: None, write_file: Writer):
    table = f"{READER_DP}/inputs/sa_ilab_orders/t.yaml"
    write_file(table, ORDERS)
    expect_problem(runner, table, 1, "no table files")


# --- from and readers -------------------------------------------------------------------------------------------


def test_from_must_name_existing_output_port(runner: CliRunner, reader: None, write_file: Writer):
    write_file(READER_PORT, "schema_version: 1\nfrom: sa_nothing\n")
    expect_problem(runner, READER_PORT, 2, "'sa_nothing'")


def test_from_must_name_port_of_another_data_product(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{DP}/dataproduct.yaml", DATAPRODUCT.replace("[sa_ilab_orders_private]", "[loop]"))
    (Path.cwd() / PRIVATE / "port.yaml").unlink()
    (Path.cwd() / PRIVATE / "ingested_orders.yaml").unlink()
    write_file(f"{DP}/inputs/loop/port.yaml", "schema_version: 1\nfrom: sa_ilab_orders\n")
    expect_problem(runner, f"{DP}/inputs/loop/port.yaml", 2, "another data product")


def test_from_must_not_name_an_input_port(runner: CliRunner, reader: None, write_file: Writer):
    write_file(READER_PORT, "schema_version: 1\nfrom: sa_ilab_orders_private\n")
    expect_problem(runner, READER_PORT, 2, "'sa_ilab_orders_private'")


def test_reading_product_must_be_a_reader(runner: CliRunner, reader: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("    - product: agg_lab_turnaround\n", ""))
    expect_problem(runner, READER_PORT, 2, "not listed in the readers")


def test_plain_string_reader_does_not_count_as_product_reader(runner: CliRunner, reader: None, write_file: Writer):
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("product: agg_lab_turnaround", "agg_lab_turnaround"))
    expect_problem(runner, READER_PORT, 2, "not listed in the readers")


# --- tables -----------------------------------------------------------------------------------------------------


def test_table_unknown_key_fails_with_line(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS + "foo: 1\n")
    expect_problem(runner, f"{OUT}/orders.yaml", ORDERS.count("\n") + 1, "unknown key 'foo'")


def test_unknown_column_rule_fails_with_line(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("[not_null, unique]", "[not_null, uniq]"))
    expect_problem(runner, f"{OUT}/orders.yaml", 7, "'uniq'")


def test_unknown_table_rule_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("rule: row_count", "rule: row_cnt"))
    expect_problem(runner, f"{OUT}/orders.yaml", 23, "'row_cnt'")


def test_table_rule_used_as_column_rule_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("[not_null, unique]", "[not_null, primary_key]"))
    expect_problem(runner, f"{OUT}/orders.yaml", 7, "'primary_key'")


def test_severity_must_be_error_warning_or_none(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("severity: warning", "severity: fatal"))
    expect_problem(runner, f"{OUT}/orders.yaml", 16, "severity")


def test_long_form_rule_with_severity_on_every_rule_kind_passes(runner: CliRunner, product: None, write_file: Writer):
    text = ORDERS.replace(
        "rules: [not_null, unique]",
        "rules:\n      - {rule: not_null, severity: error}\n      - {rule: unique, severity: none}",
    )
    write_file(f"{OUT}/orders.yaml", text)
    assert problems_of(runner) == []


def test_accepted_values_needs_values(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("        values: [open, closed]\n", ""))
    expect_problem(runner, f"{OUT}/orders.yaml", 14, "values")


def test_accepted_values_short_form_fails(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("[not_null, unique]", "[accepted_values]"))
    assert problems_of(runner)


def test_row_count_needs_a_bound_and_min_not_above_max(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("    min: 1\n", ""))
    assert problems_of(runner)
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("    min: 1\n", "    min: 5\n    max: 2\n"))
    assert problems_of(runner)


def test_primary_key_must_name_existing_columns(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("columns: [order_id]", "columns: [nope]"))
    expect_problem(runner, f"{OUT}/orders.yaml", 20, "'nope'")


def test_freshness_column_must_be_a_column(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("freshness_column: ordered_at", "freshness_column: nope"))
    expect_problem(runner, f"{OUT}/orders.yaml", 19, "'nope'")


def test_duplicate_column_names_fail(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("name: patient_id", "name: order_id"))
    expect_problem(runner, f"{OUT}/orders.yaml", 4, "order_id")


def test_pii_must_be_boolean(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("pii: true", "pii: maybe"))
    expect_problem(runner, f"{OUT}/orders.yaml", 10, "pii")


def test_table_names_are_unique_within_a_data_product(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("name: orders", "name: ingested_orders", 1))
    expect_problem(runner, f"{OUT}/orders.yaml", 2, "ingested_orders")


def test_same_table_name_in_different_data_products_is_fine(runner: CliRunner, product: None, write_file: Writer):
    other = "dataproducts/sa_other"
    write_file(
        f"{other}/dataproduct.yaml",
        "schema_version: 1\nname: other\nkind: source-aligned\nowner: o\noutputs: [sa_other]\n",
    )
    write_file(f"{other}/outputs/sa_other/port.yaml", OUTPUT_PORT.replace("    - product: agg_lab_turnaround\n", ""))
    write_file(f"{other}/outputs/sa_other/orders.yaml", ORDERS.replace("  needs: [ingested_orders]\n", ""))
    write_file(f"{other}/src/orders.py", "")
    assert problems_of(runner) == []


# --- build ------------------------------------------------------------------------------------------------------


def test_build_executor_is_optional_and_may_name_any_name_in_the_file(
    runner: CliRunner, product: None, write_file: Writer
):
    # Whether a plugin of that name exists is the plugin check's business; the file accepts any name.
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("  executor: python\n", "  executor: dbt\n"))
    problems = runner.invoke(app, ["validate", "--json"]).stdout
    assert "executor 'dbt' has no plugin" in problems
    assert "unknown" not in problems
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("  executor: python\n", ""))
    assert runner.invoke(app, ["validate"]).exit_code == 0


@pytest.mark.parametrize(
    "entrypoint", ["src/orders.py", "src/orders:build", "orders.py:", "src/orders.py:1x", "src/orders.py:a.b"]
)
def test_entrypoint_must_have_path_py_colon_function_form(
    runner: CliRunner, product: None, write_file: Writer, entrypoint: str
):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("src/orders.py:build", f'"{entrypoint}"'))
    expect_problem(runner, f"{OUT}/orders.yaml", 30, "entrypoint")


def test_entrypoint_file_must_exist(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("src/orders.py:build", "src/missing.py:build"))
    expect_problem(runner, f"{OUT}/orders.yaml", 30, "src/missing.py")


def test_entrypoint_must_stay_inside_the_data_product(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("src/orders.py:build", "../../../x.py:build"))
    expect_problem(runner, f"{OUT}/orders.yaml", 30, "inside the data product")


def test_needs_must_name_tables_of_the_same_data_product(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS.replace("[ingested_orders]", "[ingested_orders, ghost]"))
    expect_problem(runner, f"{OUT}/orders.yaml", 32, "'ghost'")


def test_needs_cycle_is_reported_with_the_path(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/ingested_orders.yaml", INGESTED + "  needs: [orders]\n")
    found = problems_of(runner)
    assert any("cycle" in m and "orders" in m and "ingested_orders" in m for _, _, m in found), found


def test_table_needing_itself_is_a_cycle(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/ingested_orders.yaml", INGESTED + "  needs: [ingested_orders]\n")
    assert any("cycle" in m for _, _, m in problems_of(runner))


def test_unreadable_table_does_not_cause_false_needs_problems(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{PRIVATE}/ingested_orders.yaml", "schema_version: 1\nname: [oops\n")
    found = problems_of(runner)
    assert len(found) == 1
    assert found[0][0] == f"{PRIVATE}/ingested_orders.yaml"


def test_all_problems_in_all_files_are_reported_at_once(runner: CliRunner, product: None, write_file: Writer):
    write_file(f"{OUT}/orders.yaml", ORDERS + "foo: 1\n")
    write_file(f"{PRIVATE}/port.yaml", SOURCE_PORT + "freshness: 1h\n")
    write_file(f"{OUT}/port.yaml", OUTPUT_PORT.replace("24h", "soon"))
    files = {f for f, _, _ in problems_of(runner)}
    assert files == {f"{OUT}/orders.yaml", f"{PRIVATE}/port.yaml", f"{OUT}/port.yaml"}
