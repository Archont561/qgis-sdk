from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

from ._surface_state import (
    CcReturn,
    CcState,
    cc_surface_node_p1,
    cc_surface_node_p2,
    cc_surface_node_p3,
)


def surface_nodes(
    widget: object,
    surface: object,
    labels: Mapping[int, str],
    fields: Sequence[str],
    *,
    parent: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for index, child in enumerate(_widget_children(widget)):
        path = f"{parent}/{index}" if parent else str(index)
        node, child_findings = _surface_node(child, surface, labels, fields, path)
        nodes.append(node)
        findings.extend(child_findings)
    return nodes, findings


def _surface_node(
    widget: Any,
    surface: object,
    labels: Mapping[int, str],
    fields: Sequence[str],
    path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _s = CcState(
        widget=widget, surface=surface, labels=labels, fields=fields, path=path
    )
    for _p in (cc_surface_node_p1, cc_surface_node_p2, cc_surface_node_p3):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


def unnamed_findings(widget: Any, role: str, node_id: str) -> list[dict[str, Any]]:
    from ._snapshot import ACTIONABLE

    if not node_id.startswith("#") or role not in ACTIONABLE:
        return []
    return [
        {
            "rule": "UI001",
            "node": node_id,
            "message": (
                f"{type(widget).__name__} has no objectName; "
                "its id is positional and breaks when the layout changes"
            ),
        }
    ]


def declared(name: str, fields: Sequence[str]) -> dict[str, str] | None:
    namespace, _, member = name.partition("/")
    if not member:
        return None
    if namespace == "form" and member in fields:
        return {"field": member}
    if namespace == "buttons":
        return {"button": member}
    return None


def label_map(surface: object) -> dict[int, str]:
    labels: dict[int, str] = {}
    for widget in _widgets(surface):
        if role(widget) != "label":
            continue
        buddy = call(widget, "buddy", None)
        if buddy is not None:
            labels[id(buddy)] = text(widget)
    return labels


def role(widget: Any) -> str:
    from ._snapshot import ROLES

    for klass in type(widget).__mro__:
        role = ROLES.get(klass.__name__)
        if role is not None:
            return role
    return "widget"


def value(widget: Any, role: str) -> Any:
    from ._snapshot import VALUE_METHOD

    method = VALUE_METHOD.get(role)
    if method is None:
        return None
    reader = getattr(widget, method, None)
    if not callable(reader):
        return None
    try:
        return reader()
    except TypeError:  # a `text(index)` style accessor, not the role's value
        return None


def position(widget: Any, surface: object) -> tuple[int, int]:
    x = y = 0
    node: Any = widget
    while node is not None and node is not surface:
        point = call(node, "pos", None)
        if point is None:
            break
        x += int(call(point, "x", 0))
        y += int(call(point, "y", 0))
        node = call(node, "parentWidget", None)
    return x, y


def size(surface: Any) -> dict[str, int]:
    return {
        "width": int(call(surface, "width", 0)),
        "height": int(call(surface, "height", 0)),
    }


def text(widget: Any) -> str | None:
    text = call(widget, "text", None)
    return text if isinstance(text, str) else None


def object_name(widget: Any) -> str:
    name = call(widget, "objectName", "")
    return name if isinstance(name, str) else ""


def call(value: object, name: str, default: Any) -> Any:
    member = getattr(value, name, None)
    if not callable(member):
        return default
    try:
        return member()
    except (RuntimeError, TypeError):
        # A deleted QObject answers RuntimeError; a signature mismatch means
        # the method is not the accessor this snapshot expects.
        return default


def _widgets(surface: object) -> Iterator[Any]:
    for child in _widget_children(surface):
        yield child
        yield from _widgets(child)


def _widget_children(widget: Any) -> Iterator[Any]:
    from ._snapshot import is_qobject, is_widget

    children = call(widget, "children", None)
    for child in children or ():
        if is_qobject(child) and is_widget(child):
            yield child


class SurfaceOptions1(TypedDict, total=False):
    surface_id: str
    kind: str
    title: str | None
    declared: Sequence[str]
    screenshot: str | None
    scale: float
    palette: Mapping[str, str] | None


@dataclass(frozen=True, slots=True)
class SurfaceValues1:
    surface_id: str
    kind: str
    title: str | None = None
    declared: Sequence[str] = ()
    screenshot: str | None = None
    scale: float = 1.0
    palette: Mapping[str, str] | None = None
