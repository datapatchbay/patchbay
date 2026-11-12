"""The core imports no integration (ADR-0024). Integrations are found through entry points, never by import.

The allow-list below is the debt of the core that still names dbt. It only shrinks: a new entry needs a reason that
is as good as these, and the pull request that removes the reason removes the entry.
"""

import ast
from pathlib import Path

import datapatchbay

PACKAGE = Path(datapatchbay.__file__).parent
INTEGRATIONS = "datapatchbay.integrations"

# core module (dotted, relative to datapatchbay) -> the integration modules it may import, with the reason.
ALLOWED: dict[str, dict[str, str]] = {
    "validation": {
        "dbt.layout": "validate runs check_dbt on the planned repo until the executor can contribute checks",
        "dbt.manifest": "validate reads the dbt manifest (check_dbt_reads) until the executor can contribute checks",
        "dbt.output": "validate diffs the committed dbt files (build_dbt_output) until the executor owns them",
    },
    "generate": {
        "dbt.output": "generate writes the committed dbt files (build_dbt_output) until the executor owns them",
    },
    "planning": {
        "dbt.layout": "the plan locates the models folder of a data product (MODELS_FOLDER)",
    },
    "pluginchecks": {
        "dbt.layout": "checks the dbt executor is installed when a table uses it (DBT_EXECUTOR)",
    },
    "scaffold": {
        "dbt.layout": "dpb new names the dbt executor (DBT_EXECUTOR)",
        "dbt.importer": "dpb new --from-dbt is a dbt-specific option, a documented exception",
    },
    "cli.new": {
        "dbt.layout": "dpb new names the dbt executor (DBT_EXECUTOR)",
        "dbt.importer": "dpb new --from-dbt is a dbt-specific option, a documented exception",
    },
}


def core_modules() -> list[Path]:
    return [p for p in sorted(PACKAGE.rglob("*.py")) if "integrations" not in p.relative_to(PACKAGE).parts]


def dotted(path: Path) -> str:
    parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def integration_imports(path: Path) -> set[str]:
    """The integration modules a file imports, relative to `datapatchbay.integrations`, at any nesting depth."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            # `from datapatchbay.integrations import dbt` imports the submodule `dbt`.
            names = [node.module] + (
                [f"{node.module}.{alias.name}" for alias in node.names] if node.module == INTEGRATIONS else []
            )
        else:
            continue
        for name in names:
            if name == INTEGRATIONS or name.startswith(INTEGRATIONS + "."):
                found.add(name.removeprefix(INTEGRATIONS).removeprefix("."))
    return found


def test_the_core_imports_only_the_integration_modules_on_the_allow_list():
    violations = []
    for path in core_modules():
        module = dotted(path)
        extra = {name for name in integration_imports(path) if name} - set(ALLOWED.get(module, {}))
        if extra:
            violations.append(f"{module} imports {sorted(extra)}")
    assert not violations, "the core must not import an integration (ADR-0024):\n" + "\n".join(violations)


def test_every_allow_list_entry_is_still_needed():
    modules = {dotted(path): integration_imports(path) for path in core_modules()}
    stale = [
        f"{module}: {name}"
        for module, allowed in ALLOWED.items()
        for name in allowed
        if name not in modules.get(module, set())
    ]
    assert not stale, "remove from ALLOWED, the import is gone:\n" + "\n".join(stale)
