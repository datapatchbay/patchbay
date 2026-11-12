"""The loaded repo: data products with their ports and tables, each keeping its file and line information.

Everything here has passed per-file schema validation. Files that failed are left out and reported as problems
by the loader; the `unreadable_*` fields record what is missing so that cross-file checks do not report false
problems about it.
"""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from ruamel.yaml.comments import CommentedMap

from datapatchbay.files.yamlio import line_of
from datapatchbay.models import DataProductFile, DataProductInputPortFile, PortFile, RootFile, TableFile


@dataclass(frozen=True, slots=True)
class LoadedFile[M]:
    """A file that passed schema validation, with the raw YAML so any key can be traced to its line.

    Attributes:
        path: The file, relative to the repo root and written with forward slashes.
        model: The validated content.
        data: The YAML as read, with position information.
    """

    path: PurePosixPath
    model: M
    data: CommentedMap

    def line(self, *location: str | int) -> int:
        """Return the 1-based line of a key or list item, such as `line("build", "needs", 0)`."""
        return line_of(self.data, location)


@dataclass(frozen=True, slots=True)
class Table:
    """A table of a port."""

    file: LoadedFile[TableFile]

    @property
    def name(self) -> str:
        """The table name from the table file."""
        return self.file.model.name

    @property
    def entrypoint(self) -> str | None:
        """The `build.entrypoint` as written (`path/to/file.py:function`), or `None` when the table sets none."""
        build = self.file.model.build
        return None if build is None else build.entrypoint

    @property
    def entrypoint_path(self) -> str | None:
        """The file part of the entrypoint, relative to the data product folder."""
        return None if self.entrypoint is None else self.entrypoint.rpartition(":")[0]

    @property
    def function(self) -> str | None:
        """The function part of the entrypoint."""
        return None if self.entrypoint is None else self.entrypoint.rpartition(":")[2]

    @property
    def needs(self) -> list[str]:
        """The tables of the same data product that must be built first."""
        build = self.file.model.build
        return [] if build is None else build.needs

    @property
    def params(self) -> dict[str, Any]:
        """The parameters passed to the entrypoint function."""
        build = self.file.model.build
        return {} if build is None else build.params


@dataclass(frozen=True, slots=True)
class Port:
    """A port of a data product: a folder under `inputs/` or `outputs/`.

    Attributes:
        name: The folder name, which is the port name.
        direction: Whether the folder is under `inputs/` or `outputs/`.
        file: The `port.yaml`.
        tables: The table files that passed validation, sorted by file name.
        table_files: Every table file on disk, whether or not it was valid.
    """

    name: str
    direction: Literal["inputs", "outputs"]
    file: LoadedFile[PortFile]
    tables: tuple[Table, ...]
    table_files: tuple[PurePosixPath, ...]

    @property
    def reads_port(self) -> str | None:
        """The output port this input port reads, or `None` when it is not fed by another data product."""
        model = self.file.model
        return model.from_ if isinstance(model, DataProductInputPortFile) else None

    @property
    def unreadable_table_count(self) -> int:
        """How many table files failed validation and are missing from `tables`."""
        if self.reads_port is not None:
            return 0
        return len(self.table_files) - len(self.tables)


@dataclass(frozen=True, slots=True)
class DataProduct:
    """A data product folder with its ports.

    Attributes:
        folder: The folder name, which is how other data products refer to it (`product:` readers).
        directory: The absolute path of the folder.
        file: The `dataproduct.yaml`.
        inputs: The input ports that passed validation, sorted by name.
        outputs: The output ports that passed validation, sorted by name.
        port_folders: Every port folder on disk, by direction, sorted.
    """

    folder: str
    directory: Path
    file: LoadedFile[DataProductFile]
    inputs: tuple[Port, ...]
    outputs: tuple[Port, ...]
    port_folders: dict[str, tuple[str, ...]]

    @property
    def ports(self) -> tuple[Port, ...]:
        """Input ports followed by output ports."""
        return (*self.inputs, *self.outputs)

    @property
    def tables(self) -> tuple[Table, ...]:
        """Every table of every port, inputs first."""
        return tuple(table for port in self.ports for table in port.tables)

    @property
    def has_unreadable_tables(self) -> bool:
        """Whether any table file of this data product failed validation."""
        return any(port.unreadable_table_count for port in self.ports)


@dataclass(slots=True)
class Repo:
    """Every data product that could be loaded.

    Attributes:
        root: The absolute repo root.
        root_file: The `datapatchbay.yaml`, read once, or `None` when it failed validation.
        dataproducts: The data products whose `dataproduct.yaml` passed validation, sorted by folder path.
        unloaded_output_ports: Output port folders of data products whose `dataproduct.yaml` failed validation.
        dataproduct_dirs: Every folder that holds a `dataproduct.yaml`.
    """

    root: Path
    root_file: LoadedFile[RootFile] | None = None
    dataproducts: list[DataProduct] = field(default_factory=list)
    unloaded_output_ports: frozenset[str] = frozenset()
    dataproduct_dirs: int = 0
