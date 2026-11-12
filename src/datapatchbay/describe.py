"""Overviews of a repo's data products: the list of all of them and the full description of one.

Both are built as plain JSON-ready data first; the text output is rendered from that same data, so `--json` and
the text always say the same.
"""

from typing import Any

from datapatchbay.cascade import ResolvedSetting, resolve_setting, resolve_settings
from datapatchbay.errors import DatapatchbayError
from datapatchbay.models import DataProductInputPortFile, OutputPortFile, ProductReader, SourceInputPortFile
from datapatchbay.repomodel import DataProduct, Port, Repo, Table
from datapatchbay.settings import EffectiveSettings

type Json = dict[str, Any]


class UnknownDataProductError(DatapatchbayError):
    """Raised when `dpb describe` is given a name that is not a data product of the repo."""


def _settings_json(resolved: dict[str, ResolvedSetting]) -> Json:
    return {name: setting.to_json() for name, setting in resolved.items()}


def list_dataproducts(repo: Repo) -> list[Json]:
    """Return one entry per data product with its kind, domain, owner and technical owner."""
    return [
        {
            "folder": product.folder,
            "name": product.file.model.name,
            "kind": product.file.model.kind,
            "domain": product.file.model.domain,
            "owner": product.file.model.owner,
            "technical_owner": product.file.model.technical_owner,
        }
        for product in repo.dataproducts
    ]


def find_dataproduct(repo: Repo, name: str) -> DataProduct:
    """Find a data product by its folder name or by its `name`.

    Raises:
        UnknownDataProductError: If there is none; the message names the data products that exist.
    """
    for product in repo.dataproducts:
        if name in (product.folder, product.file.model.name):
            return product
    existing = ", ".join(product.folder for product in repo.dataproducts)
    exists = f"the data products are: {existing}" if existing else "this repo has no data products"
    raise UnknownDataProductError(f"no data product named '{name}'; {exists}")


def _readers(port: Port) -> list[Json]:
    model = port.file.model
    if not isinstance(model, OutputPortFile):
        return []
    return [
        {"type": "product", "name": reader.product}
        if isinstance(reader, ProductReader)
        else {"type": "role", "name": reader}
        for reader in model.access.readers
    ]


def _read_by(repo: Repo, product: DataProduct, port: Port) -> list[str]:
    """The folders of the data products that have an input port reading this output port."""
    return sorted(
        {
            other.folder
            for other in repo.dataproducts
            if other is not product and any(inp.reads_port == port.name for inp in other.inputs)
        }
    )


def _rule_json(rule: Any, default: ResolvedSetting) -> Json:
    data: Json = rule.model_dump(exclude_none=True)
    data["severity"] = rule.severity or default.value
    data["severity_from"] = "rule" if rule.severity else default.level
    return data


def _table_json(settings: EffectiveSettings, product: DataProduct, port: Port, table: Table) -> Json:
    model = table.file.model
    resolved = resolve_settings(settings, dataproduct=product, port=port, table=table)
    severity = resolved["severity"]
    return {
        "name": model.name,
        "file": str(table.file.path),
        "description": model.description,
        "freshness_column": model.freshness_column,
        "columns": [
            {
                "name": column.name,
                "type": column.type,
                "description": column.description,
                "pii": column.pii,
                "rules": [_rule_json(rule, severity) for rule in column.rules],
            }
            for column in model.columns
        ],
        "rules": [_rule_json(rule, severity) for rule in model.rules],
        "entrypoint": model.build.entrypoint,
        "params": model.build.params,
        "needs": model.build.needs,
        "settings": _settings_json(resolved),
    }


def _port_json(repo: Repo, settings: EffectiveSettings, product: DataProduct, port: Port) -> Json:
    model = port.file.model
    data: Json = {
        "name": port.name,
        "file": str(port.file.path),
        "settings": _settings_json(resolve_settings(settings, dataproduct=product, port=port)),
    }
    if isinstance(model, DataProductInputPortFile):
        data["from"] = model.from_
    else:
        data["kind"] = model.kind
    if isinstance(model, SourceInputPortFile):
        data["source"] = model.source
        data["schedule"] = model.schedule
    if isinstance(model, OutputPortFile):
        data["freshness"] = model.freshness
        data["readers"] = _readers(port)
        data["pii_readers"] = model.access.pii_readers
        data["read_by"] = _read_by(repo, product, port)
    data["tables"] = [_table_json(settings, product, port, table) for table in port.tables]
    return data


