from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any, Unpack

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import Component

from ._nodes import SurfaceOptions1, SurfaceValues1, label_map, surface_nodes
from ._surface_state import surface_snapshot_facts112345678

ROLES = {
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
ACTIONABLE = frozenset(
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
VALUE_METHOD = {
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
    if is_qobject(target):
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


def is_qobject(value: object) -> bool:
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
        if not is_qobject(child) or not is_widget(child):
            continue
        if child.objectName():
            yield _widget_node(child)
        else:
            yield from _named_descendants(child)


def is_widget(value: Any) -> bool:
    probe = getattr(value, "isWidgetType", None)
    return bool(probe()) if callable(probe) else True


def surface_snapshot(
    surface: object, **options: Unpack[SurfaceOptions1]
) -> dict[str, Any]:
    """One opened surface in the decision-51 inspection format.

    ``surface`` is the widget the host opened; nothing else is read, so a
    snapshot cannot reach a window this plugin did not open. ``declared``
    names the fields the surface was built from, which links a ``form/<field>``
    node back to its schema entry. ``screenshot`` is the digest of the PNG the
    caller captured beside this tree.
    """
    values = SurfaceValues1(**options)
    if not is_qobject(surface):
        raise QgisSdkUiError(
            f"surface_snapshot takes an opened Qt surface, got {type(surface).__name__}"
        )
    fields = tuple(values.declared)
    labels = label_map(surface)
    nodes, findings = surface_nodes(surface, surface, labels, fields, parent="")
    return surface_snapshot_facts112345678(
        findings=findings,
        kind=values.kind,
        nodes=nodes,
        palette=values.palette,
        scale=values.scale,
        screenshot=values.screenshot,
        surface=surface,
        surface_id=values.surface_id,
        title=values.title,
    )


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
