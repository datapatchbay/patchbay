import shutil
from pathlib import Path

import pytest

DP = "dataproducts/sa_ilab_orders"
READER = "dataproducts/agg_lab_turnaround"

FILES = {
    "datapatchbay.yaml": "schema_version: 1\nruntime: docker\nimage: registry/root:1\n",
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
  executor: dbt
  image: registry/orders:2
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


@pytest.fixture
def lab_repo(tmp_path: Path) -> Path:
    """A copy of the valid fixture repo that CI also loads in Airflow: a source-fed data product and its reader."""
    root = tmp_path / "repo"
    shutil.copytree(LAB_REPO, root)
    return root
