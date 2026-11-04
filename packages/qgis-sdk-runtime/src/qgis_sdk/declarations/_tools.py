"""``@tool``: a method that draws one geometry and answers with it.

decision-54 point 3 asks for capture tools as a declaration, not as a widget:
the author writes an ordinary method that takes the geometry the user drew, and
the SDK knows the shape to collect it in.

    from qgis_sdk.declarations import tool

    @tool(captures="polygon", id="area", title="Draw an area")
    def area(self, geometry: Geometry) -> str:
        return self.ctx.features.evaluate("$area", ...)

Three choices are deliberate.

*A tool is a declaration, not a surface.* It carries an id, a title and the
shape it captures, and it is described by :func:`describe` exactly like a job -
so a console can list what a plugin can draw without constructing it, and the
plugin description the page and the agent already read does not move. A binding
refuses it the way it refuses a job: the button goes on an ``@action`` that
calls :func:`start`, next to the ``@tool`` it starts.

*The shape is one of the three a user can draw.* ``point``, ``line`` and
``polygon`` are what a map tool collects; a multipoint or a collection is what a
provider stores. Asking for anything else is refused where it is written rather
than when somebody clicks.

*Capture is asynchronous and the tool is not on the click path.* A drawing takes
as long as a person takes, so :func:`start` asks the canvas for the drawing and
returns a canceller; the method runs when the geometry arrives, on the GUI
thread, and a body with real work in it hands that work to ``ctx.jobs``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.declarations._describe import register_describer
from qgis_sdk.declarations._metadata import (
    Metadata,
    T,
    attach_describe,
    derive_id,
    derive_title,
    validate_given,
)
from qgis_sdk.declarations._plugin import refuse_bindings
from qgis_sdk.models.canvas import CAPTURE_SHAPES
from qgis_sdk.models.features import Geometry

__all__ = ["TOOL_ATTRIBUTE", "ToolDescription", "declared_tools", "start", "tool"]

TOOL_ATTRIBUTE = "__qgis_sdk_tool__"


@dataclass(frozen=True)
class _ToolMetadata(Metadata):
    """What ``@tool`` records: the metadata plus the shape it captures."""

    captures: str


@dataclass(frozen=True)
class ToolDescription:
    """A declared tool: its id, its title and the shape a user draws."""

    id: str
    title: str
    captures: str
    #: The method name on the plugin class, so a reader can find the body.
    handler: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "captures": self.captures,
            "handler": self.handler,
        }


def _refuse_unknown_shape(captures: Any, path: str) -> str:
    """Return ``captures`` when it is a drawable shape, refuse the rest by name."""
    if captures not in CAPTURE_SHAPES:
        raise QgisSdkDeclarationError(
            f"{path}: captures is one of {', '.join(CAPTURE_SHAPES)}, not {captures!r}"
        )
    return str(captures)


def _is_a_geometry(annotation: Any) -> bool:
    """Whether ``annotation`` is the drawn geometry, written or quoted.

    A module with ``from __future__ import annotations`` leaves the annotation a
    string, so a forward reference is read by name - the same leniency a
    description has, without importing anything to resolve it.
    """
    if annotation is inspect.Signature.empty or annotation is Geometry:
        return True
    if isinstance(annotation, str):
        return annotation.replace(" ", "").rsplit(".", 1)[-1] == "Geometry"
    return False


def _refuse_bad_signature(method: Any, path: str) -> None:
    """A tool takes the drawn geometry and nothing else.

    The geometry arrives from a user, not from a page, so there is no request
    to validate: a second parameter would have nowhere to get a value from.
    """
    parameters = [
        parameter
        for parameter in inspect.signature(method).parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(parameters) != 2:
        raise QgisSdkDeclarationError(
            f"{path}: a tool takes the geometry it drew and nothing else - "
            f"`def name(self, geometry: Geometry)`; this one takes "
            f"{len(parameters)} parameter(s)"
        )
    drawn = parameters[1]
    annotation = drawn.annotation
    if not _is_a_geometry(annotation):
        raise QgisSdkDeclarationError(
            f"{path}: {drawn.name!r} is the geometry the user drew; annotate it "
            f"as Geometry, not {annotation!r}"
        )


def tool(
    method: T | None = None,
    /,
    *,
    captures: str = "polygon",
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Declare a method that captures one ``point``, ``line`` or ``polygon``.

    ``@tool`` alone names the tool after the method and captures a polygon;
    ``id=``, ``title=`` and ``captures=`` override any of the three. The method
    is not wrapped: it is an ordinary instance method that a test can call with
    a hand-built :class:`~qgis_sdk.models.features.Geometry`.
    """
    validate_given(id, title)

    def decorate(target: T) -> T:
        if not inspect.isfunction(target):
            raise QgisSdkDeclarationError("@tool requires an instance method")
        name = getattr(target, "__name__", "tool")
        declared = _ToolMetadata(
            id=id if id is not None else derive_id(name),
            title=title if title is not None else derive_title(name),
            captures=_refuse_unknown_shape(captures, f"tool {id or name}"),
        )
        _refuse_bad_signature(target, f"tool {declared.id}")
        refuse_bindings(
            target,
            "@tool",
            instead="bind an @action that calls start() on it",
        )
        if TOOL_ATTRIBUTE in vars(target):
            raise QgisSdkDeclarationError(f"{name} is already declared as a tool")
        attach_describe(target)
        target.__qgis_sdk_tool__ = declared  # type: ignore[attr-defined]
        return target

    if method is None:
        return decorate
    return decorate(method)


