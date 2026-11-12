"""The decorators: ``@on`` and ``@subscribe``."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from qgis_sdk.declarations import WIRES_ATTRIBUTE, attach_describe
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import Component

from ._types import ON_SIGNALS, T, Wire, shown


def _mark(method: T, wire: Wire) -> T:
    if not inspect.isfunction(method):
        raise QgisSdkUiError(f"@{wire.kind} marks an instance method")
    attach_describe(method)
    wires = list(getattr(method, WIRES_ATTRIBUTE, ()))
    wires.append(wire)
    setattr(method, WIRES_ATTRIBUTE, tuple(wires))
    return method


class OnMarker:
    """``on("distance")``: pick the signal as an attribute, or call with one."""

    __slots__ = ("_target",)

    def __init__(self, target: str | Component) -> None:
        self._target = target

    def __getattr__(self, signal: str) -> Callable[[T], T]:
        if signal.startswith("_") or signal not in ON_SIGNALS:
            known = ", ".join(ON_SIGNALS)
            target_shown = shown(self._target)
            raise AttributeError(
                f"@on({target_shown}) has no signal {signal!r}; use one of {known} "
                f"or @on({target_shown}, {signal!r}) for a Qt signal"
            )
        return self._decorator(signal)

    def __call__(self, method: T) -> T:
        target_shown = shown(self._target)
        raise QgisSdkUiError(
            f"@on({target_shown}) needs a signal: @on({target_shown}).changed "
            f"or @on({target_shown}, 'valueChanged')"
        )

    def _decorator(self, signal: str) -> Callable[[T], T]:
        def decorate(method: T) -> T:
            return _mark(method, Wire("on", self._target, signal))

        return decorate


def on(target: str | Component, signal: str | None = None) -> Any:
    """Mark a method to run when ``target`` emits ``signal``.

    ``target`` is a node name - ``@on("distance").changed`` for a catalogue
    signal, ``@on("distance", "valueChanged")`` for a Qt signal by name (it
    also resolves against the catalogue's names, so ``@on("go", "clicked")``
    works on a ``Button``) - or a component declared on the surface class
    (``@on(clear).clicked``), which wires to that window's copy of it.
    """
    if isinstance(target, Component) or isinstance(target, str) and target:
        marker = OnMarker(target)
    else:
        raise QgisSdkUiError("@on needs the name of a node or a component")
    if signal is None:
        return marker
    if not isinstance(signal, str) or not signal:
        raise QgisSdkUiError(f"@on({shown(target)}): the signal must be a name")
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
