from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner


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
def runner() -> CliRunner:
    return CliRunner()
