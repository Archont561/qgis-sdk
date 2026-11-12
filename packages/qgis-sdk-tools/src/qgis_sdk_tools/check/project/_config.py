"""The ``[tool.qgis-sdk.check]`` table: what the project configures."""

from __future__ import annotations

from pathlib import Path

from qgis_sdk_tools.manifest import read_pyproject, table

from ..diagnostics import Diagnostic

__all__ = ["configured_native_modules"]

_CONFIG_TABLE = ("tool", "qgis-sdk", "check")


def configured_native_modules(root: Path) -> tuple[tuple[str, ...], list[Diagnostic]]:
    relative = Path("pyproject.toml")
    manifest, malformed = read_pyproject(root / relative)
    if malformed is not None:
        return (), [
            _config_diagnostic(relative, f"pyproject.toml does not parse: {malformed}")
        ]
    parent = table(manifest, *_CONFIG_TABLE[:-1])
    if parent is None or _CONFIG_TABLE[-1] not in parent:
        return (), []
    data = parent[_CONFIG_TABLE[-1]]
    if not isinstance(data, dict):
        return (), [
            _config_diagnostic(relative, "[tool.qgis-sdk.check] must be a table")
        ]
    globs = data.get("native-modules", [])
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        return (), [
            _config_diagnostic(
                relative,
                "[tool.qgis-sdk.check] native-modules must be a list of module globs",
            )
        ]
    return tuple(globs), []


def _config_diagnostic(path: Path, message: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=path,
        line=0,
        column=0,
        message=message,
        remediation=(
            'Write it as `native-modules = ["my_plugin.native", "my_plugin.views.*"]`.'
        ),
    )
