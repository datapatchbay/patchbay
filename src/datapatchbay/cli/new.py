"""The `dpb new` command."""

import json
from pathlib import Path
from typing import Annotated

import typer

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
    no_input: Annotated[bool, typer.Option("--no-input", help="Never prompt; fail when a value is missing.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the created files as JSON on stdout.")] = False,
) -> None:
    """Scaffold a data product folder that follows the conventions."""
    root = find_repo_root(Path.cwd())
    conventions = load_settings(root).values.conventions
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
        ),
    )
    if json_output:
        typer.echo(json.dumps({"created": [path.as_posix() for path in created]}, indent=2))
    else:
        for path in created:
            typer.echo(f"created {path.as_posix()}")
