"""PyQGIS-backed project membership.

Adding a layer is a separate, explicit step from producing one: decision-19 adds
an output to the project only after the operation succeeded, so this adapter
never adds anything on its own.
"""

from __future__ import annotations

from qgis.core import QgsProject

from qgis_sdk.core import ResourceScope

from .layers import NativeLayers

__all__ = ["NativeProject"]


class NativeProject:
    """Add owned layers to a ``QgsProject`` and read its membership."""

    def __init__(
        self,
        layers: NativeLayers,
        scope: ResourceScope,
        project: QgsProject | None = None,
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._project = project if project is not None else QgsProject.instance()

    def layer_ids(self) -> tuple[str, ...]:
        """Return the project's layer ids in insertion order."""
        self._scope.ensure_open()
        return tuple(self._project.mapLayers().keys())

    def add_layer(self, layer_id: str) -> None:
        """Add an owned layer once; a layer already in the project stays put."""
        self._scope.ensure_open()
        # Package handoff: the project must add the very instance the layers
        # adapter owns, so this sibling call is deliberate and documented on
        # NativeLayers._qgs_layer.
        layer = self._layers._qgs_layer(layer_id)
        if self._project.mapLayer(layer_id) is None:
            self._project.addMapLayer(layer)
