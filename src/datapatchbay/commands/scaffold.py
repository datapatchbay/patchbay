"""Scaffolding a data product folder that follows the conventions (`dpb new`)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from datapatchbay.errors import DatapatchbayError
from datapatchbay.files.repo import DATAPRODUCT_FILE, DATAPRODUCTS_DIR
from datapatchbay.files.yamlio import dump_mapping
from datapatchbay.models.base import SCHEMA_VERSION
from datapatchbay.models.port import check_cron
from datapatchbay.plugins import NewTable, ScaffoldedTable, ScaffoldsTables
from datapatchbay.plugins.registry import load_plugin
from datapatchbay.settings.effective import ResolvedConventions
from datapatchbay.settings.naming import derive_names, is_snake_case

DEFAULT_SCHEDULE = "0 5 * * *"
"""The schedule of the private port when none is given: every day at 05:00."""


class ScaffoldError(DatapatchbayError):
    """Raised when a data product cannot be scaffolded: missing or invalid answers, or a folder that exists."""


@dataclass(frozen=True, slots=True)
class ImportedTable:
    """A table taken from outside, for `dpb new` to write as a table file.

    Attributes:
        name: Name of the table.
        description: The description, or `None`.
        columns: The columns as the table file writes them.
        files: Files of the data product the table needs, by path relative to its folder, such as its model.
    """

    name: str
    description: str | None
    columns: list[dict[str, Any]]
    files: Mapping[str, str]


class ImportedTables(Protocol):
    """Tables that an existing project provides, instead of the example (an option such as `--from-dbt`).

    Attributes:
        option: The command line option that gave them, for messages.
        executor: The executor that builds the data product, whatever the repo's executor.
    """

    @property
    def option(self) -> str: ...

    @property
    def executor(self) -> str: ...

    def problems(self, conventions: ResolvedConventions, new: "NewDataProduct") -> Sequence[str]:
        """Return what stops the tables from being imported under the conventions."""
        ...

    def tables(
        self, conventions: ResolvedConventions, new: "NewDataProduct", dataproduct: str
    ) -> Sequence[ImportedTable]:
        """Return the tables to write, for the data product folder named `dataproduct`."""
        ...


@dataclass(frozen=True, slots=True)
class NewDataProduct:
    """The answers `dpb new` needs to scaffold a data product.

    Attributes:
        name: The bare name, written without the prefix of its kind.
        kind: One of the declared kinds.
        owner: The person accountable for the data product.
        domain: The business area, or `None` when not given.
        technical_owner: The person who builds the data product, or `None` when not given.
        source: The source that feeds a private input port, or `None` for a data product without one.
        schedule: The cron expression of the source's deliveries; only used with a `source`.
        executor: The effective executor, which writes the stub of each new table.
        imported: Tables of an existing project (`--from-dbt`): the tables come from it instead of the example, and
            the data product is built by its executor whatever the repo's executor.
    """

    name: str
    kind: str
    owner: str
    executor: str
    domain: str | None = None
    technical_owner: str | None = None
    source: str | None = None
    schedule: str = DEFAULT_SCHEDULE
    imported: ImportedTables | None = None


def missing_answers(conventions: ResolvedConventions, answers: Mapping[str, str]) -> list[str]:
    """List the required answers that are empty: `name`, `kind`, `owner` and, with declared domains, `domain`.

    Args:
        conventions: The conventions in the effective settings; declared domains make `domain` required.
        answers: The answers by key, with an empty string for a value not given.

    Returns:
        The keys of the missing answers, in the order they are asked.
    """
    required = ["name", "kind", "owner"]
    if conventions.domains:
        required.append("domain")
    return [key for key in required if not answers.get(key)]


def check_answers(conventions: ResolvedConventions, new: NewDataProduct) -> None:
    """Check the answers against the conventions.

    Args:
        conventions: The conventions in the effective settings.
        new: The answers to check.

    Raises:
        ScaffoldError: Listing every problem at once.
    """
    problems: list[str] = []
    if not is_snake_case(new.name):
        problems.append(f"name '{new.name}' must be snake_case")
    if new.kind not in conventions.kinds:
        problems.append(f"kind '{new.kind}' is not one of the declared kinds: {', '.join(conventions.kinds)}")
    if conventions.domains and new.domain not in conventions.domains:
        problems.append(f"domain '{new.domain}' is not one of the declared domains: {', '.join(conventions.domains)}")
    if new.source is not None:
        try:
            check_cron(new.schedule)
        except ValueError as exc:
            problems.append(str(exc))
    if new.imported is not None:
        if new.source is not None:
            problems.append(
                f"--source cannot be combined with {new.imported.option}: the imported models are the tables"
            )
        if not problems:  # the names need a valid kind
            problems.extend(new.imported.problems(conventions, new))
    if problems:
        raise ScaffoldError("\n".join(problems))


def _yaml(data: dict[str, Any]) -> str:
    return dump_mapping(CommentedMap({"schema_version": SCHEMA_VERSION, **data}))


def _table(name: str, description: str, build: Mapping[str, Any] | None) -> str:
    column = {"name": "id", "type": "text", "description": "Identifier of the row.", "rules": ["not_null", "unique"]}
    table: dict[str, Any] = {"name": name, "description": description, "columns": [column]}
    if build is not None:  # an executor that builds from its own files needs no block
        table["build"] = dict(build)
    return _yaml(table)


def _executor(name: str) -> ScaffoldsTables:
    executor = load_plugin("executor", name)
    if not isinstance(executor, ScaffoldsTables):
        raise ScaffoldError(f"executor '{name}' cannot scaffold tables for `dpb new`")
    return executor


def render_files(conventions: ResolvedConventions, new: NewDataProduct) -> dict[str, str]:
    """Render every file of the new data product.

    Args:
        conventions: The conventions in the effective settings; their naming templates name the folder and ports.
        new: The answers; they must pass `check_answers`.

    Returns:
        File contents by path relative to the repo root, in a stable order.
    """
    names = derive_names(conventions, name=new.name, kind_name=new.kind)
    folder = f"{DATAPRODUCTS_DIR}/{names.dataproduct}"

    product: dict[str, Any] = {"name": new.name, "kind": new.kind}
    if new.domain:
        product["domain"] = new.domain
    product["owner"] = new.owner
    if new.technical_owner:
        product["technical_owner"] = new.technical_owner
    if new.imported is not None:
        product["executor"] = new.imported.executor
    if new.source is not None:
        product["inputs"] = [names.private_port]
    product["outputs"] = [names.output_port]

    files = {f"{folder}/{DATAPRODUCT_FILE}": _yaml(product)}
    if new.imported is not None:
        return files | _imported_files(conventions, new, names.dataproduct, names.output_port, product_folder=folder)
    executor = _executor(new.executor)
    ingested = None
    if new.source is not None:
        private = f"{folder}/inputs/{names.private_port}"
        files[f"{private}/port.yaml"] = _yaml(
            {"kind": "schema", "source": new.source, "schedule": DoubleQuotedScalarString(new.schedule)}
        )
        ingested = _scaffolded(executor, conventions, new, names.dataproduct, "ingested", ())
        files[f"{private}/ingested.yaml"] = _table(
            "ingested", f"Data delivered by {new.source}, as received.", ingested.build
        )
    output = f"{folder}/outputs/{names.output_port}"
    files[f"{output}/port.yaml"] = _yaml({"kind": "schema"})
    needs = ("ingested",) if new.source is not None else ()
    example = _scaffolded(executor, conventions, new, names.dataproduct, "example", needs)
    files[f"{output}/example.yaml"] = _table("example", "Example table; rename it and describe one row.", example.build)
    for scaffolded in [ingested, example] if ingested else [example]:
        files |= {f"{folder}/{path}": text for path, text in scaffolded.files.items()}
    return files


def _scaffolded(
    executor: ScaffoldsTables,
    conventions: ResolvedConventions,
    new: NewDataProduct,
    dataproduct: str,
    table: str,
    needs: tuple[str, ...],
) -> ScaffoldedTable:
    return executor.scaffold_table(NewTable(table, needs, dataproduct, new.name, new.kind, conventions))


def scaffold(root: Path, conventions: ResolvedConventions, new: NewDataProduct) -> list[Path]:
    """Create the data product folder under `root`.

    Args:
        root: The repo root.
        conventions: The conventions in the effective settings.
        new: The answers.

    Returns:
        The created files, relative to `root`, in a stable order.

    Raises:
        ScaffoldError: If an answer is invalid or the data product folder already exists. Nothing is written then.
    """
    check_answers(conventions, new)
    files = render_files(conventions, new)
    folder = derive_names(conventions, name=new.name, kind_name=new.kind).dataproduct
    if (root / DATAPRODUCTS_DIR / folder).exists():
        raise ScaffoldError(f"{DATAPRODUCTS_DIR}/{folder} already exists; dpb new never overwrites a data product")
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return [Path(relative) for relative in files]


def _imported_files(
    conventions: ResolvedConventions, new: NewDataProduct, dataproduct: str, output_port: str, *, product_folder: str
) -> dict[str, str]:
    """The output port and a table file per imported table, with the files the executor needs for each."""
    if new.imported is None:
        raise RuntimeError("no tables were imported")
    output = f"{product_folder}/outputs/{output_port}"
    files = {f"{output}/port.yaml": _yaml({"kind": "schema"})}
    for imported in new.imported.tables(conventions, new, dataproduct):
        table: dict[str, Any] = {"name": imported.name}
        if imported.description is not None:
            table["description"] = imported.description
        table["columns"] = imported.columns
        files[f"{output}/{imported.name}.yaml"] = _yaml(table)
        files |= {f"{product_folder}/{path}": text for path, text in imported.files.items()}
    return files