def declared_tools(cls: type) -> tuple[tuple[str, _ToolMetadata], ...]:
    """The tools ``cls`` declares, in source order, as ``(name, metadata)``.

    Read from ``vars`` so a tool on a parent class is never the child's, the
    same rule ``bindings_of`` follows.
    """
    found: list[tuple[str, _ToolMetadata]] = []
    for name, member in vars(cls).items():
        function = (
            member.__func__
            if isinstance(member, (staticmethod, classmethod))
            else member
        )
        declared = (
            vars(function).get(TOOL_ATTRIBUTE) if inspect.isfunction(function) else None
        )
        if declared is not None:
            found.append((name, declared))
    return tuple(found)


def _describe_tool(method: Any) -> ToolDescription:
    declared = vars(method)[TOOL_ATTRIBUTE]
    return ToolDescription(
        id=declared.id,
        title=declared.title,
        captures=declared.captures,
        handler=method.__name__,
    )


def start(method: Any, ctx: Any) -> Callable[[], None]:
    """Start ``method``'s drawing on ``ctx.canvas`` and run it with the result.

    Returns the canceller, so a surface that closes - or a second click on the
    same button - ends the drawing without calling the body. The body runs on
    the GUI thread when the geometry arrives: a tool with real work in it hands
    that work to ``ctx.jobs`` instead of doing it in the drawing's callback.
    """
    function = method.__func__ if inspect.ismethod(method) else method
    declared = vars(function).get(TOOL_ATTRIBUTE)
    if declared is None:
        raise QgisSdkDeclarationError(
            f"{getattr(function, '__name__', function)!r} is not declared with @tool"
        )
    owner = method.__self__ if inspect.ismethod(method) else None
    if owner is None:
        raise QgisSdkDeclarationError(
            f"tool {declared.id}: start the tool on the plugin instance, "
            "not on the class"
        )
    canvas = getattr(ctx, "canvas", None)
    if canvas is None:
        raise QgisSdkDeclarationError(
            f"tool {declared.id}: this context has no canvas, so there is "
            "nothing to draw on"
        )
    return canvas.capture(declared.captures, lambda geometry: method(geometry))


register_describer(TOOL_ATTRIBUTE, _describe_tool)
