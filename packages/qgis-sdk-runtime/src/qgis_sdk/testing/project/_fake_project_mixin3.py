"""The fake project's lookups: a layer node, a group, a bookmark."""

from __future__ import annotations

from typing import Any

from qgis_sdk.models import (
    CanvasExtent,
    LayerNode,
    QgisSdkBookmarkNotFoundError,
    QgisSdkLayerNotFoundError,
)


class FakeProjectMixin3:
    def _require_layer_node(self, layer_id: str) -> int:
        position = self._index_of(layer_id)
        if position is None or self._nodes[position].kind != "layer":
            raise QgisSdkLayerNotFoundError(layer_id)
        return position

    def _require_group(self, group: str) -> LayerNode:
        position = self._index_of(group)
        if position is None or self._nodes[position].kind != "group":
            raise QgisSdkLayerNotFoundError(group)
        return self._nodes[position]

    def _require_bookmark(self, name: str) -> CanvasExtent:
        try:
            return self._bookmarks[name]
        except KeyError:
            raise QgisSdkBookmarkNotFoundError(name) from None

    @staticmethod
    def _replace(node: LayerNode, **changes: Any) -> LayerNode:
        values: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "kind": node.kind,
            "visible": node.visible,
            "parent": node.parent,
        }
        values.update(changes)
        return LayerNode(**values)
