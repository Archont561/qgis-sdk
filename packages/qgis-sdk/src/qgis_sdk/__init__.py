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
    "plugin",
]
