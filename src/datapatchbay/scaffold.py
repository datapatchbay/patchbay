"""Scaffolding a data product folder that follows the conventions (`dpb new`)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from datapatchbay.errors import DatapatchbayError
from datapatchbay.models.base import SCHEMA_VERSION
from datapatchbay.models.port import check_cron
from datapatchbay.naming import derive_names, is_snake_case
from datapatchbay.repo import DATAPRODUCT_FILE, DATAPRODUCTS_DIR
from datapatchbay.settings import ResolvedConventions
from datapatchbay.yamlio import dump_mapping

DEFAULT_SCHEDULE = "0 5 * * *"
"""The schedule of the private port when none is given: every day at 05:00."""

_STUB = '''"""Build code of the table `{table}`."""


def build() -> None:
    """Build the table `{table}`. Replace this stub with the code that writes it to the warehouse."""
    raise NotImplementedError("write the build code of the table '{table}'")
'''


class ScaffoldError(DatapatchbayError):
    """Raised when a data product cannot be scaffolded: missing or invalid answers, or a folder that exists."""


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
    """

    name: str
    kind: str
    owner: str
    domain: str | None = None
    technical_owner: str | None = None
    source: str | None = None
    schedule: str = DEFAULT_SCHEDULE


def missing_answers(conventions: ResolvedConventions, answers: Mapping[str, str]) -> list[str]:
    """List the required answers that are empty: `name`, `kind`, `owner` and, with declared domains, `domain`."""
    required = ["name", "kind", "owner"]
    if conventions.domains:
        required.append("domain")
    return [key for key in required if not answers.get(key)]


def check_answers(conventions: ResolvedConventions, new: NewDataProduct) -> None:
    """Check the answers against the conventions.

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
    if problems:
        raise ScaffoldError("\n".join(problems))


def _yaml(data: dict[str, Any]) -> str:
    return dump_mapping(CommentedMap({"schema_version": SCHEMA_VERSION, **data}))


def _table(name: str, description: str, needs: list[str]) -> str:
    build: dict[str, Any] = {"entrypoint": f"src/{name}.py:build"}
    if needs:
        build["needs"] = needs
    column = {"name": "id", "type": "text", "description": "Identifier of the row.", "rules": ["not_null", "unique"]}
    return _yaml({"name": name, "description": description, "columns": [column], "build": build})


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
    if new.source is not None:
        product["inputs"] = [names.private_port]
    product["outputs"] = [names.output_port]

    files = {f"{folder}/{DATAPRODUCT_FILE}": _yaml(product)}
    tables = ["example"]
    if new.source is not None:
        private = f"{folder}/inputs/{names.private_port}"
        files[f"{private}/port.yaml"] = _yaml(
            {"kind": "schema", "source": new.source, "schedule": DoubleQuotedScalarString(new.schedule)}
        )
        files[f"{private}/ingested.yaml"] = _table("ingested", f"Data delivered by {new.source}, as received.", [])
        tables.insert(0, "ingested")
    output = f"{folder}/outputs/{names.output_port}"
    files[f"{output}/port.yaml"] = _yaml({"kind": "schema"})
    needs = ["ingested"] if new.source is not None else []
    files[f"{output}/example.yaml"] = _table("example", "Example table; rename it and describe one row.", needs)
    for table in tables:
        files[f"{folder}/src/{table}.py"] = _STUB.format(table=table)
    return files


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
