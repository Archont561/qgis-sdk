"""Connecting: find the node, find the signal, connect the method."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import Component, Container

from ._types import ON_SIGNALS, QT_CHANGED, QT_SIGNALS, Wire

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = ["connection", "subscription", "wire_surface", "wires_of"]


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_connection_p1(_s):
    _s.shown = _s.wire.shown
    _s.node = _node(_s.root, _s.wire, _s.surface)
    _s.signal = _s.wire.signal or "changed"


def _cc_connection_p2(_s):
    if isinstance(_s.node, Component):
        _s.subscription_name = ON_SIGNALS.get(_s.signal, _s.signal)
        _s.subscribe_method = getattr(_s.node, _s.subscription_name, None)
        if not callable(_s.subscribe_method) or _s.subscription_name in _cc_fresh_1():
            raise QgisSdkUiError(
                f"@on({_s.shown}).{_s.signal}: {type(_s.node).__name__} "
                f"{_s.node.name!r} has no such signal"
            )
        _s.listener = _adapt(_s.method)
        return _CcReturn(lambda: _s.subscribe_method(_s.listener))
    _s.qt_signal = _qt_signal(_s.node, _s.signal)


def _cc_connection_p3(_s):
    if _s.qt_signal is None:
        raise QgisSdkUiError(
            f"@on({_s.shown}, {_s.signal!r}): widget {_s.shown} "
            f"({type(_s.node).__name__}) has no such signal"
        )
    _s.slot = _adapt(_s.method)


def _cc_connection_p4(_s):

    def connect() -> Callable[[], None]:
        _s.qt_signal.connect(_s.slot)

        def disconnect() -> None:
            try:
                _s.qt_signal.disconnect(_s.slot)
            except (TypeError, RuntimeError):  # already gone with the widget
                pass

        _s.disconnect = disconnect

        return disconnect

    _s.connect = connect


def _cc_connection_p5(_s):

    return _CcReturn(_s.connect)


_CC_DATA_1 = (
    "attach",
    "mount",
    "dispose",
)


def _cc_fresh_1():
    """Return a fresh copy of the shared data literal."""
    return copy.deepcopy(_CC_DATA_1)


def _wire_surface_facts1(ctx, disconnects, root, surface, unwire):
    if disconnects:
        ctx.scope.on_close(unwire)
    behaviours = getattr(surface, "_attach_behaviours", None)
    if callable(behaviours):
        behaviours(root, ctx)
    return len(disconnects)


def wires_of(cls: type) -> tuple[tuple[str, Wire], ...]:
    """Every ``(method name, wire)`` a surface class declares, base classes first."""
    from qgis_sdk.declarations import WIRES_ATTRIBUTE

    found: list[tuple[str, Wire]] = []
    seen: set[str] = set()
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if name in seen:
                continue
            wires = getattr(value, WIRES_ATTRIBUTE, None)
            if not wires:
                continue
            seen.add(name)
            found.extend((name, wire) for wire in wires)
    return tuple(found)


def wire_surface(surface: Any, root: Any, ctx: UiContext) -> int:
    """Connect every ``@on``/``@subscribe`` method of ``surface`` to ``root``.

    ``root`` is what ``build()`` returned: a catalogue component (mounted or
    not) or a Qt widget. Every connection is undone when ``ctx.scope``
    closes. A name no node carries is refused before anything connects.
    The behaviour mixins' ``_attach_behaviours`` runs last. Returns the
    number of ``@on``/``@subscribe`` connections made.
    """
    wires = wires_of(type(surface))
    plan: list[Callable[[], Callable[[], None]]] = []
    for method_name, wire in wires:
        method = getattr(surface, method_name)
        if wire.kind == "subscribe":
            plan.append(subscription(ctx, wire, method))
        else:
            plan.append(connection(root, wire, method, surface))
    disconnects: list[Callable[[], None]] = []
    for connect in plan:
        disconnects.append(connect())

    def unwire() -> None:
        while disconnects:
            disconnects.pop()()

    return _wire_surface_facts1(ctx, disconnects, root, surface, unwire)


def subscription(
    ctx: UiContext, wire: Wire, method: Callable[..., Any]
) -> Callable[[], Callable[[], None]]:
    if not ctx.has("streams"):
        raise QgisSdkUiError(
            f"@subscribe({wire.target!r}) needs ctx.streams, which this host "
            "does not provide"
        )
    streams = ctx.streams
    if wire.target not in streams.ids:
        known = ", ".join(streams.ids) or "none"
        raise QgisSdkUiError(
            f"@subscribe({wire.target!r}): the plugin declares no such stream; "
            f"it has: {known}"
        )

    def connect() -> Callable[[], None]:
        sub = streams.subscribe(wire.target, method, **wire.request)
        return sub.dispose

    return connect


def connection(
    root: Any, wire: Wire, method: Callable[..., Any], surface: Any
) -> Callable[[], Callable[[], None]]:
    _s = _CcState(root=root, wire=wire, method=method, surface=surface)
    for _p in (
        _cc_connection_p1,
        _cc_connection_p2,
        _cc_connection_p3,
        _cc_connection_p4,
        _cc_connection_p5,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def _node(root: Any, wire: Wire, surface: Any) -> Any:
    """The node ``@on`` named: by name in the tree, or the declared copy."""
    target = wire.target
    if isinstance(target, Component):
        from qgis_sdk.ui.declarative import resolve_declared

        node = resolve_declared(surface, target)
        if node is not None:
            return node
        # Not declared on the class: it must then be in the built tree by
        # identity (a module-level component ``build()`` placed).
        if target.named and _find(root, target.name) is target:
            return target
        raise QgisSdkUiError(
            f"@on({wire.shown}) on {type(surface).__name__}: the component is "
            f"not declared on {type(surface).__name__} and build() did not "
            "place it"
        )
    node = _find(root, target)
    if node is None:
        raise QgisSdkUiError(
            f"@on({target!r}) on {type(surface).__name__}: "
            f"build() produced no node named {target!r}"
        )
    return node


def _find(root: Any, name: str) -> Any:
    """Find the widget a surface published under ``name``, or ``None``."""
    if not isinstance(root, Component):
        return _find_widget(root, name)
    if root.name == name:
        return root
    found = _find_in_component(root, name)
    if found is not None:
        return found
    return _find_widget(root.widget, name) if root.mounted else None


def _find_in_component(component: Component, name: str) -> Any:
    """The searches a component defers to its own children.

    A container owns a lookup of its own and a form owns one per field; both
    raise when the name is not theirs, which is not an error here - the caller
    is walking candidates until one answers.
    """
    if isinstance(component, Container):
        found = _lookup(component.find, name)
        if found is not None:
            return found
    finder = getattr(component, "field", None)  # a Form
    return _lookup(finder, name) if callable(finder) else None


def _lookup(searcher: Callable[[str], Any], name: str) -> Any:
    """Run one deferred search, answering ``None`` when it does not know ``name``."""
    try:
        return searcher(name)
    except QgisSdkUiError:
        return None


def _find_widget(widget: Any, name: str) -> Any:
    if widget is None:
        return None
    if callable(getattr(widget, "objectName", None)) and widget.objectName() == name:
        return widget
    finder = getattr(widget, "findChild", None)
    if not callable(finder):
        return _find_fake(widget, name)
    # ``findChild`` wants a type: the QObject base every widget carries,
    # taken from the widget itself so this module never imports Qt.
    base = next((c for c in type(widget).__mro__ if c.__name__ == "QObject"), None)
    if base is None:  # pragma: no cover - a fake tree exposing findChild
        return _find_fake(widget, name)
    return finder(base, name)


def _find_fake(widget: Any, name: str) -> Any:
    for child in getattr(widget, "children", lambda: ())():
        if getattr(child, "objectName", lambda: None)() == name:
            return child
        found = _find_fake(child, name)
        if found is not None:
            return found
    return None


def _qt_signal(widget: Any, signal: str) -> Any:
    candidates: tuple[str, ...]
    if signal == "changed":
        candidates = QT_CHANGED
    else:
        candidates = QT_SIGNALS.get(signal, (signal,))
    for candidate in candidates:
        attribute = getattr(widget, candidate, None)
        if attribute is not None and callable(getattr(attribute, "connect", None)):
            return attribute
    return None


def _adapt(method: Callable[..., Any]) -> Callable[..., Any]:
    """Call ``method`` with the value when it takes one, without it otherwise."""
    try:
        parameters = [
            parameter
            for parameter in inspect.signature(method).parameters.values()
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            or parameter.kind is parameter.VAR_POSITIONAL
        ]
    except (TypeError, ValueError):
        return method
    if parameters:
        return method

    def without_value(*_ignored: object) -> Any:
        return method()

    return without_value
