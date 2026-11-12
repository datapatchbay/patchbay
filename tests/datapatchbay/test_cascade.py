from pathlib import Path, PurePosixPath

from datapatchbay.cascade import CASCADING_SETTINGS, resolve_cascade, resolve_setting
from datapatchbay.loading import load_repo
from datapatchbay.repomodel import DataProduct
from datapatchbay.settings import EffectiveSettings, load_settings


def setup(root: Path) -> tuple[EffectiveSettings, DataProduct, DataProduct]:
    repo, problems = load_repo(root)
    assert problems == []
    orders = next(p for p in repo.dataproducts if p.folder == "sa_jaffle_orders")
    reader = next(p for p in repo.dataproducts if p.folder == "agg_order_turnaround")
    return load_settings(root), orders, reader


def test_table_setting_beats_every_other_level(sample_repo: Path):
    settings, orders, _ = setup(sample_repo)
    port = orders.outputs[0]
    got = resolve_setting("image", settings, dataproduct=orders, port=port, table=port.tables[0])
    assert (got.value, got.level) == ("registry/orders:2", "table")
    assert got.file == PurePosixPath("dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml")


def test_port_setting_beats_data_product_and_root(sample_repo: Path):
    settings, orders, _ = setup(sample_repo)
    port = orders.outputs[0]
    got = resolve_setting("runtime", settings, dataproduct=orders, port=port, table=port.tables[0])
    assert (got.value, got.level) == ("kubernetes", "port")


def test_data_product_setting_beats_root_and_defaults(sample_repo: Path):
    settings, orders, _ = setup(sample_repo)
    got = resolve_setting("severity", settings, dataproduct=orders, port=orders.outputs[0])
    assert (got.value, got.level) == ("warning", "dataproduct")
    assert got.file == PurePosixPath("dataproducts/sa_jaffle_orders/dataproduct.yaml")


def test_root_setting_is_used_when_no_nearer_level_sets_it(sample_repo: Path):
    settings, _, reader = setup(sample_repo)
    got = resolve_setting("runtime", settings, dataproduct=reader)
    assert (got.value, got.level, got.file) == ("docker", "root", PurePosixPath("datapatchbay.yaml"))


def test_packaged_default_is_used_when_nothing_sets_it(sample_repo: Path):
    settings, _, reader = setup(sample_repo)
    got = resolve_setting("executor", settings, dataproduct=reader)
    assert (got.value, got.level, got.file) == ("python", "defaults", None)


def test_setting_that_no_level_sets_is_unset(sample_repo: Path):
    (sample_repo / "datapatchbay.yaml").write_text("schema_version: 1\n")
    settings, _, reader = setup(sample_repo)
    got = resolve_setting("image", settings, dataproduct=reader)
    assert (got.value, got.level, got.file) == (None, "unset", None)


def test_orchestrator_cascades_over_root_and_data_product_only(sample_repo: Path):
    settings, orders, reader = setup(sample_repo)
    port = orders.outputs[0]
    nearest = resolve_setting("orchestrator", settings, dataproduct=orders, port=port, table=port.tables[0])
    assert (nearest.value, nearest.level) == ("prefect", "dataproduct")
    assert resolve_setting("orchestrator", settings, dataproduct=reader).level == "defaults"


def test_the_cascade_resolves_every_setting_of_a_table_with_its_provenance(sample_repo: Path):
    settings, orders, _ = setup(sample_repo)
    port = orders.outputs[0]
    table = port.tables[0]
    got = resolve_cascade(load_repo(sample_repo)[0], settings).for_table(table)
    assert {name: (s.value, s.level) for name, s in got.items()} == {
        "executor": ("spark", "table"),
        "runtime": ("kubernetes", "port"),
        "image": ("registry/orders:2", "table"),
        "container": ({"environment": {"WAREHOUSE": "orders"}, "mem_limit": "1g"}, "table"),
        "severity": ("warning", "dataproduct"),
    }
    assert got["image"].to_json() == {
        "value": "registry/orders:2",
        "level": "table",
        "file": "dataproducts/sa_jaffle_orders/outputs/sa_jaffle_orders/orders.yaml",
    }
    assert got["image"].line == table.file.line("build", "image")
    assert got["runtime"].line == port.file.line("runtime")
    assert got["severity"].line == orders.file.line("severity")


def test_the_cascade_of_a_data_product_adds_the_orchestrator_and_root_lines(sample_repo: Path):
    settings, orders, reader = setup(sample_repo)
    repo, _ = load_repo(sample_repo)
    cascade = resolve_cascade(repo, settings)
    assert list(cascade.for_dataproduct(orders)) == [*CASCADING_SETTINGS, "orchestrator"]
    assert cascade.for_dataproduct(orders)["orchestrator"].level == "dataproduct"
    assert cascade.for_dataproduct(reader)["orchestrator"].level == "defaults"
    root = cascade.for_dataproduct(reader)["container"]
    assert (root.level, root.line) == ("root", 4)  # the `container:` key of the sample root file


def test_the_cascading_settings_are_the_fields_of_the_cascading_settings_model():
    assert CASCADING_SETTINGS == ("executor", "runtime", "image", "container", "severity")


def test_container_cascades_as_a_whole_and_the_nearest_one_wins(sample_repo: Path):
    settings, orders, reader = setup(sample_repo)
    port = orders.outputs[0]
    table = resolve_setting("container", settings, dataproduct=orders, port=port, table=port.tables[0])
    assert (table.value, table.level) == ({"environment": {"WAREHOUSE": "orders"}, "mem_limit": "1g"}, "table")
    root = resolve_setting("container", settings, dataproduct=reader)
    assert (root.value, root.level) == ({"environment": {"WAREHOUSE": "root"}}, "root")


def test_container_is_unset_when_no_level_sets_it(sample_repo: Path):
    (sample_repo / "datapatchbay.yaml").write_text("schema_version: 1\n")
    settings, _, reader = setup(sample_repo)
    assert resolve_setting("container", settings, dataproduct=reader).level == "unset"
