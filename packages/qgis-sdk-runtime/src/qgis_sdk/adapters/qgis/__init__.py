"""PyQGIS-backed service adapters for the curated pure contracts.

Importing this package needs a QGIS installation. It is deliberately absent from
the eager pure import surface: ``qgis_sdk.adapters`` does not re-export it, and
``tests/test_pure_imports.py`` imports the other adapters with QGIS blocked.

The adapters in this package implement the same ``qgis_sdk.services`` contracts
as the in-memory doubles, and the contract suite in ``tests/services`` runs both
against one set of tests.
"""

from .algorithms import NativeAlgorithms
from .context import IfaceDesktopAccess, native_plugin_context
from .layers import NativeLayers
from .network import NativeNetworkTransport
from .notifications import NativeNotifications
from .processing import NativeProcessing, NativeProcessingProvider
from .project import NativeProject
from .settings import NativeSettings
from .styles import NativeStyles
from .workers import ThreadPoolWorkers

__all__ = [
    "IfaceDesktopAccess",
    "NativeAlgorithms",
    "NativeLayers",
    "NativeNetworkTransport",
    "NativeNotifications",
    "NativeProcessing",
    "NativeProcessingProvider",
    "NativeProject",
    "NativeSettings",
    "NativeStyles",
    "ThreadPoolWorkers",
    "native_plugin_context",
]
