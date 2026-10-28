"""QGIS-free authoring and core SDK foundations."""

from .bindings import describe_bindings, menu, shortcut, toolbar
from .core._application import QgisSdkPlugin
from .declarations import (
    ActionDescription,
    PluginDescription,
    QgisSdkDeclarationError,
    StreamDescription,
    describe,
)

__all__ = [
    "ActionDescription",
    "PluginDescription",
    "QgisSdkDeclarationError",
    "QgisSdkPlugin",
    "StreamDescription",
    "describe",
    "describe_bindings",
    "menu",
    "shortcut",
    "toolbar",
]
