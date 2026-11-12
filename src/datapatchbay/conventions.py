"""Checks of the conventions in the effective settings: kinds, domains, naming templates and snake_case names."""

from collections.abc import Iterator
from pathlib import PurePosixPath

from ruamel.yaml.comments import CommentedMap

from datapatchbay.models import DataProductInputPortFile
from datapatchbay.naming import (
    DBT_MODEL_PLACEHOLDERS,
    DerivedNames,
    NamingTemplateError,
    check_template,
    derive_names,
    is_snake_case,
)
from datapatchbay.problems import Problem
from datapatchbay.repo import ROOT_FILE
from datapatchbay.repomodel import DataProduct, Port, Repo
from datapatchbay.settings import EffectiveSettings
from datapatchbay.yamlio import line_of

_TEMPLATE_KEYS = ("dataproduct", "output_port", "private_port", "role", "dbt_model")


def check_conventions(repo: Repo, settings: EffectiveSettings, root_data: CommentedMap) -> list[Problem]:
    """Check every data product against the kinds, domains and naming templates in the effective settings.

    Args:
        repo: The loaded repo.
        settings: The effective settings.
        root_data: The raw `datapatchbay.yaml`, so template problems can name a line.

    Returns:
        All the problems found. When a naming template is invalid, only that is reported, because no name can be
        derived from it.
    """
    template_problems = list(_check_templates(settings, root_data))
    if template_problems:
        return template_problems

    problems: list[Problem] = []
    owners: dict[str, DataProduct] = {}
    port_owners: dict[str, Port] = {}
    for dataproduct in repo.dataproducts:
        problems.extend(_check_snake_case(dataproduct))
        problems.extend(_check_domain(dataproduct, settings))
        derived = _derive(dataproduct, settings)
        if derived is None:
            problems.append(_unknown_kind(dataproduct, settings))
            continue
        problems.extend(_check_derived_names(dataproduct, derived))
        problems.extend(_check_unique(dataproduct, derived, owners, port_owners))
    return problems


def _check_templates(settings: EffectiveSettings, root_data: CommentedMap) -> Iterator[Problem]:
    for key in _TEMPLATE_KEYS:
        template: str = getattr(settings.values.conventions.names, key)
        try:
            check_template(template, DBT_MODEL_PLACEHOLDERS if key == "dbt_model" else ())
        except NamingTemplateError as error:
            line = line_of(root_data, ("conventions", "names", key))
            yield Problem(PurePosixPath(ROOT_FILE), line, f"conventions.names.{key}: {error}")


def _derive(dataproduct: DataProduct, settings: EffectiveSettings) -> DerivedNames | None:
    model = dataproduct.file.model
    if model.kind not in settings.values.conventions.kinds:
        return None
    return derive_names(settings.values.conventions, name=model.name, kind_name=model.kind)


def _unknown_kind(dataproduct: DataProduct, settings: EffectiveSettings) -> Problem:
    file = dataproduct.file
    declared = ", ".join(settings.values.conventions.kinds) or "none"
    return Problem(
        file.path,
        file.line("kind"),
        f"kind '{file.model.kind}' is not one of the kinds in the conventions; declared kinds: {declared}",
    )


def _check_domain(dataproduct: DataProduct, settings: EffectiveSettings) -> Iterator[Problem]:
    file = dataproduct.file
    domains = settings.values.conventions.domains
    if domains and file.model.domain is not None and file.model.domain not in domains:
        yield Problem(
            file.path,
            file.line("domain"),
            f"domain '{file.model.domain}' is not one of the domains in the conventions; declared domains: "
            f"{', '.join(domains)}",
        )


def _check_snake_case(dataproduct: DataProduct) -> Iterator[Problem]:
    file = dataproduct.file
    if not is_snake_case(file.model.name):
        yield Problem(file.path, file.line("name"), f"data product name '{file.model.name}' must be snake_case")
    for port in dataproduct.ports:
        if not is_snake_case(port.name):
            yield Problem(*_port_position(dataproduct, port), f"port name '{port.name}' must be snake_case")
    for table in dataproduct.tables:
        table_file = table.file
        if not is_snake_case(table.name):
            yield Problem(table_file.path, table_file.line("name"), f"table name '{table.name}' must be snake_case")
        for index, column in enumerate(table_file.model.columns):
            if not is_snake_case(column.name):
                yield Problem(
                    table_file.path,
                    table_file.line("columns", index, "name"),
                    f"column name '{column.name}' must be snake_case",
                )


def _port_position(dataproduct: DataProduct, port: Port) -> tuple[PurePosixPath, int]:
    """Where a port name is written: its entry in the port list of `dataproduct.yaml`, else its `port.yaml`."""
    listed: list[str] = getattr(dataproduct.file.model, port.direction)
    if port.name in listed:
        return dataproduct.file.path, dataproduct.file.line(port.direction, listed.index(port.name))
    return port.file.path, 1


def _check_derived_names(dataproduct: DataProduct, derived: DerivedNames) -> Iterator[Problem]:
    file = dataproduct.file
    if dataproduct.folder != derived.dataproduct:
        yield Problem(
            file.path,
            file.line("name"),
            f"data product folder '{dataproduct.folder}' must be named '{derived.dataproduct}', "
            "which the naming template produces from `name` and `kind`",
        )
    for port in dataproduct.outputs:
        yield from _check_port_name(dataproduct, port, "default output port", derived.output_port, derived)
    for port in dataproduct.inputs:
        if isinstance(port.file.model, DataProductInputPortFile):
            continue  # Named after the output port it reads, which another data product owns.
        yield from _check_port_name(dataproduct, port, "private port", derived.private_port, derived)


def _check_port_name(
    dataproduct: DataProduct, port: Port, role: str, default: str, derived: DerivedNames
) -> Iterator[Problem]:
    """A port is the default one the template produces, or a further port that starts with the derived name."""
    if port.name == default or port.name.startswith(derived.dataproduct):
        return
    yield Problem(
        *_port_position(dataproduct, port),
        f"port '{port.name}' must be the {role} '{default}' or start with the data product's name "
        f"'{derived.dataproduct}'",
    )


def _check_unique(
    dataproduct: DataProduct,
    derived: DerivedNames,
    owners: dict[str, DataProduct],
    port_owners: dict[str, Port],
) -> Iterator[Problem]:
    file = dataproduct.file
    other = owners.setdefault(derived.dataproduct, dataproduct)
    if other is not dataproduct:
        yield Problem(
            file.path,
            file.line("name"),
            f"data product name '{derived.dataproduct}' is already used by {other.file.path}; "
            "derived names are unique across the repo",
        )
    for port in dataproduct.ports:
        if isinstance(port.file.model, DataProductInputPortFile):
            continue  # Shares the name of the output port it reads.
        first = port_owners.setdefault(port.name, port)
        if first is not port:
            yield Problem(
                *_port_position(dataproduct, port),
                f"port name '{port.name}' is already used by {first.file.path}; port names are unique across the repo",
            )
