"""Constants and helpers shared by the dbt tests."""

from pathlib import Path

from datapatchbay.validation import load_and_validate, validate_repo

DP = "dataproducts/agg_order_turnaround"
TABLE = f"{DP}/outputs/agg_order_turnaround/turnaround.yaml"
MODEL = f"{DP}/models/agg_order_turnaround__turnaround.sql"
TABLE_YAML = "schema_version: 1\nname: turnaround\ncolumns:\n  - name: days\n    type: numeric\n"


def rendered(repo: Path) -> list[str]:
    """The problems of `validate_repo`, with an empty dbt manifest in place unless the test made one."""
    if not (repo / "target" / "manifest.json").exists():
        write(repo, "target/manifest.json", '{"metadata": {}, "nodes": {}, "sources": {}}')
    return [problem.render() for problem in validate_repo(repo).problems]


def checked(repo: Path) -> list[str]:
    """The problems of the files themselves, before `validate_repo` compares the generated dbt files."""
    return [problem.render() for problem in load_and_validate(repo)[1].problems]


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
