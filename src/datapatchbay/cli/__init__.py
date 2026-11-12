"""The `dpb` command line: a thin layer over the package."""

from typing import Any

import typer
from typer.core import TyperGroup

from datapatchbay.cli.config import config
from datapatchbay.cli.generate import generate
from datapatchbay.cli.new import new
from datapatchbay.cli.overview import describe, list_command
from datapatchbay.cli.schema import schema
from datapatchbay.cli.upgrade import upgrade
from datapatchbay.cli.validate import validate
from datapatchbay.errors import DatapatchbayError


class _Group(TyperGroup):
    """The one place that catches the package base exception and turns it into a message and exit code 2."""

    # typer.Context is the public name of the context class that TyperGroup.invoke is annotated with.
    def invoke(self, ctx: typer.Context) -> Any:  # ty: ignore[incompatible-method-override]
        try:
            return super().invoke(ctx)
        except DatapatchbayError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc


app = typer.Typer(
    name="dpb",
    cls=_Group,
    help="Data products as code: declare owners, ports and freshness in YAML.",
    no_args_is_help=True,
    add_completion=False,
)
app.command()(new)
app.command()(validate)
app.command()(config)
app.command()(upgrade)
app.command("list")(list_command)
app.command()(describe)
app.command()(schema)
app.command()(generate)


@app.callback()
def _root() -> None:
    """Keep `dpb` a command group, so subcommands keep their names as more arrive."""


def main() -> None:
    """Run the `dpb` command."""
    app()