def describe_dataproduct(repo: Repo, settings: EffectiveSettings, product: DataProduct) -> Json:
    """Describe one data product in full: ports, tables, columns, quality rules, freshness, readers and settings.

    Every setting is resolved at the level it applies to, with the level and file the value came from. The
    orchestrator applies to the whole data product, so it appears only at the top.
    """
    model = product.file.model
    resolved = resolve_settings(settings, dataproduct=product)
    resolved["orchestrator"] = resolve_setting("orchestrator", settings, dataproduct=product)
    return {
        "folder": product.folder,
        "name": model.name,
        "file": str(product.file.path),
        "kind": model.kind,
        "domain": model.domain,
        "owner": model.owner,
        "technical_owner": model.technical_owner,
        "description": model.description,
        "settings": _settings_json(resolved),
        "inputs": [_port_json(repo, settings, product, port) for port in product.inputs],
        "outputs": [_port_json(repo, settings, product, port) for port in product.outputs],
    }


def _setting_line(setting: Json, name: str) -> str:
    where = setting["file"] or setting["level"]
    value = "-" if setting["value"] is None else setting["value"]
    return f"{name}: {value}  ({setting['level']}{'' if setting['file'] is None else ', ' + where})"


def _settings_lines(settings: Json, indent: str) -> list[str]:
    return [indent + _setting_line(setting, name) for name, setting in settings.items()]


def render_list(entries: list[Json]) -> str:
    """Render the data product list as an aligned table."""
    header = ("DATA PRODUCT", "KIND", "DOMAIN", "OWNER", "TECHNICAL OWNER")
    rows = [(e["folder"], e["kind"], e["domain"] or "-", e["owner"], e["technical_owner"] or "-") for e in entries]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [header, *rows]
    )


def _rule_text(rule: Json) -> str:
    extra = {key: value for key, value in rule.items() if key not in ("rule", "severity", "severity_from")}
    detail = "".join(f" {key}={value}" for key, value in extra.items())
    return f"{rule['rule']}{detail} [{rule['severity']}, from {rule['severity_from']}]"


def _table_lines(table: Json) -> list[str]:
    lines = [f"      table {table['name']}  ({table['file']})"]
    if table["description"]:
        lines.append(f"        {table['description']}")
    if table["freshness_column"]:
        lines.append(f"        freshness column: {table['freshness_column']}")
    lines.append(
        f"        build: {table['entrypoint']}" + (f"  needs: {', '.join(table['needs'])}" if table["needs"] else "")
    )
    if table["params"]:
        lines.append(f"        params: {table['params']}")
    lines.extend(_settings_lines(table["settings"], "        "))
    lines.append("        columns:")
    for column in table["columns"]:
        pii = " pii" if column["pii"] else ""
        lines.append(f"          {column['name']} {column['type']}{pii}")
        lines.extend(f"            rule: {_rule_text(rule)}" for rule in column["rules"])
    lines.extend(f"        table rule: {_rule_text(rule)}" for rule in table["rules"])
    return lines


def _port_lines(port: Json, direction: str) -> list[str]:
    lines = [f"    {direction} port {port['name']}  ({port['file']})"]
    if "from" in port:
        lines.append(f"      reads: {port['from']}")
    else:
        lines.append(f"      kind: {port['kind']}")
    if "source" in port:
        lines.append(f"      source: {port['source']}  schedule: {port['schedule']}")
    if "freshness" in port:
        lines.append(f"      freshness: {port['freshness'] or '-'}")
        readers = [f"product:{r['name']}" if r["type"] == "product" else r["name"] for r in port["readers"]]
        lines.append(f"      readers: {', '.join(readers) or '-'}")
        lines.append(f"      pii readers: {', '.join(port['pii_readers']) or '-'}")
        lines.append(f"      read by: {', '.join(port['read_by']) or '-'}")
    lines.extend(_settings_lines(port["settings"], "      "))
    for table in port["tables"]:
        lines.extend(_table_lines(table))
    return lines


def render_description(description: Json) -> str:
    """Render a data product description as indented text."""
    lines = [
        f"{description['folder']}  ({description['file']})",
        f"  name: {description['name']}",
        f"  kind: {description['kind']}",
        f"  domain: {description['domain'] or '-'}",
        f"  owner: {description['owner']}",
        f"  technical owner: {description['technical_owner'] or '-'}",
    ]
    if description["description"]:
        lines.append(f"  {description['description']}")
    lines.append("  settings:")
    lines.extend(_settings_lines(description["settings"], "    "))
    for port in description["inputs"]:
        lines.extend(_port_lines(port, "input"))
    for port in description["outputs"]:
        lines.extend(_port_lines(port, "output"))
    return "\n".join(lines)
