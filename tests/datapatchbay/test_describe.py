from pathlib import Path
from typing import Any

import pytest

from datapatchbay.describe import (
    UnknownDataProductError,
    describe_dataproduct,
    find_dataproduct,
    list_dataproducts,
    render_description,
    render_list,
)
from datapatchbay.loading import load_repo
from datapatchbay.settings import load_settings


def describe(root: Path, folder: str) -> dict[str, Any]:
    repo, _ = load_repo(root)
    return describe_dataproduct(repo, load_settings(root), find_dataproduct(repo, folder))


def test_list_has_kind_domain_owner_and_technical_owner(sample_repo: Path):
    repo, _ = load_repo(sample_repo)
    assert list_dataproducts(repo) == [
        {
            "folder": "agg_order_turnaround",
            "name": "order_turnaround",
            "kind": "aggregate",
            "domain": None,
            "owner": "Ann",
            "technical_owner": None,
        },
        {
            "folder": "sa_jaffle_orders",
            "name": "jaffle_orders",
            "kind": "source-aligned",
            "domain": "shop",
            "owner": "Jane Doe",
            "technical_owner": "Joe Dev",
        },
    ]


def test_render_list_aligns_columns(sample_repo: Path):
    repo, _ = load_repo(sample_repo)
    lines = render_list(list_dataproducts(repo)).splitlines()
    assert lines[0].split() == ["DATA", "PRODUCT", "KIND", "DOMAIN", "OWNER", "TECHNICAL", "OWNER"]
    assert lines[2].split() == ["sa_jaffle_orders", "source-aligned", "shop", "Jane", "Doe", "Joe", "Dev"]


def test_find_by_folder_or_name_and_unknown_names_existing(sample_repo: Path):
    repo, _ = load_repo(sample_repo)
    assert find_dataproduct(repo, "sa_jaffle_orders").folder == "sa_jaffle_orders"
    assert find_dataproduct(repo, "jaffle_orders").folder == "sa_jaffle_orders"
    with pytest.raises(UnknownDataProductError, match=r"'nope'.*agg_order_turnaround, sa_jaffle_orders"):
        find_dataproduct(repo, "nope")


def test_describe_lists_output_port_readers_freshness_and_who_reads_it(sample_repo: Path):
    port = describe(sample_repo, "sa_jaffle_orders")["outputs"][0]
    assert port["freshness"] == "24h"
    assert port["readers"] == [
        {"type": "role", "name": "grp-shop-reporting"},
        {"type": "product", "name": "agg_order_turnaround"},
    ]
    assert port["pii_readers"] == ["grp-shop-support"]
    assert port["read_by"] == ["agg_order_turnaround"]


def test_describe_shows_input_ports(sample_repo: Path):
    source = describe(sample_repo, "sa_jaffle_orders")["inputs"][0]
    assert (source["source"], source["schedule"]) == ("jaffle_shop", "0 5 * * *")
    assert describe(sample_repo, "agg_order_turnaround")["inputs"][0]["from"] == "sa_jaffle_orders"


def test_describe_shows_tables_columns_and_rules_with_severity_origin(sample_repo: Path):
    table = describe(sample_repo, "sa_jaffle_orders")["outputs"][0]["tables"][0]
    assert table["freshness_column"] == "order_id"
    assert table["needs"] == ["ingested_orders"]
    columns = {c["name"]: c for c in table["columns"]}
    assert columns["order_id"]["rules"] == [{"rule": "not_null", "severity": "warning", "severity_from": "dataproduct"}]
    assert columns["status"]["rules"][0]["severity_from"] == "rule"
    assert columns["status"]["rules"][0]["values"] == ["open", "closed"]
    assert table["rules"][0]["min"] == 1


def test_describe_resolves_settings_with_level_at_each_place(sample_repo: Path):
    description = describe(sample_repo, "sa_jaffle_orders")
    assert description["settings"]["orchestrator"]["level"] == "dataproduct"
    assert description["settings"]["runtime"]["level"] == "root"
    port = description["outputs"][0]
    assert port["settings"]["runtime"] == {"value": "kubernetes", "level": "port", "file": port["file"]}
    assert port["tables"][0]["settings"]["executor"]["level"] == "table"
    assert "orchestrator" not in port["settings"]


def test_render_description_shows_resolved_settings_and_levels(sample_repo: Path):
    text = render_description(describe(sample_repo, "sa_jaffle_orders"))
    assert "runtime: kubernetes  (port, dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/port.yaml)" in text
    assert "executor: python  (defaults)" in text
    assert "read by: agg_order_turnaround" in text
    assert "rule: not_null [warning, from dataproduct]" in text
