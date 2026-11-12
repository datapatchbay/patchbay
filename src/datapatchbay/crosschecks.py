"""Rules that span files: port lists against folders, links between ports, and tables within a data product.

Each check reads the loaded `Repo` and returns problems. A check skips what depends on a file that failed to load,
because the loader already reported that file.
"""

from collections.abc import Iterator
from typing import Literal

from datapatchbay.models import DataProductInputPortFile, OutputPortFile, ProductReader
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Port, Repo, Table


def check_repo(repo: Repo) -> list[Problem]:
    """Run every cross-file check and return all the problems found."""
    problems: list[Problem] = []
    for dataproduct in repo.dataproducts:
        problems.extend(_check_port_lists(dataproduct))
        problems.extend(_check_table_counts(dataproduct))
        problems.extend(_check_table_names(dataproduct))
        problems.extend(_check_builds(dataproduct))
        problems.extend(_check_reads(repo, dataproduct))
        problems.extend(_check_product_readers(repo, dataproduct))
    return problems


def _check_port_lists(dataproduct: DataProduct) -> Iterator[Problem]:
    """The port lists in `dataproduct.yaml` and the folders under `inputs/` and `outputs/` agree both ways."""
    file = dataproduct.file
    for direction in ("inputs", "outputs"):
        listed: list[str] = getattr(file.model, direction)
        folders = dataproduct.port_folders[direction]
        seen: set[str] = set()
        for index, name in enumerate(listed):
            line = file.line(direction, index)
            if name in seen:
                yield Problem(file.path, line, f"port '{name}' is listed more than once in `{direction}`")
            seen.add(name)
            if name not in folders:
                yield Problem(
                    file.path, line, f"port '{name}' is listed in `{direction}` but has no folder {direction}/{name}"
                )
        for folder in folders:
            if folder not in listed:
                yield Problem(
                    file.path, file.line(direction), f"folder {direction}/{folder} is not listed in `{direction}`"
                )


def _check_table_counts(dataproduct: DataProduct) -> Iterator[Problem]:
    """A `table` port has exactly one table file; an input port that reads a data product has none."""
    for port in dataproduct.ports:
        model = port.file.model
        if isinstance(model, DataProductInputPortFile):
            for path in port.table_files:
                yield Problem(
                    path, 1, f"input port '{port.name}' reads another data product and has no table files; remove it"
                )
        elif model.kind == "table" and len(port.table_files) != 1:
            yield Problem(
                port.file.path,
                port.file.line("kind"),
                f"port '{port.name}' is of kind table and needs exactly one table file, found {len(port.table_files)}",
            )


def _check_table_names(dataproduct: DataProduct) -> Iterator[Problem]:
    first: dict[str, Table] = {}
    for table in dataproduct.tables:
        if table.name in first:
            yield Problem(
                table.file.path,
                table.file.line("name"),
                f"table name '{table.name}' is already used by {first[table.name].file.path}; "
                "table names are unique within a data product",
            )
        else:
            first[table.name] = table


def _check_builds(dataproduct: DataProduct) -> Iterator[Problem]:
    """Entrypoints exist inside the data product; `needs` names its tables and has no cycle."""
    root = dataproduct.directory.resolve()
    tables: dict[str, Table] = {}
    for table in dataproduct.tables:
        tables.setdefault(table.name, table)

    for table in dataproduct.tables:
        file = table.file
        build = file.model.build
        if build is None:
            continue  # built by dbt, or reported by the build checks
        if (path_text := table.entrypoint_path) is not None:
            target = (dataproduct.directory / path_text).resolve()
            line = file.line("build", "entrypoint")
            if not target.is_relative_to(root):
                yield Problem(file.path, line, f"entrypoint file {path_text} must be inside the data product folder")
            elif not target.is_file():
                yield Problem(file.path, line, f"entrypoint file {path_text} does not exist in the data product folder")

        if not dataproduct.has_unreadable_tables:
            for index, need in enumerate(table.needs):
                if need not in tables:
                    yield Problem(
                        file.path,
                        file.line("build", "needs", index),
                        f"'{need}' in `needs` is not a table of data product '{dataproduct.folder}'",
                    )
    yield from _needs_cycles(tables)


def _needs_cycles(tables: dict[str, Table]) -> Iterator[Problem]:
    state: dict[str, str] = {}  # missing: not visited, "open": on the current path, "done": finished
    path: list[str] = []
    reported: set[frozenset[str]] = set()
    found: list[Problem] = []

    def visit(name: str) -> None:
        state[name] = "open"
        path.append(name)
        file = tables[name].file
        for index, need in enumerate(tables[name].needs):
            if need not in tables:
                continue
            if state.get(need) == "open":
                cycle = path[path.index(need) :]
                if frozenset(cycle) not in reported:
                    reported.add(frozenset(cycle))
                    arrow = " -> ".join([*cycle, need])
                    found.append(
                        Problem(file.path, file.line("build", "needs", index), f"`needs` forms a cycle: {arrow}")
                    )
            elif need not in state:
                visit(need)
        path.pop()
        state[name] = "done"

    for name in tables:
        if name not in state:
            visit(name)
    yield from found


def _check_reads(repo: Repo, dataproduct: DataProduct) -> Iterator[Problem]:
    """`from` names an output port of another data product, which lists this data product as a reader."""
    for port in dataproduct.inputs:
        model = port.file.model
        if not isinstance(model, DataProductInputPortFile):
            continue
        line = port.file.line("from")
        target = model.from_
        if target in {output.name for output in dataproduct.outputs} | set(dataproduct.port_folders["outputs"]):
            yield Problem(
                port.file.path,
                line,
                f"'{target}' is an output port of this data product; `from` must name an "
                "output port of another data product",
            )
            continue
        found = find_other_output(repo, dataproduct, target)
        if found is None:
            yield Problem(
                port.file.path, line, f"'{target}' is not an output port of another data product in this repo"
            )
            continue
        if found == "unreadable" or not isinstance(found.file.model, OutputPortFile):
            continue  # the owning files failed to load; their problems are reported already
        readers = found.file.model.access.readers
        if not any(isinstance(r, ProductReader) and r.product == dataproduct.folder for r in readers):
            yield Problem(
                port.file.path,
                line,
                f"data product '{dataproduct.folder}' reads '{target}' but is not listed in the readers of that port; "
                f"add `- product: {dataproduct.folder}` under access.readers in {found.file.path}",
            )


def _check_product_readers(repo: Repo, dataproduct: DataProduct) -> Iterator[Problem]:
    """A `product:` reader of an output port names a data product in this repo."""
    if len(repo.dataproducts) != repo.dataproduct_dirs:
        return  # some data products failed to load; their problems are reported already, and one may be the reader
    folders = {other.folder for other in repo.dataproducts}
    for port in dataproduct.outputs:
        model = port.file.model
        if not isinstance(model, OutputPortFile):
            continue
        for index, reader in enumerate(model.access.readers):
            if isinstance(reader, ProductReader) and reader.product not in folders:
                yield Problem(
                    port.file.path,
                    port.file.line("access", "readers", index),
                    f"reader `product: {reader.product}` is not a data product in this repo",
                )


def find_other_output(repo: Repo, reader: DataProduct, name: str) -> Port | Literal["unreadable"] | None:
    """Find an output port of another data product.

    Returns `None` when there is none, and `"unreadable"` when the folder exists but its files failed to load.
    """
    for other in repo.dataproducts:
        if other is reader:
            continue
        for port in other.outputs:
            if port.name == name:
                return port
        if name in other.port_folders["outputs"]:
            return "unreadable"
    return "unreadable" if name in repo.unloaded_output_ports else None
