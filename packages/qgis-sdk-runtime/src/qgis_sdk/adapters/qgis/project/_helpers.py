from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsRectangle,
)

from qgis_sdk.models import (
    CanvasExtent,
)

if TYPE_CHECKING:
    from qgis.core import QgsLayerTreeNode


#: The prefix a layer-tree group's derived id carries (``group:a/b``).
GROUP_ID_PREFIX = "group:"


def is_layer(node: QgsLayerTreeNode) -> bool:
    """Whether a tree node is a layer rather than a group.

    A layer node answers ``layerId()`` and a group does not, which is the one
    difference both spellings of the tree classes agree on.
    """
    return hasattr(node, "layerId")


def group_id_of(node: Any) -> str:
    """Return the derived id of ``node`` and its ancestors, or ``""`` for the root."""
    names: list[str] = []
    current = node
    while current is not None and not is_layer(current):
        parent = current.parent()
        if parent is None:
            break
        names.append(str(current.name()))
        current = parent
    if not names:
        return ""
    return GROUP_ID_PREFIX + "/".join(reversed(names))


def bookmark_list(manager: Any) -> list[Any]:
    """Return the manager's bookmarks as a list.

    ``QgsBookmarkManager.bookmarks()`` answers a name-keyed map on a 3.x build
    and a plain list on a 4.x one, so the callers index neither.
    """
    bookmarks = manager.bookmarks()
    values = getattr(bookmarks, "values", None)
    return list(bookmarks if values is None else values())


def extent(box: Any) -> CanvasExtent:
    return CanvasExtent(
        x_min=box.xMinimum(),
        y_min=box.yMinimum(),
        x_max=box.xMaximum(),
        y_max=box.yMaximum(),
        crs=None,
    )


def box(extent: CanvasExtent) -> QgsRectangle:
    return QgsRectangle(extent.x_min, extent.y_min, extent.x_max, extent.y_max)
