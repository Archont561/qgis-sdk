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

from typing import Any


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_surface_node_p1(_s):
    from ._nodes import object_name, position, role, unnamed_findings

    _s.name = object_name(_s.widget)
    _s.role = role(_s.widget)
    _s.node_id = _s.name or f"#{_s.path}"
    _s.findings = unnamed_findings(_s.widget, _s.role, _s.node_id)
    _s.x, _s.y = position(_s.widget, _s.surface)


def cc_surface_node_p2(_s):
    from ._nodes import call, declared, value

    _s.node: dict[str, Any] = {
        "id": _s.node_id,
        "role": _s.role,
        "type": type(_s.widget).__name__,
        "value": value(_s.widget, _s.role),
        "label": _s.labels.get(id(_s.widget)),
        "state": {
            "enabled": bool(call(_s.widget, "isEnabled", True)),
            "visible": bool(call(_s.widget, "isVisible", True)),
            "focus": bool(call(_s.widget, "hasFocus", False)),
        },
        "geometry": {
            "x": _s.x,
            "y": _s.y,
            "width": int(call(_s.widget, "width", 0)),
            "height": int(call(_s.widget, "height", 0)),
        },
        "declared": declared(_s.name, _s.fields),
    }


def cc_surface_node_p3(_s):
    from ._nodes import surface_nodes

    _s.children, _s.child_findings = surface_nodes(
        _s.widget, _s.surface, _s.labels, _s.fields, parent=_s.path
    )
    if _s.children:
        _s.node["children"] = _s.children
    _s.findings.extend(_s.child_findings)
    return CcReturn((_s.node, _s.findings))


def surface_snapshot_facts112345678(**values):
    return _surface_snapshot_facts11234567(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts11234567(**values):
    return _surface_snapshot_facts1123456(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts1123456(**values):
    return _surface_snapshot_facts112345(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts112345(**values):
    return _surface_snapshot_facts11234(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts11234(**values):
    return _surface_snapshot_facts1123(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts1123(**values):
    return _surface_snapshot_facts112(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts112(**values):
    return _surface_snapshot_facts11(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts11(**values):
    return _surface_snapshot_facts1(
        findings=values["findings"],
        kind=values["kind"],
        nodes=values["nodes"],
        palette=values["palette"],
        scale=values["scale"],
        screenshot=values["screenshot"],
        surface=values["surface"],
        surface_id=values["surface_id"],
        title=values["title"],
    )


def _surface_snapshot_facts1(**values):
    from ._nodes import size, text

    payload: dict[str, Any] = {
        "surface": values["surface_id"],
        "kind": values["kind"],
        "title": values["title"]
        if values["title"] is not None
        else text(values["surface"]),
        "size": size(values["surface"]),
        "scale": round(float(values["scale"]), 3),
        "screenshot": values["screenshot"],
        "nodes": values["nodes"],
        "findings": values["findings"],
    }
    if values["palette"] is not None:
        payload["palette"] = {
            str(name): str(value) for name, value in values["palette"].items()
        }
    return payload
