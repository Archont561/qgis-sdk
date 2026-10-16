"""Optional Qt WebEngine host support for QGIS-aware deployments.

The SDK core remains QGIS-free. This adapter probes for the Qt WebEngine
Python bindings lazily and reports an actionable SDK error when a deployment
has not provisioned them. It never imports Qt, PyQt, or QGIS while the module
is imported.
"""

from __future__ import annotations

from typing import Any

from qgis_sdk.models.errors import QgisSdkOptionalDependencyError

WEBENGINE_DEPENDENCY = "pyqt6-webengine"
WEBENGINE_INSTALLATION_HINT = (
    "Install the Qt WebEngine Python bindings provided by the QGIS "
    "distribution for this platform (for example python3-pyqt6-webengine on "
    "Debian/Ubuntu or the matching OSGeo4W/macOS package). The SDK does not "
    "download or install Qt WebEngine itself."
)


def _import_webengine_view() -> Any | None:
    """Return the ``QWebEngineView`` class if its bindings are installed."""
    candidates = (
        ("qgis.PyQt.QtWebEngineWidgets", "QWebEngineView"),
        ("PyQt6.QtWebEngineWidgets", "QWebEngineView"),
        ("PyQt5.QtWebEngineWidgets", "QWebEngineView"),
    )
    for module_name, class_name in candidates:
        try:
            module = __import__(module_name, fromlist=(class_name,))
        except ImportError:
            continue
        view_class = getattr(module, class_name, None)
        if view_class is not None:
            return view_class
    return None


def webengine_available() -> bool:
    """Return whether a Qt WebEngine view can be created in this runtime."""
    return _import_webengine_view() is not None


def require_webengine() -> None:
    """Raise an actionable error unless Qt WebEngine view bindings exist."""
    if not webengine_available():
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )


def create_webengine_view(*args: Any, **kwargs: Any) -> Any:
    """Create a ``QWebEngineView`` or raise an actionable SDK error."""
    view_class = _import_webengine_view()
    if view_class is None:
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )
    return view_class(*args, **kwargs)
