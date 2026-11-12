from pathlib import Path, PurePosixPath

import pytest

from datapatchbay import schemas
from datapatchbay.builtin.dbt_executor import DbtExecutor
from datapatchbay.cascade import resolve_setting
from datapatchbay.loading import load_repo
from datapatchbay.planning import plan_dataproducts
from datapatchbay.plugins import DbtCall
from datapatchbay.settings import load_settings
from datapatchbay.validation import validate_repo

DP = "dataproducts/agg_lab_turnaround"
TABLE = f"{DP}/outputs/agg_lab_turnaround/turnaround.yaml"
MODEL = f"{DP}/models/agg_lab_turnaround__turnaround.sql"
TABLE_YAML = "schema_version: 1\nname: turnaround\ncolumns:\n  - name: days\n    type: numeric\n"


def rendered(repo: Path) -> list[str]:
    return [problem.render() for problem in validate_repo(repo).problems]


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def dbt_repo(lab_repo: Path) -> Path:
    """The lab repo where the reader data product builds its table with dbt, set on the data product."""
    product = lab_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(lab_repo, TABLE, TABLE_YAML)
    write(lab_repo, MODEL, "select 1 as days\n")
    return lab_repo


def test_a_table_built_by_dbt_needs_no_build_block_and_its_model(dbt_repo: Path):
    assert rendered(dbt_repo) == []


@pytest.mark.parametrize("level", ["root", "dataproduct", "port", "table"])
def test_executor_dbt_is_accepted_at_every_level(tmp_path: Path, level: str):
    root = "schema_version: 1\n" + ("executor: dbt\n" if level == "root" else "")
    product = "schema_version: 1\nname: x\nkind: aggregate\nowner: Ann\noutputs: [agg_x]\n"
    product += "executor: dbt\n" if level == "dataproduct" else ""
    port = "schema_version: 1\nkind: schema\n" + ("executor: dbt\n" if level == "port" else "")
    table = TABLE_YAML + ("build:\n  executor: dbt\n" if level == "table" else "")
    write(tmp_path, "datapatchbay.yaml", root)
    write(tmp_path, "dataproducts/agg_x/dataproduct.yaml", product)
    write(tmp_path, "dataproducts/agg_x/outputs/agg_x/port.yaml", port)
    write(tmp_path, "dataproducts/agg_x/outputs/agg_x/t.yaml", table.replace("turnaround", "t"))
    write(tmp_path, "dataproducts/agg_x/models/agg_x__t.sql", "select 1\n")
    assert rendered(tmp_path) == []


def test_the_nearest_executor_wins(dbt_repo: Path):
    write(dbt_repo, TABLE, TABLE_YAML + "build:\n  executor: python\n  entrypoint: src/turnaround.py:build\n")
    (dbt_repo / MODEL).unlink()
    assert rendered(dbt_repo) == []
    repo, _ = load_repo(dbt_repo)
    product = next(p for p in repo.dataproducts if p.folder == "agg_lab_turnaround")
    resolved = resolve_setting(
        "executor",
        load_settings(dbt_repo),
        dataproduct=product,
        port=product.outputs[0],
        table=product.outputs[0].tables[0],
    )
    assert (resolved.value, resolved.level) == ("python", "table")


@pytest.mark.parametrize(
    ("block", "key"),
    [("entrypoint: src/turnaround.py:build", "entrypoint"), ("params: {a: 1}", "params"), ("needs: []", "needs")],
)
def test_entrypoint_params_and_needs_fail_on_a_dbt_table(dbt_repo: Path, block: str, key: str):
    write(dbt_repo, TABLE, TABLE_YAML + f"build:\n  {block}\n")
    assert rendered(dbt_repo) == [
        f"{TABLE}:7: `build.{key}` is not allowed on table 'turnaround', which dbt builds; "
        "dbt takes the order from `ref()` in the model"
    ]


def test_a_missing_model_names_the_expected_path(dbt_repo: Path):
    (dbt_repo / MODEL).unlink()
    assert rendered(dbt_repo) == [
        f"{TABLE}:2: model file models/agg_lab_turnaround__turnaround.sql does not exist in the folder of "
        "data product 'agg_lab_turnaround'; table 'turnaround' is built by dbt"
    ]


def test_the_model_name_follows_the_dbt_model_template(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{table}_v1"\n')
    assert "models/turnaround_v1.sql does not exist" in rendered(dbt_repo)[0]


def test_unknown_placeholder_in_the_dbt_model_template_fails(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{bogus}"\n')
    [message] = rendered(dbt_repo)
    assert message.startswith("datapatchbay.yaml:4: conventions.names.dbt_model: naming template")


def test_a_python_file_in_models_fails(dbt_repo: Path):
    write(dbt_repo, f"{DP}/models/staging/helper.py", "x = 1\n")
    assert rendered(dbt_repo) == [
        f"{DP}/models/staging/helper.py: a .py file in a data product's `models/` folder is read by dbt as a "
        "dbt Python model; move it to `src/`"
    ]


def test_a_python_table_still_needs_an_entrypoint(lab_repo: Path):
    write(lab_repo, TABLE, TABLE_YAML)
    assert rendered(lab_repo) == [
        f"{TABLE}: table 'turnaround' needs a `build` block with an `entrypoint`, because its executor is 'python'"
    ]
    write(lab_repo, TABLE, TABLE_YAML + "build:\n  params: {}\n")
    assert rendered(lab_repo) == [
        f"{TABLE}:6: table 'turnaround' needs a `build.entrypoint`, because its executor is 'python'"
    ]


def test_the_dbt_model_template_defaults_and_is_in_the_schema(lab_repo: Path):
    assert load_settings(lab_repo).values.conventions.names.dbt_model == "{dataproduct}__{table}"
    assert "dbt_model" in schemas.json_schema("root")["$defs"]["NamesConvention"]["properties"]


def dbt_call_of(repo: Path) -> DbtCall:
    loaded, _ = load_repo(repo)
    plans = plan_dataproducts(loaded, load_settings(repo))
    table = next(t for plan in plans for t in plan.tables if t.name == "turnaround")
    return DbtExecutor().call(table)


def test_the_dbt_executor_selects_the_models_folder_of_the_data_product(dbt_repo: Path):
    call = dbt_call_of(dbt_repo)
    assert call == DbtCall(select=PurePosixPath(f"{DP}/models"), project_dir="../..", profiles_dir="~/.dbt")


def test_the_dbt_settings_decide_where_the_project_and_profiles_are(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", "schema_version: 1\ndbt:\n  project_dir: /opt/dbt\n  profiles_dir: profiles\n")
    call = dbt_call_of(dbt_repo)
    assert (call.select, call.project_dir, call.profiles_dir) == (PurePosixPath(f"{DP}/models"), "/opt/dbt", "profiles")


def test_a_project_dir_inside_the_repo_makes_the_selection_relative_to_it(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", "schema_version: 1\ndbt:\n  project_dir: dataproducts\n")
    call = dbt_call_of(dbt_repo)
    assert (call.select, call.project_dir) == (PurePosixPath("agg_lab_turnaround/models"), "..")
