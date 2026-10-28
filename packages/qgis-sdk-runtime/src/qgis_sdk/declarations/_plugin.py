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


def refuse_bindings(target: Any, decorator: str) -> None:
    """``@job``/``@stream`` applied over a binding: refuse with the way forward."""
    if bindings_of(target):
        raise QgisSdkDeclarationError(
            f"{decorator} cannot carry a toolbar, menu or shortcut binding "
            f"({target.__name__}); bind an @action instead"
        )


def validate_plugin_bindings(cls: type) -> None:
    """Refuse a plain method that carries a binding, when the class is created.

    Bindings stack on ``@action`` in any order, so a binding applied below
    ``@action`` cannot tell yet; the plugin class is where both are known.
    """
    for name, member in vars(cls).items():
        function = member.__func__ if isinstance(member, staticmethod) else member
        if not inspect.isfunction(function) or not bindings_of(function):
            continue
        if not hasattr(function, "__qgis_sdk_action__"):
            raise QgisSdkDeclarationError(
                f"{cls.__name__}.{name} carries a binding but is not an @action; "
                "add @action (bindings stack on it in any order)"
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
    validate_given(id, title)
    label = id if id is not None else "stream"
    if not isinstance(events, dict):
        raise QgisSdkDeclarationError(
            f"{label}: events must be a mapping of kind to type"
        )
    if not events:
        raise QgisSdkDeclarationError(
            f"{label}: a stream declares at least one event kind"
        )
    for kind in events:
        if kind not in STREAM_EVENT_KINDS:
            raise QgisSdkDeclarationError(
                f"{label}: {kind!r} is not a stream event kind; "
                f"use one of {', '.join(STREAM_EVENT_KINDS)}"
            )

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@stream requires an instance method")
        declared = method_metadata(method, id, title)
        _require_undeclared(method, declared.id, "@stream")
        refuse_bindings(method, "@stream")
        attach_describe(method)
        method.__qgis_sdk_stream__ = _StreamMetadata(
            declared.id, declared.title, dict(events)
        )
        return method

    return decorate


def _require_undeclared(method: Any, id: str, decorator: str) -> None:
    """One method is one operation: it cannot be an action and a stream at once."""
    for marker in ("__qgis_sdk_action__", "__qgis_sdk_stream__"):
        if hasattr(method, marker):
            raise QgisSdkDeclarationError(f"{id}: duplicate {decorator} declaration")
