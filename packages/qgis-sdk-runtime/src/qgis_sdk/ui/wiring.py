"""``@on`` and ``@subscribe``: connect a surface's methods after ``build()``.

decision-55 keeps decorators to marking: ``@on("distance").changed`` and
``@subscribe("progress")`` attach a record to the method and nothing else,
so the method stays a plain method a test calls directly with a fake
context. Once the host (or :func:`qgis_sdk.testing.build_surface`) has the
built tree, :func:`wire_surface` reads the records, finds each named node
- a catalogue component by ``name`` or a Qt widget by ``objectName`` in a
hand-built or ``.ui``-loaded tree - connects the method, and registers the
disconnects with the view's scope, so a closed window hears nothing more.

``@on(name)`` offers the signals the catalogue speaks - ``changed``,
``clicked``, ``toggled``, ``edited``, ``accepted``, ``cancelled``,
``finished``, ``selected`` - and ``@on(name, "textEdited")`` names a Qt
signal of a widget directly.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar

from qgis_sdk.models import QgisSdkUiError

from .components import Component, Container

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = [
    "ON_SIGNALS",
    "WIRES_ATTRIBUTE",
    "OnMarker",
    "Wire",
    "on",
    "subscribe",
    "wire_surface",
    "wires_of",
]

T = TypeVar("T", bound=Callable[..., Any])

WIRES_ATTRIBUTE = "__qgis_sdk_wires__"

#: The catalogue signals ``@on(name).<signal>`` accepts, each mapped to the
#: component's subscription method.
ON_SIGNALS: Mapping[str, str] = MappingProxyType(
    {
        "changed": "changed",
        "clicked": "clicked",
        "toggled": "changed",
        "edited": "changed",
        "accepted": "accepted",
        "cancelled": "cancelled",
        "finished": "finished",
        "selected": "changed",
    }
)

#: What ``changed`` means on a plain Qt widget: the first of these it has.
_QT_CHANGED = (
    "valueChanged",
    "textChanged",
    "toggled",
    "currentIndexChanged",
    "currentTextChanged",
    "dateTimeChanged",
    "dateChanged",
    "colorChanged",
    "layerChanged",
    "fieldChanged",
    "crsChanged",
    "fileChanged",
    "currentChanged",
)

#: A catalogue signal on a plain Qt widget, where it is not ``changed``.
_QT_SIGNALS = {
    "clicked": ("clicked",),
    "toggled": ("toggled",),
    "edited": ("textEdited", "textChanged", "valueChanged"),
    "accepted": ("accepted",),
    "cancelled": ("rejected",),
    "finished": ("finished",),
    "selected": ("itemSelectionChanged", "currentRowChanged", "currentIndexChanged"),
}


@dataclass(frozen=True, slots=True)
class Wire:
    """One connection a method asked for."""

    kind: str  # "on" | "subscribe"
    target: str
    signal: str | None = None
    request: Mapping[str, object] = field(default_factory=dict)


def _mark(method: T, wire: Wire) -> T:
    if not inspect.isfunction(method):
        raise QgisSdkUiError(f"@{wire.kind} marks an instance method")
    wires = list(getattr(method, WIRES_ATTRIBUTE, ()))
    wires.append(wire)
    setattr(method, WIRES_ATTRIBUTE, tuple(wires))
    return method


class OnMarker:
    """``on("distance")``: pick the signal as an attribute, or call with one."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, signal: str) -> Callable[[T], T]:
        if signal.startswith("_") or signal not in ON_SIGNALS:
            known = ", ".join(ON_SIGNALS)
            raise AttributeError(
                f"@on({self._name!r}) has no signal {signal!r}; use one of {known} "
                f"or @on({self._name!r}, {signal!r}) for a Qt signal"
            )
        return self._decorator(signal)

    def __call__(self, method: T) -> T:
        raise QgisSdkUiError(
            f"@on({self._name!r}) needs a signal: @on({self._name!r}).changed "
            f"or @on({self._name!r}, 'valueChanged')"
        )

    def _decorator(self, signal: str) -> Callable[[T], T]:
        def decorate(method: T) -> T:
            return _mark(method, Wire("on", self._name, signal))

        return decorate


