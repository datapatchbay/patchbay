from collections.abc import Callable
from pathlib import Path

import pytest
from plugin_fakes import FakeOrchestrator, register
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
    """Register fake plugins under the made-up names the test repos use, next to the ones that are installed."""
    register(monkeypatch, "orchestrator", "prefect", FakeOrchestrator)
    register(monkeypatch, "executor", "spark", object)
