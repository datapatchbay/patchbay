from pathlib import Path

import pytest

DP = "dataproducts/sa_jaffle_orders"
READER = "dataproducts/agg_order_turnaround"

FILES = {
    "datapatchbay.yaml": (
        "schema_version: 1\nruntime: docker\nimage: registry/root:1\ncontainer:\n  environment: {WAREHOUSE: root}\n"
    ),
    f"{DP}/dataproduct.yaml": """\
schema_version: 1
name: jaffle_orders
kind: source-aligned
domain: shop
owner: Jane Doe
technical_owner: Joe Dev
description: Orders from the jaffle shop
severity: warning
orchestrator: prefect
inputs: [sa_jaffle_orders_private]
outputs: [sa_jaffle_orders]
""",
    f"{DP}/inputs/sa_jaffle_orders_private/port.yaml": """\
schema_version: 1
kind: schema
source: jaffle_shop
schedule: "0 5 * * *"
""",
    f"{DP}/inputs/sa_jaffle_orders_private/ingested.yaml": """\
schema_version: 1
name: ingested_orders
columns:
  - name: order_id
    type: text
build:
  entrypoint: src/ingested.py:build
""",
    f"{DP}/outputs/sa_jaffle_orders/port.yaml": """\
schema_version: 1
kind: schema
freshness: 24h
runtime: kubernetes
access:
  readers:
    - grp-shop-reporting
    - product: agg_order_turnaround
  pii_readers: [grp-shop-support]
""",
    f"{DP}/outputs/sa_jaffle_orders/orders.yaml": """\
schema_version: 1
name: orders
description: One row per jaffle shop order
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
        "schema_version: 1\nname: order_turnaround\nkind: aggregate\nowner: Ann\ninputs: [sa_jaffle_orders]\n"
    ),
    f"{READER}/inputs/sa_jaffle_orders/port.yaml": "schema_version: 1\nfrom: sa_jaffle_orders\n",
}


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A valid repo with two data products where settings are set at every level."""
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path
