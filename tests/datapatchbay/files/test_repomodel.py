from pathlib import Path, PurePosixPath

from datapatchbay.files.loading import load_repo
from datapatchbay.files.repomodel import LoadedFile, Table
from datapatchbay.files.yamlio import load_mapping
from datapatchbay.models import TableFile


def _table(tmp_path: Path, build: str) -> Table:
    path = tmp_path / "table.yaml"
    path.write_text(f"schema_version: 1\nname: t\ncolumns:\n  - {{name: a, type: text}}\n{build}")
    data = load_mapping(path)
    return Table(LoadedFile(PurePosixPath("table.yaml"), TableFile.model_validate(data), data))


def test_a_table_with_a_build_block_exposes_entrypoint_function_params_and_needs(tmp_path: Path):
    table = _table(tmp_path, "build:\n  entrypoint: src/a.py:make\n  params: {n: 1}\n  needs: [x]\n")
    assert (table.entrypoint, table.entrypoint_path, table.function) == ("src/a.py:make", "src/a.py", "make")
    assert (table.params, table.needs) == ({"n": 1}, ["x"])


def test_a_table_without_a_build_block_has_no_entrypoint_and_no_needs(tmp_path: Path):
    table = _table(tmp_path, "")
    assert (table.entrypoint, table.entrypoint_path, table.function) == (None, None, None)
    assert (table.params, table.needs) == ({}, [])


def test_a_table_loaded_from_a_repo_reads_its_build_through_the_same_accessors(sample_repo: Path):
    repo, _ = load_repo(sample_repo)
    tables = [table for product in repo.dataproducts for table in product.tables if table.entrypoint]
    assert tables
    assert all(table.entrypoint_path and table.function for table in tables)
