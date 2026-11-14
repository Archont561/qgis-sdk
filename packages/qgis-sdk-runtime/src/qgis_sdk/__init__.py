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

# decision-56: the tier these names are promised at. Every public module carries
# one, `qgis-sdk api dump` records them, and doc-12's Stability section is
# rendered from that record rather than restated by hand.
__stability__ = "stable"
