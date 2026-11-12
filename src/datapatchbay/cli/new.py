"""The `dpb new` command."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from datapatchbay.dbt import DBT_EXECUTOR
from datapatchbay.dbt_import import DEFAULT_TYPE, DbtImport, read_dbt_models
from datapatchbay.repo import find_repo_root
from datapatchbay.scaffold import DEFAULT_SCHEDULE, NewDataProduct, ScaffoldError, missing_answers, scaffold
from datapatchbay.settings import ResolvedConventions, load_settings

_QUESTIONS = {
    "name": "Name (without the kind prefix)",
    "kind": "Kind",
    "domain": "Domain",
    "owner": "Owner",
    "technical_owner": "Technical owner",
}


def _prompt(key: str, conventions: ResolvedConventions) -> str:
    """Ask for one answer. Optional answers can be left empty; required ones are asked again until given."""
    choices = {"kind": list(conventions.kinds), "domain": conventions.domains}.get(key, [])
    question = f"{_QUESTIONS[key]} ({', '.join(choices)})" if choices else _QUESTIONS[key]
    optional = key == "technical_owner" or (key == "domain" and not conventions.domains)
    if optional:
        return typer.prompt(question, default="", show_default=False)
    return typer.prompt(question)


def new(
    name: Annotated[str | None, typer.Option(help="Name of the data product, without the prefix of its kind.")] = None,
    kind: Annotated[str | None, typer.Option(help="Kind of the data product, from the declared kinds.")] = None,
    domain: Annotated[str | None, typer.Option(help="Business area of the data product.")] = None,
    owner: Annotated[str | None, typer.Option(help="The person accountable for the data product.")] = None,
    technical_owner: Annotated[
        str | None, typer.Option("--technical-owner", help="The person who builds the data product.")
    ] = None,
    source: Annotated[
        str | None, typer.Option(help="Source that feeds the data product; adds a private input port.")
    ] = None,
    schedule: Annotated[
        str, typer.Option(help="Cron expression of the source's deliveries; used with --source.")
    ] = DEFAULT_SCHEDULE,
    from_dbt: Annotated[
        Path | None,
        typer.Option(
            "--from-dbt",
            help="Folder with the models (.sql) and properties (.yml) of an existing dbt project: copies the models "
            "into the data product and writes a table file per model. The executor of the data product is dbt.",
        ),
    ] = None,
    no_input: Annotated[bool, typer.Option("--no-input", help="Never prompt; fail when a value is missing.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the created files as JSON on stdout.")] = False,
) -> None:
    """Scaffold a data product folder that follows the conventions."""
    root = find_repo_root(Path.cwd())
    settings = load_settings(root)
    conventions = settings.values.conventions
    given = {"name": name, "kind": kind, "domain": domain, "owner": owner, "technical_owner": technical_owner}
    answers = {key: value or "" for key, value in given.items()}
    if no_input:
        missing = missing_answers(conventions, answers)
        if missing:
            flags = ", ".join(f"--{key.replace('_', '-')}" for key in missing)
            raise ScaffoldError(f"missing values: {flags}; give them as flags or run without --no-input")
    else:
        for key, value in given.items():
            if value is None:
                answers[key] = _prompt(key, conventions)
    imported = read_dbt_models(from_dbt, default_severity=settings.values.severity) if from_dbt is not None else None
    created = scaffold(
        root,
        conventions,
        NewDataProduct(
            name=answers["name"],
            kind=answers["kind"],
            owner=answers["owner"],
            domain=answers["domain"] or None,
            technical_owner=answers["technical_owner"] or None,
            source=source,
            schedule=schedule,
            dbt=settings.values.executor == DBT_EXECUTOR,
            imported=imported,
        ),
    )
    if json_output:
        report: dict[str, object] = {"created": [path.as_posix() for path in created]}
        if imported is not None:
            report |= {key: [asdict(item) for item in items] for key, items in _left_out(imported).items()}
        typer.echo(json.dumps(report, indent=2))
    else:
        for path in created:
            typer.echo(f"created {path.as_posix()}")
        if imported is not None:
            _echo_left_out(imported)


def _left_out(imported: DbtImport) -> dict[str, list[Any]]:
    return {"unmapped_tests": imported.unmapped, "skipped": imported.skipped, "untyped_columns": imported.untyped}


def _echo_left_out(imported: DbtImport) -> None:
    for test in imported.unmapped:
        where = f"{test.model}.{test.column}" if test.column else test.model
        typer.echo(f"not imported: {where} {test.test}: {test.reason}")
    for skipped in imported.skipped:
        typer.echo(f"skipped model {skipped.model}: {skipped.reason}")
    for untyped in imported.untyped:
        typer.echo(f"no data_type: {untyped.model}.{untyped.column} is written as '{DEFAULT_TYPE}'; set the real type")
