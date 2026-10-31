"""PyQGIS-backed service adapters for the curated pure contracts.

Importing a *name* from this package imports the adapter behind it and needs a
QGIS installation; importing the package itself does not. That split matters for
the hosts that never need the rest of the surface: a QGIS Server process serves
requests through :class:`~qgis_sdk.adapters.qgis.server.QgsServerHost` and has no
use for Qt Widgets or Processing, and the server wiring is checked against
``qgis.server`` stand-ins on a machine with no QGIS at all (TASK-80). The eager
form dragged every adapter in through ``.algorithms`` and made both impossible.

The adapters in this package implement the same ``qgis_sdk.services`` contracts
as the in-memory doubles, and the contract suite in ``tests/services`` runs both
against one set of tests.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the names, for readers and type checkers; not imported
    from .algorithms import NativeAlgorithms
    from .context import IfaceDesktopAccess, native_plugin_context
    from .features import NativeFeatureEditing, NativeFeatures
    from .jobs import DEFAULT_INTERVAL_MS, QgsJobPump
    from .layers import NativeLayers
    from .log import NativeLog
    from .network import NativeNetworkTransport
    from .notifications import NativeNotifications
    from .processing import NativeProcessing, NativeProcessingProvider
    from .project import NativeProject
    from .server import QgsServerHost
    from .settings import NativeSettings
    from .styles import NativeStyles
    from .tasks import QgsTaskWorkers
    from .workers import ThreadPoolWorkers

__all__ = [
    "DEFAULT_INTERVAL_MS",
    "IfaceDesktopAccess",
    "NativeAlgorithms",
    "NativeFeatureEditing",
    "NativeFeatures",
    "NativeLayers",
    "NativeLog",
    "NativeNetworkTransport",
    "NativeNotifications",
    "NativeProcessing",
    "NativeProcessingProvider",
    "NativeProject",
    "NativeSettings",
    "NativeStyles",
    "QgsJobPump",
    "QgsServerHost",
    "QgsTaskWorkers",
    "ThreadPoolWorkers",
    "native_plugin_context",
]

#: Which module holds each exported name; the import happens on first access.
_EXPORTS: dict[str, str] = {
    "DEFAULT_INTERVAL_MS": ".jobs",
    "IfaceDesktopAccess": ".context",
    "NativeAlgorithms": ".algorithms",
    "NativeFeatureEditing": ".features",
    "NativeFeatures": ".features",
    "NativeLayers": ".layers",
    "NativeLog": ".log",
    "NativeNetworkTransport": ".network",
    "NativeNotifications": ".notifications",
    "NativeProcessing": ".processing",
    "NativeProcessingProvider": ".processing",
    "NativeProject": ".project",
    "NativeSettings": ".settings",
    "NativeStyles": ".styles",
    "QgsJobPump": ".jobs",
    "QgsServerHost": ".server",
    "QgsTaskWorkers": ".tasks",
    "ThreadPoolWorkers": ".workers",
    "native_plugin_context": ".context",
}


def __getattr__(name: str) -> Any:
    """Import the adapter behind ``name`` the first time it is asked for."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
