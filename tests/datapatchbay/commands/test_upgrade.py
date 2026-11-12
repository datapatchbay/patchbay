import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from datapatchbay.commands.upgrade import Migration, rename_key, upgrade_repo

FILES = {
    "datapatchbay.yaml": "# root\nschema_version: 1\nwharehouse: x  # keep me\n",
    "dataproducts/sa_a/dataproduct.yaml": "schema_version: 1\nname: a\nwharehouse: y\n",
    "dataproducts/sa_a/inputs/sa_a_private/port.yaml": "schema_version: 1\nname: p\n",
    "dataproducts/sa_a/inputs/sa_a_private/t_in.yaml": "schema_version: 1\nname: t_in\n",
    "dataproducts/sa_a/outputs/sa_a/port.yaml": "schema_version: 1\nname: o\n",
    "dataproducts/sa_a/outputs/sa_a/orders.yaml": "schema_version: 1\nname: orders\n",
}


def rename_wharehouse(data: CommentedMap) -> None:
    """Test-only migration 1 -> 2: fix the typo `wharehouse` where it occurs."""
    if "wharehouse" in data:
        rename_key(data, "wharehouse", "warehouse")


MIGRATIONS = {1: Migration(rename_wharehouse)}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for name, text in FILES.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_upgrade_with_everything_current_changes_nothing(repo: Path):
    result = upgrade_repo(repo)
    assert result.changes == []
    assert result.problems == []
    assert {n: (repo / n).read_text() for n in FILES} == FILES


def test_upgrade_rewrites_all_four_kinds_of_file(repo: Path):
    result = upgrade_repo(repo, migrations=MIGRATIONS, current_version=2)
    assert sorted(str(c.file) for c in result.changes) == sorted(FILES)
    for name in FILES:
        assert "schema_version: 2" in (repo / name).read_text()
    assert all((c.from_version, c.to_version) == (1, 2) for c in result.changes)


def test_upgrade_keeps_comments_and_key_order(repo: Path):
    upgrade_repo(repo, migrations=MIGRATIONS, current_version=2)
    assert (repo / "datapatchbay.yaml").read_text() == "# root\nschema_version: 2\nwarehouse: x  # keep me\n"
    assert (repo / "dataproducts/sa_a/dataproduct.yaml").read_text() == "schema_version: 2\nname: a\nwarehouse: y\n"


def test_upgrade_runs_steps_in_order_until_current(repo: Path):
    order: list[int] = []

    def step(n: int) -> Migration:
        def apply(data: CommentedMap) -> None:
            order.append(n)
            data[f"step{n}"] = True

        return Migration(apply)

    result = upgrade_repo(repo, migrations={1: step(1), 2: step(2), 3: step(3)}, current_version=4)
    assert order[:3] == [1, 2, 3]
    assert {(c.from_version, c.to_version) for c in result.changes} == {(1, 4)}
    text = (repo / "dataproducts/sa_a/outputs/sa_a/orders.yaml").read_text()
    assert text == "schema_version: 4\nname: orders\nstep1: true\nstep2: true\nstep3: true\n"


def test_upgrade_only_touches_files_that_are_behind(repo: Path):
    path = repo / "dataproducts/sa_a/outputs/sa_a/orders.yaml"
    path.write_text("schema_version: 2\nname: orders\n")
    result = upgrade_repo(repo, migrations=MIGRATIONS, current_version=2)
    assert "dataproducts/sa_a/outputs/sa_a/orders.yaml" not in [str(c.file) for c in result.changes]
    assert path.read_text() == "schema_version: 2\nname: orders\n"


def test_dry_run_reports_changes_and_writes_nothing(repo: Path):
    result = upgrade_repo(repo, dry_run=True, migrations=MIGRATIONS, current_version=2)
    assert len(result.changes) == len(FILES)
    assert {n: (repo / n).read_text() for n in FILES} == FILES
    root_change = next(c for c in result.changes if str(c.file) == "datapatchbay.yaml")
    assert root_change.before == FILES["datapatchbay.yaml"]
    assert root_change.after == "# root\nschema_version: 2\nwarehouse: x  # keep me\n"


def test_rename_key_keeps_position_and_its_comment():
    yaml = YAML(typ="rt")
    data = yaml.load("a: 1\nold: 2  # note\nc: 3\n")
    rename_key(data, "old", "new")
    buffer = io.StringIO()
    yaml.dump(data, buffer)
    assert buffer.getvalue() == "a: 1\nnew: 2  # note\nc: 3\n"


def test_file_newer_than_known_is_refused_and_nothing_is_written(repo: Path):
    (repo / "dataproducts/sa_a/dataproduct.yaml").write_text("schema_version: 9\nname: a\n")
    result = upgrade_repo(repo, migrations=MIGRATIONS, current_version=2)
    assert result.changes == []
    [problem] = result.problems
    assert problem.render() == (
        "dataproducts/sa_a/dataproduct.yaml:1: schema_version 9 is newer than this datapatchbay understands "
        "(newest known: 2); upgrade datapatchbay"
    )
    assert (repo / "datapatchbay.yaml").read_text() == FILES["datapatchbay.yaml"]


@pytest.mark.parametrize("text", ["name: a\n", "schema_version: one\n", "schema_version: 0\n", "- a\n", ""])
def test_unreadable_or_unversioned_file_is_refused(repo: Path, text: str):
    (repo / "dataproducts/sa_a/dataproduct.yaml").write_text(text)
    result = upgrade_repo(repo)
    assert len(result.problems) == 1
    assert str(result.problems[0].file) == "dataproducts/sa_a/dataproduct.yaml"


def test_missing_migration_step_is_refused(repo: Path):
    result = upgrade_repo(repo, migrations={}, current_version=2)
    assert result.changes == []
    assert "no migration from schema_version 1" in result.problems[0].message


def test_rewrite_keeps_quotes_long_lines_and_the_product_md_list_style(repo: Path):
    long_line = "word " * 40
    text = (
        "schema_version: 1\n"
        "name: 'quoted'\n"
        f"description: {long_line.strip()}\n"
        "columns:\n"
        "  - name: status\n"
        "    rules:\n"
        "      - rule: accepted_values\n"
        "        values: [open, closed]\n"
    )
    path = repo / "dataproducts/sa_a/outputs/sa_a/orders.yaml"
    path.write_text(text)
    upgrade_repo(repo, migrations=MIGRATIONS, current_version=2)
    assert path.read_text() == text.replace("schema_version: 1", "schema_version: 2")
