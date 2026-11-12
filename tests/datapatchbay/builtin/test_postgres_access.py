"""The SQL that makes an output port real in Postgres: views, masking and grants (ADR-0002, ADR-0007).

The tests that apply the SQL to a real Postgres are integration tests (`tests/datapatchbay/integration`).
"""

import re
from dataclasses import replace
from pathlib import Path

import pytest
from access_support import ORDERS, ORDERS_FILE, PORT, PORT_FILE, apply_sql, plan_of

from datapatchbay.builtin.postgres import PostgresWarehouse
from datapatchbay.builtin.postgres_access import _dollar_tag
from datapatchbay.errors import DatapatchbayError


@pytest.fixture
def repo(lab_repo: Path) -> Path:
    (lab_repo / PORT).write_text(PORT_FILE)
    (lab_repo / ORDERS).write_text(ORDERS_FILE)
    return lab_repo


def test_the_apply_is_one_task_with_a_stable_id_and_the_same_sql_for_the_same_input(repo: Path):
    (task,) = PostgresWarehouse().apply_tasks(plan_of(repo))
    assert task.task_id == "apply_access"
    assert apply_sql(repo) == apply_sql(repo)


def test_a_data_product_without_output_ports_applies_nothing(repo: Path):
    assert PostgresWarehouse().apply_tasks(replace(plan_of(repo), outputs=())) == ()


def test_the_sql_names_roles_through_the_role_template_and_never_grants_on_the_private_schema(repo: Path):
    text = apply_sql(repo)
    assert '"dp_agg_lab_turnaround"' in text
    assert not re.search(r"GRANT[^;]*sa_ilab_orders_private", text)


def test_an_identifier_with_a_quote_is_escaped(repo: Path):
    (repo / PORT).write_text(PORT_FILE.replace("grp-lab-reporting", 'we"ird'))
    assert '"we""ird"' in apply_sql(repo)


def test_a_dollar_quote_tag_never_occurs_in_the_text_it_wraps():
    assert _dollar_tag("plain") == "$body$"
    assert _dollar_tag("a$body$b") not in "a$body$b"


def test_a_product_reader_that_is_not_a_data_product_is_an_error(repo: Path):
    (repo / PORT).write_text(PORT_FILE.replace("agg_lab_turnaround", "nope"))
    with pytest.raises(DatapatchbayError, match="nope"):
        apply_sql(repo)
