"""The decorators: ``@plugin``, ``@action``, ``@stream`` and the binding attributes."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    Any,
)

from qgis_sdk.declarations._contract import STREAM_EVENT_KINDS, QgisSdkDeclarationError
from qgis_sdk.declarations._metadata import (
    Metadata,
    T,
    attach_describe,
    declare_class,
    method_metadata,
    validate_given,
)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_stream_p1(_s):
    validate_given(_s.id, _s.title)
    _s.label = _s.id if _s.id is not None else "stream"
    if not isinstance(_s.events, dict):
        raise QgisSdkDeclarationError(
            f"{_s.label}: events must be a mapping of kind to type"
        )
    if not _s.events:
        raise QgisSdkDeclarationError(
            f"{_s.label}: a stream declares at least one event kind"
        )


def _cc_stream_p2(_s):
    for kind in _s.events:
        _s.kind = kind
        if _s.kind not in STREAM_EVENT_KINDS:
            raise QgisSdkDeclarationError(
                f"{_s.label}: {_s.kind!r} is not a stream event kind; "
                f"use one of {', '.join(STREAM_EVENT_KINDS)}"
            )


def _cc_stream_p3(_s):

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@stream requires an instance method")
        declared = method_metadata(method, _s.id, _s.title)
        _require_undeclared(method, declared.id, "@stream")
        refuse_bindings(method, "@stream")
        attach_describe(method)
        method.__qgis_sdk_stream__ = _StreamMetadata(
            declared.id, declared.title, dict(_s.events)
        )
        return method

    _s.decorate = decorate


def _cc_stream_p4(_s):

    return _CcReturn(_s.decorate)


PLUGIN_ATTRIBUTE = "__qgis_sdk_plugin__"
#: An SDK class with this dict describes itself as an action *result* (the
#: handle a job-submitting action returns); ``WIRE_VALUE_METHOD`` is how the
#: dispatcher turns the instance into that JSON.
WIRE_SCHEMA_ATTRIBUTE = "__qgis_sdk_schema__"
WIRE_VALUE_METHOD = "__qgis_sdk_wire__"


def plugin(
    cls: type[T] | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach plugin metadata without wrapping or constructing the class.

    ``@plugin`` alone derives the id (``field_tools_<hash>`` for a class named
    ``FieldTools``) and the title (``Field Tools``); ``id=`` and ``title=``
    override either one.
    """
    decorate = declare_class(PLUGIN_ATTRIBUTE, "@plugin", id=id, title=title)

    def decorate_plugin(target: type[T]) -> type[T]:
        decorate(target)
        validate_plugin_bindings(target)
        return target

    if cls is None:
        return decorate_plugin
    return decorate_plugin(cls)


BINDINGS_ATTRIBUTE = "__qgis_sdk_bindings__"
BINDING_ORDER_ATTRIBUTE = "__qgis_sdk_binding_order__"


def bindings_of(target: object) -> tuple[Any, ...]:
    """The Desktop bindings declared on ``target`` itself (:mod:`qgis_sdk.bindings`).

    Read from ``vars`` so a binding on a parent class is never the child's;
    innermost decorator first, the way the source reads bottom-up.
    """
    if not hasattr(target, "__dict__"):
        return ()
    return tuple(vars(target).get(BINDINGS_ATTRIBUTE, ()))


def refuse_bindings(
    target: Any, decorator: str, *, instead: str = "bind an @action instead"
) -> None:
    """``@job``/``@stream``/``@tool`` applied over a binding: refuse, with a way forward."""
    if bindings_of(target):
        raise QgisSdkDeclarationError(
            f"{decorator} cannot carry a toolbar, menu or shortcut binding "
            f"({target.__name__}); {instead}"
        )


def validate_plugin_bindings(cls: type) -> None:
    """Refuse a method that carries a binding but no ``@action``.

    ``@tool`` refuses a binding itself, in either order; a plain method is
    refused here, when the class is created, because that is where the
    declaration would have had to be.
    """
    for name, member in vars(cls).items():
        function = member.__func__ if isinstance(member, staticmethod) else member
        if not inspect.isfunction(function) or not bindings_of(function):
            continue
        if not hasattr(function, "__qgis_sdk_action__"):
            raise QgisSdkDeclarationError(
                f"{cls.__name__}.{name} carries a binding but is not an @action; "
                "add one (a @tool is started by an @action that calls start())"
            )


def action(
    method: T | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach allowlisted action metadata to an ordinary instance method.

    ``@action`` alone names the action after the method (``list_layers``, titled
    ``List layers``); ``id=`` and ``title=`` override either one.
    """
    validate_given(id, title)

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@action requires an instance method")
        declared = method_metadata(method, id, title)
        _require_undeclared(method, declared.id, "@action")
        attach_describe(method)
        method.__qgis_sdk_action__ = declared
        return method

    if method is None:
        return decorate
    return decorate(method)


@dataclass(frozen=True)
class _StreamMetadata(Metadata):
    events: dict[str, Any]


def stream(
    *, events: Any, id: str | None = None, title: str | None = None
) -> Callable[[T], T]:
    """Attach stream metadata to an instance method that produces events.

    ``events`` maps each event kind the stream emits (``data``, ``progress``,
    ``state``) to the annotation of that kind's payload. It is the declaration of
    the wire (decision-28): the method's parameters are the subscribe request,
    its return annotation is not described (it still has to resolve, like every
    annotation), and a kind the map does not name is one the host refuses to
    emit. An omitted ``id`` or ``title`` comes from the method name, as for
    ``@action``.
    """
    _s = _CcState(events=events, id=id, title=title)
    for _p in (_cc_stream_p1, _cc_stream_p2, _cc_stream_p3, _cc_stream_p4):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def _require_undeclared(method: Any, id: str, decorator: str) -> None:
    """One method is one operation: it cannot be an action and a stream at once."""
    for marker in ("__qgis_sdk_action__", "__qgis_sdk_stream__"):
        if hasattr(method, marker):
            raise QgisSdkDeclarationError(f"{id}: duplicate {decorator} declaration")
