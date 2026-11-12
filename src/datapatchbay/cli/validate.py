"""The `dpb validate` command."""

import json
from pathlib import Path
from typing import Annotated

import typer

from datapatchbay.repo import find_repo_root
from datapatchbay.validation import validate_repo


def validate(
    json_output: Annotated[bool, typer.Option("--json", help="Print the problems as JSON on stdout.")] = False,
) -> None:
    """Validate every data product against the schema. Exits non-zero when anything is wrong."""
    report = validate_repo(find_repo_root(Path.cwd()))
    if json_output:
        typer.echo(json.dumps(report.to_json(), indent=2))
    else:
        for problem in report.problems:
            typer.echo(problem.render(), err=True)
        if report.ok:
            typer.echo(f"ok: {report.dataproducts_checked} data product(s) valid")
        else:
            typer.echo(f"{len(report.problems)} problem(s) found", err=True)
    if not report.ok:
        raise typer.Exit(code=1)
