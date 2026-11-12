import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datapatchbay.cli import app
from datapatchbay.validation import validate_repo

FLAGS = ["new", "--name", "ilab_orders", "--kind", "source-aligned", "--owner", "Jane Doe", "--no-input"]


def assert_valid(root: Path) -> None:
    report = validate_repo(root)
    assert [problem.render() for problem in report.problems] == []
    assert report.dataproducts_checked == 1


def test_new_without_source_creates_validating_data_product(runner: CliRunner, repo: Path):
    result = runner.invoke(app, [*FLAGS, "--domain", "lab", "--technical-owner", "Joe Dev"])
    assert result.exit_code == 0, result.output
    folder = repo / "dataproducts/sa_ilab_orders"
    assert (folder / "dataproduct.yaml").read_text() == (
        "schema_version: 1\n"
        "name: ilab_orders\n"
        "kind: source-aligned\n"
        "domain: lab\n"
        "owner: Jane Doe\n"
        "technical_owner: Joe Dev\n"
        "outputs:\n"
        "  - sa_ilab_orders\n"
    )
    assert (folder / "outputs/sa_ilab_orders/port.yaml").read_text() == "schema_version: 1\nkind: schema\n"
    assert (folder / "outputs/sa_ilab_orders/example.yaml").read_text() == (
        "schema_version: 1\n"
        "name: example\n"
        "description: Example table; rename it and describe one row.\n"
        "columns:\n"
        "  - name: id\n"
        "    type: text\n"
        "    description: Identifier of the row.\n"
        "    rules:\n"
        "      - not_null\n"
        "      - unique\n"
        "build:\n"
        "  entrypoint: src/example.py:build\n"
    )
    assert (folder / "src/example.py").is_file()
    assert not (folder / "inputs").exists()
    assert_valid(repo)


def test_new_with_source_adds_private_port_with_schedule_and_ingested_table(runner: CliRunner, repo: Path):
    result = runner.invoke(app, [*FLAGS, "--source", "ilab", "--schedule", "0 6 * * 1-5"])
    assert result.exit_code == 0, result.output
    folder = repo / "dataproducts/sa_ilab_orders"
    assert "inputs:\n  - sa_ilab_orders_private\n" in (folder / "dataproduct.yaml").read_text()
    assert (folder / "inputs/sa_ilab_orders_private/port.yaml").read_text() == (
        'schema_version: 1\nkind: schema\nsource: ilab\nschedule: "0 6 * * 1-5"\n'
    )
    assert "entrypoint: src/ingested.py:build" in (folder / "inputs/sa_ilab_orders_private/ingested.yaml").read_text()
    assert "needs:\n    - ingested" in (folder / "outputs/sa_ilab_orders/example.yaml").read_text()
    assert (folder / "src/ingested.py").is_file()
    assert_valid(repo)


def test_new_uses_default_schedule_when_none_given(runner: CliRunner, repo: Path):
    runner.invoke(app, [*FLAGS, "--source", "ilab"])
    port = repo / "dataproducts/sa_ilab_orders/inputs/sa_ilab_orders_private/port.yaml"
    assert 'schedule: "0 5 * * *"' in port.read_text()
    assert_valid(repo)


