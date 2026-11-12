from pathlib import Path
from typing import Any

import pytest

from datapatchbay.files.loading import load_repo
from datapatchbay.pipeline.generate import generate_repo


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_load_repo_keeps_tables_ports_and_line_info(tmp_path: Path):
    _write(tmp_path, "datapatchbay.yaml", "schema_version: 1\n")
    base = "dataproducts/sa_x"
    _write(tmp_path, f"{base}/dataproduct.yaml", "schema_version: 1\nname: x\nkind: k\nowner: o\noutputs: [sa_x]\n")
    _write(tmp_path, f"{base}/outputs/sa_x/port.yaml", "schema_version: 1\nkind: schema\nfreshness: 1d\n")
    _write(
        tmp_path,
        f"{base}/outputs/sa_x/t.yaml",
        "schema_version: 1\nname: t\ncolumns:\n  - {name: a, type: text}\n"
        "build:\n  executor: python\n  entrypoint: src/t.py:build\n",
    )

    repo, problems = load_repo(tmp_path)

    assert problems == []
    [product] = repo.dataproducts
    assert product.folder == "sa_x"
    [port] = product.outputs
    [table] = port.tables
    assert (table.name, table.file.path.as_posix()) == ("t", f"{base}/outputs/sa_x/t.yaml")
    assert table.file.line("build", "entrypoint") == 7
    assert product.tables == (table,)


def test_load_repo_leaves_out_files_that_failed_and_reports_them(tmp_path: Path):
    _write(tmp_path, "datapatchbay.yaml", "schema_version: 1\n")
    base = "dataproducts/sa_x"
    _write(tmp_path, f"{base}/dataproduct.yaml", "schema_version: 1\nname: x\nkind: k\nowner: o\noutputs: [sa_x]\n")
    _write(tmp_path, f"{base}/outputs/sa_x/port.yaml", "schema_version: 1\nkind: nope\n")

    repo, problems = load_repo(tmp_path)

    assert len(problems) == 1
    assert "kind" in problems[0].message
    [product] = repo.dataproducts
    assert product.outputs == ()
    assert product.port_folders["outputs"] == ("sa_x",)


def test_generate_reads_datapatchbay_yaml_once(jaffle_repo: Path, monkeypatch: pytest.MonkeyPatch):
    reads: list[Path] = []
    real = Path.read_text

    def counting(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    generate_repo(jaffle_repo)
    assert reads.count(jaffle_repo / "datapatchbay.yaml") == 1
