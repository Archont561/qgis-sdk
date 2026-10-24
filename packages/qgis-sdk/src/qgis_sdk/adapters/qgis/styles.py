"""PyQGIS-backed application of reviewed, packaged layer styles.

Compatibility is decided before anything is applied, by the same
``StyleSpec.incompatibilities`` rule the fake uses, so a mismatch is refused
without touching the layer. Only symbology is set: the application stylesheet and
palette are never read or written here (decision-16).
"""

from __future__ import annotations

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkPackagedResourceError, QgisSdkStyleIncompatibleError
from qgis_sdk.resources import require_style, style_path

from .layers import NativeLayers

__all__ = ["NativeStyles"]


class NativeStyles:
    """Apply a reviewed packaged QML resource to a compatible layer."""

    def __init__(self, layers: NativeLayers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope

    def apply_style(self, layer_id: str, style: str) -> None:
        """Validate the target, then load the packaged QML onto the layer."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        spec = require_style(style)
        reasons = spec.incompatibilities(info)
        if reasons:
            raise QgisSdkStyleIncompatibleError(layer_id, style, reasons)

        resource = style_path(style)
        # Package handoff: the style must be loaded onto the very instance the
        # layers adapter owns, not a copy of its description.
        layer = self._layers._qgs_layer(layer_id)
        message, loaded = layer.loadNamedStyle(str(resource))
        if not loaded:
            raise QgisSdkPackagedResourceError(style, message or "QGIS rejected it")
