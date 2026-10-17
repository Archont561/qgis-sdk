"""QGIS-free authoring and core SDK foundations."""

from .declarations import (
    ActionDescription,
    PluginDescription,
    QgisSdkDeclarationError,
    action,
    describe_plugin,
    plugin,
)

__all__ = [
    "ActionDescription",
    "PluginDescription",
    "QgisSdkDeclarationError",
    "action",
    "describe_plugin",
    "hello",
    "plugin",
]


def hello() -> str:
    """Return a greeting used by the package smoke test."""
    return "hello world"
