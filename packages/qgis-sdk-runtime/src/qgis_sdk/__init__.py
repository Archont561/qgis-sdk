"""QGIS-free authoring and core SDK foundations."""

from .bindings import describe_bindings, menu, shortcut, toolbar
from .declarations import (
    ActionDescription,
    PluginDescription,
    QgisSdkDeclarationError,
    StreamDescription,
    action,
    describe,
    describe_plugin,
    plugin,
    stream,
)

__all__ = [
    "ActionDescription",
    "PluginDescription",
    "QgisSdkDeclarationError",
    "StreamDescription",
    "action",
    "describe",
    "describe_bindings",
    "describe_plugin",
    "menu",
    "plugin",
    "shortcut",
    "stream",
    "toolbar",
]
