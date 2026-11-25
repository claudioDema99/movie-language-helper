"""Offline import checks for the documented dependency direction."""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

PACKAGE_ROOT = (Path(__file__).parents[2] / "src" / "movie_language_helper").resolve()

FORBIDDEN_INTERNAL_PREFIXES = {
    "domain": (
        "movie_language_helper.adapters",
        "movie_language_helper.application",
        "movie_language_helper.infrastructure",
        "movie_language_helper.ports",
    ),
    "application": (
        "movie_language_helper.adapters",
        "movie_language_helper.infrastructure",
    ),
    "ports": (
        "movie_language_helper.adapters",
        "movie_language_helper.infrastructure",
    ),
}


def imported_modules(path: Path) -> Iterator[str]:
    """Yield absolute module names imported by one Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def layer_sources(layer: str) -> Iterator[Path]:
    """Yield every Python file in an architecture layer."""
    yield from sorted((PACKAGE_ROOT / layer).rglob("*.py"))


def test_core_layers_only_import_standard_library_and_project_modules() -> None:
    violations: list[str] = []

    for layer in ("domain", "application", "ports"):
        for path in layer_sources(layer):
            for module in imported_modules(path):
                import_root = module.split(".", maxsplit=1)[0]
                if (
                    import_root not in sys.stdlib_module_names
                    and import_root != "movie_language_helper"
                ):
                    relative_path = path.relative_to(PACKAGE_ROOT)
                    violations.append(f"{relative_path}: {module}")

    assert violations == [], (
        "Third-party imports crossed a core boundary:\n" + "\n".join(violations)
    )


def test_internal_imports_follow_the_documented_dependency_direction() -> None:
    violations: list[str] = []

    for layer, forbidden_prefixes in FORBIDDEN_INTERNAL_PREFIXES.items():
        for path in layer_sources(layer):
            for module in imported_modules(path):
                if module.startswith(forbidden_prefixes):
                    relative_path = path.relative_to(PACKAGE_ROOT)
                    violations.append(f"{relative_path}: {module}")

    assert violations == [], "An import points toward an outer layer:\n" + "\n".join(
        violations
    )
