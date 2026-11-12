"""`dpb validate` on the example repo after the real `dbt parse`. Integration tests (ADR-0020).

The unit tests in `cli/test_example.py` validate a copy of the example against a hand-written dbt manifest. These
tests write the manifest with dbt itself. A missing dbt fails them.
"""

import shutil
from pathlib import Path

import pytest
from dbt_helpers import dbt_parse
from typer.testing import CliRunner

from datapatchbay.cli import app

pytestmark = pytest.mark.dbt

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "jaffle_shop"
READER = "dataproducts/agg_order_turnaround"
MODEL = f"{READER}/models/agg_order_turnaround__turnaround.sql"


@pytest.fixture
def in_example(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A copy of the example without a dbt manifest."""
    copy = tmp_path / "jaffle_shop"
    shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("target", "logs"))
    monkeypatch.chdir(copy)
    return copy


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_validate_passes_after_dbt_parse(runner: CliRunner, in_example: Path):
    # The profile of the example reads the connection from the environment and has defaults, so parsing needs no server.
    dbt_parse(in_example, in_example)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output


def test_validate_fails_after_dbt_parse_when_the_model_reads_the_private_table(runner: CliRunner, in_example: Path):
    (in_example / READER / "models" / "private_sources.yml").write_text(
        "sources:\n  - name: sa_jaffle_orders_private\n    schema: sa_jaffle_orders_private\n"
        "    tables:\n      - name: orders\n"
    )
    (in_example / MODEL).write_text(
        "select order_id, 1 as turnaround_hours, ordered_at\nfrom {{ source('sa_jaffle_orders_private', 'orders') }}\n"
    )
    dbt_parse(in_example, in_example)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code != 0
    assert f"{MODEL}:2:" in result.output
    assert "private schema 'sa_jaffle_orders_private'" in result.output
