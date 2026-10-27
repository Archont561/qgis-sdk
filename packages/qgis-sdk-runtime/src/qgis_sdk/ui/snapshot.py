"""``ui_snapshot``: the semantic tree of a surface, with or without Qt (decision-51).

A snapshot is a nested dict - ``type``, ``name``, ``objectName``, the
component's state, ``children`` - that a pure test asserts on and an agent
reads. Given a catalogue :class:`~qgis_sdk.ui.components.Component` it is
the component's own ``snapshot()``; given a Qt widget it is the tree of the
widget's named descendants, read through ``objectName`` only, so the ids of
a surface built under the fake and of the same surface mounted natively
line up (``snapshot_names``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qgis_sdk.models import QgisSdkUiError

from .components import Component

__all__ = ["snapshot_names", "ui_snapshot"]


def ui_snapshot(target: object) -> dict[str, Any]:
    """The semantic tree of ``target``: a component, a surface or a Qt widget.

    A :class:`Component` answers with its own node. An object with a
    ``root`` component (what :func:`qgis_sdk.testing.build_surface` returns)
    is snapshotted through it. Anything with ``objectName`` and ``children``
    is walked as a Qt widget tree: unnamed widgets are transparent, named
    ones become nodes.
    """
    if isinstance(target, Component):
        return target.snapshot()
    root = getattr(target, "root", None)
    if isinstance(root, Component):
        return root.snapshot()
    if _is_qobject(target):
        return _widget_node(target)
    raise QgisSdkUiError(
        f"ui_snapshot takes a component, a built surface or a Qt widget, "
        f"got {type(target).__name__}"
    )


def snapshot_names(node: dict[str, Any]) -> tuple[str, ...]:
    """Every ``objectName`` in ``node`` and below, depth first."""
    return tuple(_names(node))


def _names(node: dict[str, Any]) -> Iterator[str]:
    name = node.get("objectName")
    if name:
        yield name
    for child in node.get("children", ()):
        yield from _names(child)


def _is_qobject(value: object) -> bool:
    return callable(getattr(value, "objectName", None)) and callable(
        getattr(value, "children", None)
    )


def _widget_node(widget: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": type(widget).__name__,
        "objectName": widget.objectName(),
    }
    text = getattr(widget, "text", None)
    if callable(text):
        try:
            node["text"] = text()
        except TypeError:  # a `text(index)` style accessor
            pass
    children = list(_named_descendants(widget))
    if children:
        node["children"] = children
    return node


def _named_descendants(widget: Any) -> Iterator[dict[str, Any]]:
    for child in widget.children():
        if not _is_qobject(child) or not _is_widget(child):
            continue
        if child.objectName():
            yield _widget_node(child)
        else:
            yield from _named_descendants(child)


def _is_widget(value: Any) -> bool:
    probe = getattr(value, "isWidgetType", None)
    return bool(probe()) if callable(probe) else True
