from pathlib import Path

from audit_support import audit_of, columns_yaml


def test_a_table_without_quality_rules_gets_no_audit_task(jaffle_repo: Path):
    assert audit_of(jaffle_repo, columns_yaml()) is None


def test_a_table_gets_one_audit_task_named_after_it_with_a_check_per_rule_in_a_fixed_order(jaffle_repo: Path):
    table = columns_yaml(
        order_id_rules="- not_null\n- unique\n", status_rules="- {rule: accepted_values, values: [a]}\n"
    )
    table += "rules:\n  - {rule: row_count, min: 1}\n  - {rule: primary_key, columns: [order_id]}\n"
    task = audit_of(jaffle_repo, table)
    assert task is not None
    assert task.task_id == "audit_orders"
    assert [(c.rule, c.table, c.column) for c in task.checks] == [
        ("not_null", "orders", "order_id"),
        ("unique", "orders", "order_id"),
        ("accepted_values", "orders", "status"),
        ("row_count", "orders", None),
        ("primary_key", "orders", "order_id"),
    ]


def test_a_bare_rule_takes_the_default_severity_of_the_table_and_a_rule_can_override_it(jaffle_repo: Path):
    table = columns_yaml(order_id_rules="- not_null\n- {rule: unique, severity: error}\n")
    task = audit_of(jaffle_repo, table, settings="severity: warning\n")
    assert task is not None
    assert [(c.rule, c.severity) for c in task.checks] == [("not_null", "warning"), ("unique", "error")]


def test_the_default_severity_cascades_from_the_data_product_to_the_table(jaffle_repo: Path):
    product = jaffle_repo / "dataproducts/sa_jaffle_orders/dataproduct.yaml"
    product.write_text(product.read_text() + "severity: warning\n")
    task = audit_of(jaffle_repo, columns_yaml(order_id_rules="- not_null\n"), settings="severity: error\n")
    assert task is not None
    assert [c.severity for c in task.checks] == ["warning"]


def test_a_rule_with_severity_none_produces_no_sql(jaffle_repo: Path):
    table = columns_yaml(order_id_rules="- {rule: not_null, severity: none}\n- unique\n")
    task = audit_of(jaffle_repo, table)
    assert task is not None
    assert [c.rule for c in task.checks] == ["unique"]


def test_a_table_whose_rules_are_all_none_gets_no_audit_task(jaffle_repo: Path):
    assert audit_of(jaffle_repo, columns_yaml(order_id_rules="- not_null\n"), settings="severity: none\n") is None


def test_the_sql_of_a_check_counts_violations_in_the_private_schema_of_the_table(jaffle_repo: Path):
    task = audit_of(jaffle_repo, columns_yaml(order_id_rules="- not_null\n"))
    assert task is not None
    assert task.checks[0].sql == 'SELECT count(*) FROM "sa_jaffle_orders_private"."orders" WHERE "order_id" IS NULL'