def on(name: str, signal: str | None = None) -> Any:
    """Mark a method to run when node ``name`` emits ``signal``.

    ``@on("distance").changed`` for a catalogue signal; ``@on("distance",
    "valueChanged")`` for a Qt signal by name (it also resolves against the
    catalogue's names, so ``@on("go", "clicked")`` works on a ``Button``).
    """
    if not isinstance(name, str) or not name:
        raise QgisSdkUiError("@on needs the name of a node")
    marker = OnMarker(name)
    if signal is None:
        return marker
    if not isinstance(signal, str) or not signal:
        raise QgisSdkUiError(f"@on({name!r}): the signal must be a name")
    return marker._decorator(signal)


def subscribe(stream: str, /, **request: object) -> Callable[[T], T]:
    """Mark a method to receive every event of the plugin's ``stream``.

    The method takes the :class:`~qgis_sdk.ui.streams.StreamEvent`. The
    subscription opens after ``build()`` with ``request`` as the stream's
    arguments and ends with the view's scope.
    """
    if not isinstance(stream, str) or not stream:
        raise QgisSdkUiError("@subscribe needs the id of a stream")

    def decorate(method: T) -> T:
        return _mark(method, Wire("subscribe", stream, None, dict(request)))

    return decorate


def wires_of(cls: type) -> tuple[tuple[str, Wire], ...]:
    """Every ``(method name, wire)`` a surface class declares, base classes first."""
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
            plan.append(_subscription(ctx, wire, method))
        else:
            plan.append(_connection(root, wire, method, surface))
    disconnects: list[Callable[[], None]] = []
    for connect in plan:
        disconnects.append(connect())

    def unwire() -> None:
        while disconnects:
            disconnects.pop()()

    if disconnects:
        ctx.scope.on_close(unwire)
    behaviours = getattr(surface, "_attach_behaviours", None)
    if callable(behaviours):
        behaviours(root, ctx)
    return len(disconnects)


def _subscription(
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
        subscription = streams.subscribe(wire.target, method, **wire.request)
        return subscription.dispose

    return connect


def _connection(
    root: Any, wire: Wire, method: Callable[..., Any], surface: Any
) -> Callable[[], Callable[[], None]]:
    node = _find(root, wire.target)
    if node is None:
        raise QgisSdkUiError(
            f"@on({wire.target!r}) on {type(surface).__name__}: "
            f"build() produced no node named {wire.target!r}"
        )
    signal = wire.signal or "changed"
    if isinstance(node, Component):
        subscription_name = ON_SIGNALS.get(signal, signal)
        subscribe_method = getattr(node, subscription_name, None)
        if not callable(subscribe_method) or subscription_name in (
            "attach",
            "mount",
            "dispose",
        ):
            raise QgisSdkUiError(
                f"@on({wire.target!r}).{signal}: {type(node).__name__} "
                f"{wire.target!r} has no such signal"
            )
        listener = _adapt(method)
        return lambda: subscribe_method(listener)
    qt_signal = _qt_signal(node, signal)
    if qt_signal is None:
        raise QgisSdkUiError(
            f"@on({wire.target!r}, {signal!r}): widget {wire.target!r} "
            f"({type(node).__name__}) has no such signal"
        )
    slot = _adapt(method)

    def connect() -> Callable[[], None]:
        qt_signal.connect(slot)

        def disconnect() -> None:
            try:
                qt_signal.disconnect(slot)
            except (TypeError, RuntimeError):  # already gone with the widget
                pass

        return disconnect

    return connect


def _find(root: Any, name: str) -> Any:
    if isinstance(root, Component):
        if root.name == name:
            return root
        if isinstance(root, Container):
            try:
                return root.find(name)
            except QgisSdkUiError:
                pass
        finder = getattr(root, "field", None)  # a Form
        if callable(finder):
            try:
                return finder(name)
            except QgisSdkUiError:
                pass
        if root.mounted:
            return _find_widget(root.widget, name)
        return None
    return _find_widget(root, name)


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
        candidates = _QT_CHANGED
    else:
        candidates = _QT_SIGNALS.get(signal, (signal,))
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
