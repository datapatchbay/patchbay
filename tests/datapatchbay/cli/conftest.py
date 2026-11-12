from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay import pluginchecks


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal valid repo, entered as the working directory."""
    (tmp_path / "datapatchbay.yaml").write_text("schema_version: 1\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def write_dataproduct(repo: Path) -> Callable[[str, str], Path]:
    """Return a factory that writes `dataproducts/<folder>/dataproduct.yaml`."""

    def write(folder: str, text: str) -> Path:
        path = repo / "dataproducts" / folder / "dataproduct.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    return write


@pytest.fixture
def write_file(repo: Path) -> Callable[[str, str], Path]:
    """Return a factory that writes any file below the repo root, creating folders as needed."""

    def write(relative: str, text: str) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    return write


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def every_plugin_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the plugin check accept any name, for tests that use made-up plugin names to test other rules."""
    monkeypatch.setattr(
        pluginchecks,
        "plugin_names",
        lambda kind: ["airflow", "prefect", "dbt", "docker", "kubernetes", "python", "worker", "postgres"],
    )
