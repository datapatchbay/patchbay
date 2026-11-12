"""The core imports no integration, and an integration reaches shared code only through `datapatchbay.plugins`
(ADR-0024). Integrations are found through entry points, never by import.

The allow-list below holds the documented exceptions: `dpb new --from-dbt` is implemented in the dbt integration. It
only shrinks: a new entry needs a reason that is as good as this one.
"""

import ast
from pathlib import Path

import datapatchbay

PACKAGE = Path(datapatchbay.__file__).parent
INTEGRATIONS = "datapatchbay.integrations"

# core module (dotted, relative to datapatchbay) -> the integration modules it may import, with the reason.
ALLOWED: dict[str, dict[str, str]] = {
    "cli.new": {
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


# Folders that start with an underscore hold code shared by several integrations; each is open to named integrations.
SHARED_INTEGRATION_FOLDERS: dict[str, set[str]] = {
    "_container": {"docker", "kubernetes"},
}


def integration_modules() -> list[Path]:
    return [p for p in sorted((PACKAGE / "integrations").rglob("*.py")) if p.parent != PACKAGE / "integrations"]


def own_folder(path: Path) -> str:
    return path.relative_to(PACKAGE / "integrations").parts[0]


def test_an_integration_imports_no_other_integration_folder():
    """Shared code comes from `datapatchbay.plugins` (sql, codegen), never from the folder of another integration."""
    violations = []
    for path in integration_modules():
        folder = own_folder(path)
        for name in integration_imports(path):
            target = name.split(".")[0]
            if target in ("", folder) or folder in SHARED_INTEGRATION_FOLDERS.get(target, set()):
                continue
            violations.append(f"integrations.{folder} ({path.name}) imports integrations.{name}")
    assert not violations, "an integration may import only its own folder or datapatchbay.plugins:\n" + "\n".join(
        violations
    )


def test_an_integration_uses_no_relative_import_out_of_its_folder():
    violations = []
    for path in integration_modules():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level > 1:
                violations.append(f"{path.relative_to(PACKAGE)} imports {'.' * node.level}{node.module or ''}")
    assert not violations, "\n".join(violations)


def test_the_shared_toolkits_are_public_and_declare_what_is_public():
    for name in ("sql", "codegen"):
        module = __import__(f"datapatchbay.plugins.{name}", fromlist=["x"])
        assert "public, not yet stable in milestone 1" in (module.__doc__ or "")
        assert module.__all__, name
        for exported in module.__all__:
            assert hasattr(module, exported), f"datapatchbay.plugins.{name} lists {exported} in __all__ but lacks it"
