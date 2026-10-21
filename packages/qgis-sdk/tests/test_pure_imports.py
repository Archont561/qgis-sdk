"""Guard the public, QGIS-free package boundary without running QGIS."""

import ast
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "qgis_sdk"
LAYER_ORDER = {
    "models": 0,
    "declarations": 1,
    "services": 1,
    "scaffold": 1,
    "core": 2,
}
LAYER_PATHS = {
    "core": SOURCE_ROOT / "core",
    "scaffold": SOURCE_ROOT / "scaffold",
    "declarations": SOURCE_ROOT / "declarations.py",
    "models": SOURCE_ROOT / "models",
    "services": SOURCE_ROOT / "services",
}


def imports_in(path: Path, layer: str) -> list[tuple[str, int]]:
    """Read declared imports even inside functions or conditional blocks."""
    package = f"qgis_sdk.{layer}"
    imports: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            imports.append((name, node.lineno))
            # `from qgis_sdk import adapters` and `from . import adapters`
            # must not bypass the dependency-direction check.
            if name == "qgis_sdk" or node.module is None:
                imports.extend(
                    (f"{name}.{alias.name}", node.lineno) for alias in node.names
                )
    return imports


@pytest.mark.parametrize("layer", LAYER_ORDER)
def test_pure_layers_only_import_the_stdlib_and_lower_pure_layers(layer: str) -> None:
    path = LAYER_PATHS[layer]
    files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
    assert files, f"Missing public pure layer: {layer}"
    for file in files:
        for module, line in imports_in(file, layer):
            parts = module.split(".")
            if parts[0] == "qgis_sdk":
                allowed = len(parts) > 1 and parts[1] in LAYER_ORDER
                allowed = allowed and LAYER_ORDER[parts[1]] <= LAYER_ORDER[layer]
            else:
                allowed = parts[0] in sys.stdlib_module_names
            assert allowed, (
                f"{file.relative_to(SOURCE_ROOT)}:{line}: forbidden import {module}"
            )


def test_pure_public_imports_succeed_with_native_modules_forbidden(
    tmp_path: Path,
) -> None:
    script = textwrap.dedent(
        """
        import importlib
        import sys

        sys.path.insert(0, sys.argv[1])

        class RejectNative:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'qgis', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'pydantic'}:
                    raise AssertionError(f'eager native import: {fullname}')
                return None

        sys.meta_path.insert(0, RejectNative())
        for module in ('qgis_sdk', 'qgis_sdk.models', 'qgis_sdk.declarations',
                       'qgis_sdk.services', 'qgis_sdk.scaffold', 'qgis_sdk.core',
                       'qgis_sdk.core.contexts', 'qgis_sdk.core.runtime',
                       'qgis_sdk.adapters.desktop',
                       'qgis_sdk.adapters.pydantic',
                       'qgis_sdk.adapters.webengine'):
            importlib.import_module(module)
        from qgis_sdk import action, describe_plugin, plugin

        @plugin(id='isolated', title='Isolated')
        class Example:
            @action(id='run', title='Run')
            def run(self, count: int) -> str:
                raise AssertionError('inspection dispatched a handler')

        assert describe_plugin(Example).actions[0].id == 'run'
        assert 'qgis' not in sys.modules
        assert 'pydantic' not in sys.modules
        print('native-free')
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(SOURCE_ROOT.parent)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "native-free"
