"""The two snapshots of decision-51: a component tree and a surface capture.

``ui_snapshot`` is the small tree used by the catalogue and declarative tests.
``surface_snapshot`` is the inspection format: one opened surface as nodes with
a role, value, label, state and geometry, plus the findings that say where an
id is brittle, and a canonical JSON rendering of it.

A snapshot is a nested dict - ``type``, ``name``, ``objectName``, the
component's state, ``children`` - that a pure test asserts on and an agent
reads. Given a catalogue :class:`~qgis_sdk.ui.components.Component` it is
the component's own ``snapshot()``; given a Qt widget it is the tree of the
widget's named descendants, read through ``objectName`` only, so the ids of
a surface built under the fake and of the same surface mounted natively
line up (``snapshot_names``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from qgis_sdk.models import QgisSdkUiError

from .components import Component

__all__ = ["canonical_json", "snapshot_names", "surface_snapshot", "ui_snapshot"]

#: Qt and QGIS classes to the role a reader thinks in. Roles, not class names,
#: are the stable part: a widget swap that keeps the role keeps the reference.
_ROLES = {
    "QLineEdit": "textbox",
    "QPlainTextEdit": "textbox",
    "QTextEdit": "textbox",
    "QTextBrowser": "textbox",
    "QComboBox": "combobox",
    "QgsMapLayerComboBox": "combobox",
    "QgsFieldComboBox": "combobox",
    "QgsProjectionSelectionWidget": "crs",
    "QgsColorButton": "colour",
    "QgsFileWidget": "file",
    "QgsSpinBox": "spinbox",
    "QgsDoubleSpinBox": "spinbox",
    "QSpinBox": "spinbox",
    "QDoubleSpinBox": "spinbox",
    "QSlider": "slider",
    "QDial": "slider",
    "QCheckBox": "checkbox",
    "QRadioButton": "radio",
    "QPushButton": "button",
    "QToolButton": "button",
    "QDialogButtonBox": "buttons",
    "QMenu": "menu",
    "QToolBar": "toolbar",
    "QLabel": "label",
    "QGroupBox": "group",
    "QTabWidget": "tab",
    "QTabBar": "tab",
    "QSplitter": "splitter",
    "QScrollArea": "scroll",
    "QStackedWidget": "stack",
    "QStatusBar": "status",
    "QProgressBar": "progress",
    "QTableWidget": "table",
    "QTableView": "table",
    "QTreeWidget": "tree",
    "QTreeView": "tree",
    "QListWidget": "list",
    "QListView": "list",
    "QgsMapCanvas": "canvas",
    "QDialog": "dialog",
    "QMainWindow": "window",
    "QFrame": "container",
    "QWidget": "container",
}

#: Roles a user acts on, so an unstable id is a finding rather than a detail.
_ACTIONABLE = frozenset(
    {
        "textbox",
        "combobox",
        "spinbox",
        "slider",
        "checkbox",
        "radio",
        "button",
        "buttons",
        "colour",
        "crs",
        "file",
        "list",
        "menu",
        "table",
        "tab",
        "toolbar",
        "tree",
    }
)

#: The method that reads a role's value, where the role has one.
_VALUE_METHOD = {
    "textbox": "text",
    "label": "text",
    "button": "text",
    "combobox": "currentText",
    "spinbox": "value",
    "slider": "value",
    "progress": "value",
    "checkbox": "isChecked",
    "radio": "isChecked",
    "group": "title",
    "tab": "currentIndex",
    "stack": "currentIndex",
    "table": "rowCount",
    "tree": "topLevelItemCount",
    "list": "count",
}


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


def surface_snapshot(
    surface: object,
    *,
    surface_id: str,
    kind: str,
    title: str | None = None,
    declared: Sequence[str] = (),
    screenshot: str | None = None,
    scale: float = 1.0,
    palette: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """One opened surface in the decision-51 inspection format.

    ``surface`` is the widget the host opened; nothing else is read, so a
    snapshot cannot reach a window this plugin did not open. ``declared``
    names the fields the surface was built from, which links a ``form/<field>``
    node back to its schema entry. ``screenshot`` is the digest of the PNG the
    caller captured beside this tree.
    """
    if not _is_qobject(surface):
        raise QgisSdkUiError(
            f"surface_snapshot takes an opened Qt surface, got {type(surface).__name__}"
        )
    fields = tuple(declared)
    labels = _label_map(surface)
    nodes, findings = _surface_nodes(surface, surface, labels, fields, parent="")
    payload: dict[str, Any] = {
        "surface": surface_id,
        "kind": kind,
        "title": title if title is not None else _text(surface),
        "size": _size(surface),
        "scale": round(float(scale), 3),
        "screenshot": screenshot,
        "nodes": nodes,
        "findings": findings,
    }
    if palette is not None:
        payload["palette"] = {str(name): str(value) for name, value in palette.items()}
    return payload


def canonical_json(payload: Mapping[str, Any]) -> str:
    """The canonical rendering: sorted keys, no spaces, one trailing newline.

    Two captures of the same surface render byte-identically, which is what an
    approved snapshot compares.
    """
    rendered = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return rendered + "\n"


def _surface_nodes(
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
    name = _object_name(widget)
    role = _role(widget)
    node_id = name or f"#{path}"
    findings = _unnamed_findings(widget, role, node_id)
    x, y = _position(widget, surface)
    node: dict[str, Any] = {
        "id": node_id,
        "role": role,
        "type": type(widget).__name__,
        "value": _value(widget, role),
        "label": labels.get(id(widget)),
        "state": {
            "enabled": bool(_call(widget, "isEnabled", True)),
            "visible": bool(_call(widget, "isVisible", True)),
            "focus": bool(_call(widget, "hasFocus", False)),
        },
        "geometry": {
            "x": x,
            "y": y,
            "width": int(_call(widget, "width", 0)),
            "height": int(_call(widget, "height", 0)),
        },
        "declared": _declared(name, fields),
    }
    children, child_findings = _surface_nodes(
        widget, surface, labels, fields, parent=path
    )
    if children:
        node["children"] = children
    findings.extend(child_findings)
    return node, findings


def _unnamed_findings(widget: Any, role: str, node_id: str) -> list[dict[str, Any]]:
    if not node_id.startswith("#") or role not in _ACTIONABLE:
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


def _declared(name: str, fields: Sequence[str]) -> dict[str, str] | None:
    namespace, _, member = name.partition("/")
    if not member:
        return None
    if namespace == "form" and member in fields:
        return {"field": member}
    if namespace == "buttons":
        return {"button": member}
    return None


def _label_map(surface: object) -> dict[int, str]:
    labels: dict[int, str] = {}
    for widget in _widgets(surface):
        if _role(widget) != "label":
            continue
        buddy = _call(widget, "buddy", None)
        if buddy is not None:
            labels[id(buddy)] = _text(widget)
    return labels


def _role(widget: Any) -> str:
    for klass in type(widget).__mro__:
        role = _ROLES.get(klass.__name__)
        if role is not None:
            return role
    return "widget"


def _value(widget: Any, role: str) -> Any:
    method = _VALUE_METHOD.get(role)
    if method is None:
        return None
    reader = getattr(widget, method, None)
    if not callable(reader):
        return None
    try:
        return reader()
    except TypeError:  # a `text(index)` style accessor, not the role's value
        return None


def _position(widget: Any, surface: object) -> tuple[int, int]:
    x = y = 0
    node: Any = widget
    while node is not None and node is not surface:
        point = _call(node, "pos", None)
        if point is None:
            break
        x += int(_call(point, "x", 0))
        y += int(_call(point, "y", 0))
        node = _call(node, "parentWidget", None)
    return x, y


def _size(surface: Any) -> dict[str, int]:
    return {
        "width": int(_call(surface, "width", 0)),
        "height": int(_call(surface, "height", 0)),
    }


def _text(widget: Any) -> str | None:
    text = _call(widget, "text", None)
    return text if isinstance(text, str) else None


def _object_name(widget: Any) -> str:
    name = _call(widget, "objectName", "")
    return name if isinstance(name, str) else ""


def _call(value: object, name: str, default: Any) -> Any:
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
    children = _call(widget, "children", None)
    for child in children or ():
        if _is_qobject(child) and _is_widget(child):
            yield child