def test_new_names_folder_and_ports_from_the_naming_templates(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text(
        "schema_version: 1\n"
        "conventions:\n"
        "  names:\n"
        '    dataproduct: "dp_{kind.prefix}_{name}"\n'
        '    output_port: "dp_{kind.prefix}_{name}"\n'
        '    private_port: "dp_{kind.prefix}_{name}_raw"\n'
    )
    result = runner.invoke(app, [*FLAGS, "--source", "ilab"])
    assert result.exit_code == 0, result.output
    folder = repo / "dataproducts/dp_sa_ilab_orders"
    assert (folder / "inputs/dp_sa_ilab_orders_raw/port.yaml").is_file()
    assert (folder / "outputs/dp_sa_ilab_orders/port.yaml").is_file()
    assert_valid(repo)


def test_new_no_input_lists_every_missing_value(runner: CliRunner, repo: Path):
    result = runner.invoke(app, ["new", "--no-input"])
    assert result.exit_code == 2
    assert "--name, --kind, --owner" in result.output
    assert not (repo / "dataproducts").exists()


def test_new_no_input_requires_domain_when_domains_are_declared(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nconventions:\n  domains: [lab, sales]\n")
    result = runner.invoke(app, FLAGS)
    assert result.exit_code == 2
    assert "--domain" in result.output


def test_new_prompts_for_missing_values_in_a_terminal(runner: CliRunner, repo: Path):
    result = runner.invoke(app, ["new"], input="ilab_orders\nsource-aligned\n\nJane Doe\nJoe Dev\n")
    assert result.exit_code == 0, result.output
    for question in ("Name", "Kind", "Domain", "Owner", "Technical owner"):
        assert question in result.output
    text = (repo / "dataproducts/sa_ilab_orders/dataproduct.yaml").read_text()
    assert "owner: Jane Doe" in text
    assert "technical_owner: Joe Dev" in text
    assert "domain" not in text
    assert_valid(repo)


def test_new_prompts_only_for_values_not_given_as_flags(runner: CliRunner, repo: Path):
    result = runner.invoke(app, ["new", "--name", "ilab_orders", "--kind", "source-aligned"], input="\nJane\n\n")
    assert result.exit_code == 0, result.output
    assert "Name" not in result.output
    assert "Kind" not in result.output
    assert_valid(repo)


def test_new_refuses_to_overwrite_an_existing_data_product(runner: CliRunner, repo: Path):
    assert runner.invoke(app, FLAGS).exit_code == 0
    path = repo / "dataproducts/sa_ilab_orders/dataproduct.yaml"
    path.write_text(path.read_text() + "description: edited by hand\n")
    before = path.read_text()
    result = runner.invoke(app, [*FLAGS, "--owner", "Someone Else"])
    assert result.exit_code == 2
    assert "dataproducts/sa_ilab_orders already exists" in result.output
    assert path.read_text() == before


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--name", "Bad Name"], "must be snake_case"),
        (["--kind", "nonsense"], "is not one of the declared kinds: source-aligned, aggregate, consumer-aligned"),
        (["--source", "ilab", "--schedule", "not cron"], "is not a cron expression"),
    ],
)
def test_new_rejects_invalid_answers_and_writes_nothing(runner: CliRunner, repo: Path, extra: list[str], message: str):
    result = runner.invoke(app, [*FLAGS, *extra])
    assert result.exit_code == 2
    assert message in result.output
    assert not (repo / "dataproducts").exists()


def test_new_rejects_domain_outside_the_declared_domains(runner: CliRunner, repo: Path):
    (repo / "datapatchbay.yaml").write_text("schema_version: 1\nconventions:\n  domains: [lab]\n")
    result = runner.invoke(app, [*FLAGS, "--domain", "sales"])
    assert result.exit_code == 2
    assert "domain 'sales' is not one of the declared domains: lab" in result.output


def test_new_json_prints_only_the_created_files_on_stdout(runner: CliRunner, repo: Path):
    result = runner.invoke(app, [*FLAGS, "--source", "ilab", "--json"])
    assert result.exit_code == 0, result.output
    folder = "dataproducts/sa_ilab_orders"
    assert json.loads(result.stdout) == {
        "created": [
            f"{folder}/dataproduct.yaml",
            f"{folder}/inputs/sa_ilab_orders_private/port.yaml",
            f"{folder}/inputs/sa_ilab_orders_private/ingested.yaml",
            f"{folder}/outputs/sa_ilab_orders/port.yaml",
            f"{folder}/outputs/sa_ilab_orders/example.yaml",
            f"{folder}/src/ingested.py",
            f"{folder}/src/example.py",
        ]
    }


def test_new_fails_outside_a_repo(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, FLAGS)
    assert result.exit_code == 2
    assert "no datapatchbay.yaml found" in result.output
