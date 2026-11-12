"""Naming templates: rendering the derived names of a data product from its bare name and kind (ADR-0006)."""

import re
from dataclasses import dataclass

from datapatchbay.errors import DatapatchbayError
from datapatchbay.models.root import KindConvention
from datapatchbay.settings import ResolvedConventions

PLACEHOLDERS = ("name", "kind.prefix", "kind.name")
"""The placeholders a naming template may use."""

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")


class NamingTemplateError(DatapatchbayError):
    """Raised when a naming template cannot be rendered."""


@dataclass(frozen=True, slots=True)
class DerivedNames:
    """Every name a naming template produces for one data product."""

    dataproduct: str
    output_port: str
    private_port: str
    role: str


def is_snake_case(text: str) -> bool:
    """Return whether `text` is snake_case: lowercase letters and digits in words joined by single underscores."""
    return _SNAKE_CASE.fullmatch(text) is not None


def check_template(template: str) -> None:
    """Check that a naming template only uses known placeholders and has balanced braces.

    Raises:
        NamingTemplateError: If it does not; the message lists the placeholders available.
    """
    available = ", ".join(f"{{{placeholder}}}" for placeholder in PLACEHOLDERS)
    for match in _PLACEHOLDER.finditer(template):
        if match.group(1) not in PLACEHOLDERS:
            raise NamingTemplateError(
                f"naming template '{template}' uses unknown placeholder {{{match.group(1)}}}; available: {available}"
            )
    literal = _PLACEHOLDER.sub("", template)
    if "{" in literal or "}" in literal:
        raise NamingTemplateError(f"naming template '{template}' has an unmatched brace; available: {available}")


def render_name(template: str, *, name: str, kind_name: str, kind: KindConvention) -> str:
    """Render a naming template for a data product.

    Args:
        template: The naming template, for example `"{kind.prefix}_{name}"`.

    Keyword Args:
        name: The data product's bare name, for example `"ilab_orders"`.
        kind_name: The name of the data product's kind, for example `"source-aligned"`.
        kind: The convention of that kind, which holds its prefix.

    Returns:
        The rendered name.

    Raises:
        NamingTemplateError: If the template uses a placeholder that does not exist.
    """
    check_template(template)
    values = {"name": name, "kind.prefix": kind.prefix, "kind.name": kind_name}
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def derive_names(conventions: ResolvedConventions, *, name: str, kind_name: str) -> DerivedNames:
    """Render every naming template of the conventions for a data product.

    Raises:
        NamingTemplateError: If a template uses an unknown placeholder.
        KeyError: If `kind_name` is not one of the declared kinds.
    """
    kind = conventions.kinds[kind_name]
    templates = conventions.names

    def render(template: str) -> str:
        return render_name(template, name=name, kind_name=kind_name, kind=kind)

    return DerivedNames(
        dataproduct=render(templates.dataproduct),
        output_port=render(templates.output_port),
        private_port=render(templates.private_port),
        role=render(templates.role),
    )
