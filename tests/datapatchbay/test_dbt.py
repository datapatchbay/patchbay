from pathlib import Path, PurePosixPath

import pytest
from dbt_helpers import DP, MODEL, TABLE, TABLE_YAML, checked, rendered, write
from plan_helpers import plan_all

from datapatchbay import schemas
from datapatchbay.builtin.dbt_executor import DbtExecutor
from datapatchbay.cascade import resolve_cascade
from datapatchbay.loading import load_repo
from datapatchbay.plugins import DbtCall
from datapatchbay.settings import load_settings


@pytest.fixture
def dbt_repo(jaffle_repo: Path) -> Path:
    """The jaffle shop repo where the reader data product builds its table with dbt, set on the data product."""
    product = jaffle_repo / DP / "dataproduct.yaml"
    product.write_text(product.read_text() + "executor: dbt\n")
    write(jaffle_repo, TABLE, TABLE_YAML)
    write(jaffle_repo, MODEL, "select 1 as days\n")
    return jaffle_repo


def test_a_table_built_by_dbt_needs_no_build_block_and_its_model(dbt_repo: Path):
    assert checked(dbt_repo) == []


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
    assert checked(tmp_path) == []


def test_the_nearest_executor_wins(dbt_repo: Path):
    write(dbt_repo, TABLE, TABLE_YAML + "build:\n  executor: python\n  entrypoint: src/turnaround.py:build\n")
    (dbt_repo / MODEL).unlink()
    assert checked(dbt_repo) == []
    repo, _ = load_repo(dbt_repo)
    product = next(p for p in repo.dataproducts if p.folder == "agg_order_turnaround")
    resolved = resolve_cascade(repo, load_settings(dbt_repo)).for_table(product.outputs[0].tables[0])["executor"]
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
        f"{TABLE}:2: model file models/agg_order_turnaround__turnaround.sql does not exist in the folder of "
        "data product 'agg_order_turnaround'; table 'turnaround' is built by dbt"
    ]


def test_the_model_name_follows_the_dbt_model_template(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{table}_v1"\n')
    assert "models/turnaround_v1.sql does not exist" in rendered(dbt_repo)[0]


def test_a_rendered_model_name_that_is_not_a_plain_identifier_fails(dbt_repo: Path):
    write(
        dbt_repo,
        "datapatchbay.yaml",
        'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{dataproduct}/{table}"\n',
    )
    [message] = rendered(dbt_repo)
    assert message.startswith(f"{TABLE}:2: ")
    assert "'agg_order_turnaround/turnaround'" in message
    assert "plain identifier" in message


def _second_dbt_product(repo: Path) -> None:
    folder = "dataproducts/agg_other"
    write(
        repo,
        f"{folder}/dataproduct.yaml",
        "schema_version: 1\nname: other\nkind: aggregate\nowner: Ann\noutputs: [agg_other]\nexecutor: dbt\n",
    )
    write(repo, f"{folder}/outputs/agg_other/port.yaml", "schema_version: 1\nkind: schema\n")
    write(repo, f"{folder}/outputs/agg_other/turnaround.yaml", TABLE_YAML)


def test_two_tables_with_the_same_rendered_model_name_fail(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{table}"\n')
    write(dbt_repo, f"{DP}/models/turnaround.sql", "select 1 as days\n")
    _second_dbt_product(dbt_repo)
    write(dbt_repo, "dataproducts/agg_other/models/turnaround.sql", "select 1 as days\n")
    [message] = checked(dbt_repo)
    assert message.startswith("dataproducts/agg_other/outputs/agg_other/turnaround.yaml:2: ")
    assert "dbt model name 'turnaround' is already used by " + TABLE in message
    assert "unique across the repo, whatever their case" in message


def test_model_names_that_differ_only_in_case_collide(dbt_repo: Path):
    write(dbt_repo, "datapatchbay.yaml", 'schema_version: 1\nconventions:\n  names:\n    dbt_model: "{table}"\n')
    write(dbt_repo, f"{DP}/models/turnaround.sql", "select 1 as days\n")
    _second_dbt_product(dbt_repo)
    write(
        dbt_repo,
        "dataproducts/agg_other/outputs/agg_other/turnaround.yaml",
        TABLE_YAML.replace("turnaround", "Turnaround", 1),
    )
    write(dbt_repo, "dataproducts/agg_other/models/Turnaround.sql", "select 1 as days\n")
    assert any("already used by " + TABLE in message for message in checked(dbt_repo))


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


def test_a_python_table_still_needs_an_entrypoint(jaffle_repo: Path):
    write(jaffle_repo, TABLE, TABLE_YAML)
    assert rendered(jaffle_repo) == [
        f"{TABLE}: table 'turnaround' needs a `build` block with an `entrypoint`, because its executor is 'python'"
    ]
    write(jaffle_repo, TABLE, TABLE_YAML + "build:\n  params: {}\n")
    assert rendered(jaffle_repo) == [
        f"{TABLE}:6: table 'turnaround' needs a `build.entrypoint`, because its executor is 'python'"
    ]


def test_the_dbt_model_template_defaults_and_is_in_the_schema(jaffle_repo: Path):
    assert load_settings(jaffle_repo).values.conventions.names.dbt_model == "{dataproduct}__{table}"
    assert "dbt_model" in schemas.json_schema("root")["$defs"]["NamesConvention"]["properties"]


def dbt_call_of(repo: Path) -> DbtCall:
    loaded, _ = load_repo(repo)
    plans = plan_all(loaded, repo)
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
    assert (call.select, call.project_dir) == (PurePosixPath("agg_order_turnaround/models"), "..")
