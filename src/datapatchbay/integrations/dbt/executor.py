"""The `dbt` executor: a table is built by a dbt model in the data product's `models/` folder (ADR-0015).

Besides the build call, the executor has the capabilities of `datapatchbay.plugins` that dbt needs, so the core names
no dbt: it checks the model files, produces and checks the committed dbt files, builds its tables in one `dbt build`
per data product, runs the quality rules itself as dbt data tests, and scaffolds the stub model for `dpb new`.
"""

from collections.abc import Sequence
from pathlib import PurePosixPath

from datapatchbay.integrations.dbt.layout import check_dbt_dataproduct, check_dbt_table, new_model_name
from datapatchbay.integrations.dbt.manifest import check_dbt_reads
from datapatchbay.integrations.dbt.output import DbtOutput, build_dbt_output
from datapatchbay.plugins import (
    CommandCall,
    NewTable,
    PlannedRepo,
    ScaffoldedTable,
    TablePlan,
    UnsupportedCombinationError,
)
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Repo, Table
from datapatchbay.settings import EffectiveSettings


class DbtExecutor:
    """Build a table with a dbt model, by a `dbt build` of the models of its data product."""

    batch_key = "dbt"
    call_type = CommandCall

    def __init__(self) -> None:
        self._model_names: dict[str, PurePosixPath] = {}

    def call(self, table: TablePlan) -> CommandCall:
        """Return the `dbt build` of the data product's `models/` folder, run in the dbt project.

        The command runs with the project as its working directory, so the project is `.`; the profiles folder is
        passed as set, and the runtime expands its leading `~`.

        Raises:
            UnsupportedCombinationError: If the plan holds no dbt location.
        """
        location = table.dbt
        if location is None:
            raise UnsupportedCombinationError(f"table '{table.name}' has no dbt location to build from")
        argv = (
            "dbt",
            "build",
            "--select",
            f"path:{location.models}",
            "--project-dir",
            ".",
            "--profiles-dir",
            location.profiles_dir,
        )
        return CommandCall(argv=argv, cwd=location.project_dir, home_args=(len(argv) - 1,))

    def committed_output(self, planned: PlannedRepo) -> DbtOutput:
        """Work out the dbt properties, sources and tests and the `dbt_project.yml` sync (ADR-0013)."""
        return build_dbt_output(planned)

    def check_dataproduct(self, repo: Repo, dataproduct: DataProduct) -> Sequence[Problem]:
        """Report a `.py` file in the `models/` folder, which dbt reads as a dbt Python model."""
        return list(check_dbt_dataproduct(repo, dataproduct))

    def check_table(self, settings: EffectiveSettings, dataproduct: DataProduct, table: Table) -> Sequence[Problem]:
        """Check the table file and the model file of a table dbt builds; model names are unique across the repo."""
        return list(check_dbt_table(settings, dataproduct, table, self._model_names))

    def check_plans(self, planned: PlannedRepo) -> Sequence[Problem]:
        """Compare what the dbt models read, from the manifest, with the input ports (ADR-0014)."""
        return check_dbt_reads(planned)

    def owns_quality_rules(self, table: TablePlan) -> bool:
        """Return `True`: the rules of a table dbt builds run as dbt data tests in `dbt build` (ADR-0019)."""
        return True

    def scaffold_table(self, table: NewTable) -> ScaffoldedTable:
        """Return a stub model in `models/`, reading the first table it needs; the table file needs no `build`."""
        model = new_model_name(table, table.name)
        if table.needs:
            sql = f"select id from {{{{ ref('{new_model_name(table, table.needs[0])}') }}}}\n"
        else:
            sql = "select cast(null as text) as id where false\n"
        return ScaffoldedTable(build=None, files={f"models/{model}.sql": sql})
