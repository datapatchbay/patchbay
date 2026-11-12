import shutil
from pathlib import Path

import pytest

DP = "dataproducts/sa_ilab_orders"
READER = "dataproducts/agg_lab_turnaround"

FILES = {
    "datapatchbay.yaml": (
        "schema_version: 1\nruntime: docker\nimage: registry/root:1\ncontainer:\n  environment: {WAREHOUSE: root}\n"
    ),
    f"{DP}/dataproduct.yaml": """\
schema_version: 1
name: ilab_orders
kind: source-aligned
domain: lab
owner: Jane Doe
technical_owner: Joe Dev
description: Orders from iLab
severity: warning
orchestrator: prefect
inputs: [sa_ilab_orders_private]
outputs: [sa_ilab_orders]
""",
    f"{DP}/inputs/sa_ilab_orders_private/port.yaml": """\
schema_version: 1
kind: schema
source: ilab
schedule: "0 5 * * *"
""",
    f"{DP}/inputs/sa_ilab_orders_private/ingested.yaml": """\
schema_version: 1
name: ingested_orders
columns:
  - name: order_id
    type: text
build:
  entrypoint: src/ingested.py:build
""",
    f"{DP}/outputs/sa_ilab_orders/port.yaml": """\
schema_version: 1
kind: schema
freshness: 24h
runtime: kubernetes
access:
  readers:
    - grp-lab-reporting
    - product: agg_lab_turnaround
  pii_readers: [grp-lab-doctors]
""",
    f"{DP}/outputs/sa_ilab_orders/orders.yaml": """\
schema_version: 1
name: orders
description: One row per lab order
columns:
  - name: order_id
    type: text
    rules: [not_null]
  - name: status
    type: text
    rules:
      - rule: accepted_values
        values: [open, closed]
        severity: error
freshness_column: order_id
rules:
  - rule: row_count
    min: 1
build:
  entrypoint: src/orders.py:build
  executor: spark
  image: registry/orders:2
  container:
    environment: {WAREHOUSE: orders}
    mem_limit: 1g
  needs: [ingested_orders]
""",
    f"{DP}/src/ingested.py": "def build(): ...\n",
    f"{DP}/src/orders.py": "def build(): ...\n",
    f"{READER}/dataproduct.yaml": (
        "schema_version: 1\nname: lab_turnaround\nkind: aggregate\nowner: Ann\ninputs: [sa_ilab_orders]\n"
    ),
    f"{READER}/inputs/sa_ilab_orders/port.yaml": "schema_version: 1\nfrom: sa_ilab_orders\n",
}


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A valid repo with two data products where settings are set at every level."""
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


LAB_REPO = Path(__file__).parents[1] / "airflow" / "repo"


DBT_FIXTURE = frozenset({"dbt_project.yml", "models", "weekly_summary.yaml"})
"""The files of the fixture repo that exist for the table built by dbt, which most tests do without."""


@pytest.fixture
def lab_repo(tmp_path: Path) -> Path:
    """A copy of the valid fixture repo that CI also loads in Airflow, without its table built by dbt.

    A source-fed data product and its reader, and a data product that mixes runtimes.
    """
    root = tmp_path / "repo"
    shutil.copytree(LAB_REPO, root, ignore=lambda _folder, names: DBT_FIXTURE.intersection(names))
    return root


@pytest.fixture
def lab_dbt_repo(tmp_path: Path) -> Path:
    """A copy of the whole fixture repo, where `agg_lab_weekly` also has a table that dbt builds."""
    root = tmp_path / "repo"
    shutil.copytree(LAB_REPO, root)
    return root
