"""QGIS-free experimental declaration metadata and description generation."""

import inspect
import json
import re
from collections.abc import Callable
from dataclasses import MISSING, dataclass, fields, is_dataclass
from types import UnionType
from typing import (
    Any,
    Literal,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from .models import MAX_SAFE_INTEGER, QgisSdkError

T = TypeVar("T")


class QgisSdkDeclarationError(QgisSdkError):
    """A declaration cannot be represented in the versioned contract."""

    code = "invalid_declaration"


@dataclass(frozen=True)
class _Metadata:
    id: str
    title: str


def _metadata(id: str, title: str) -> _Metadata:
    if not isinstance(id, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", id):
        raise QgisSdkDeclarationError(
            f"Invalid declaration id {id!r}: use a letter followed by letters, digits, _, . or -"
        )
    if not isinstance(title, str) or not title.strip():
        raise QgisSdkDeclarationError(f"{id}: title must be a nonempty string")
    return _Metadata(id, title)


def plugin(*, id: str, title: str) -> Callable[[type[T]], type[T]]:
    """Attach plugin metadata without wrapping or constructing the class."""
    metadata = _metadata(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError("@plugin requires a class")
        if "__qgis_sdk_plugin__" in vars(cls):
            raise QgisSdkDeclarationError(f"{id}: duplicate @plugin declaration")
        cls.__qgis_sdk_plugin__ = metadata
        return cls

    return decorate


def action(*, id: str, title: str) -> Callable[[T], T]:
    """Attach allowlisted action metadata to an ordinary instance method."""
    metadata = _metadata(id, title)

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@action requires an instance method")
        if hasattr(method, "__qgis_sdk_action__"):
            raise QgisSdkDeclarationError(f"{id}: duplicate @action declaration")
        method.__qgis_sdk_action__ = metadata
        return method

    return decorate


@dataclass(frozen=True)
class ActionDescription:
    """Serializable action structure; handler is a binding name, not a callable."""

    id: str
    title: str
    handler: str
    request: dict[str, Any]
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return an independent JSON-compatible value."""
        return json.loads(json.dumps(vars(self), allow_nan=False))


@dataclass(frozen=True)
class PluginDescription:
    """Version 1 description, independent of SDK and future bridge versions."""

    id: str
    title: str
    actions: tuple[ActionDescription, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "actions": [action.to_dict() for action in self.actions],
        }

    def to_json(self) -> str:
        """Produce canonical key ordering with no nonfinite JSON numbers."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )


def _object_schema(properties: dict, required: list[str]) -> dict[str, Any]:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _hints(target: Any, path: str) -> dict[str, Any]:
    try:
        return get_type_hints(target, include_extras=True)
    except (NameError, TypeError) as error:
        raise QgisSdkDeclarationError(
            f"{path}: cannot resolve annotations: {error}"
        ) from error


def _schema(
    annotation: Any, path: str, *, result: bool, stack: tuple = ()
) -> dict[str, Any]:
    primitives = {
        str: "string",
        bool: "boolean",
        float: "number",
        int: "integer",
        type(None): "null",
        None: "null",
    }
    primitive = next(
        (name for cls, name in primitives.items() if annotation is cls), None
    )
    if primitive is not None:
        schema = {"type": primitive}
        if annotation is int:
            schema.update(minimum=-MAX_SAFE_INTEGER, maximum=MAX_SAFE_INTEGER)
        return schema
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return {
            "anyOf": [_schema(arg, path, result=result, stack=stack) for arg in args]
        }
    if origin is list and len(args) == 1:
        return {
            "type": "array",
            "items": _schema(args[0], path + "[]", result=result, stack=stack),
        }
    if origin is Literal:
        if not all(type(value) in (str, int, bool, type(None)) for value in args):
            raise QgisSdkDeclarationError(
                f"{path}: Literal supports only JSON strings, safe integers, booleans and null"
            )
        if any(type(value) is int and abs(value) > MAX_SAFE_INTEGER for value in args):
            raise QgisSdkDeclarationError(
                f"{path}: Literal integer exceeds the safe-integer range"
            )
        return {"enum": list(args)}
    if inspect.isclass(annotation) and is_dataclass(annotation):
        if annotation in stack:
            raise QgisSdkDeclarationError(
                f"{path}: recursive dataclasses are not supported"
            )
        hints = _hints(annotation, path)
        properties, required = {}, []
        for field in fields(annotation):
            properties[field.name] = _schema(
                hints[field.name],
                f"{path}.{field.name}",
                result=result,
                stack=(*stack, annotation),
            )
            if result or (
                field.default is MISSING and field.default_factory is MISSING
            ):
                required.append(field.name)
        return _object_schema(properties, required)
    raise QgisSdkDeclarationError(
        f"{path}: unsupported annotation {annotation!r}; use JSON primitives, list, union, Literal or a dataclass"
    )


def _describe_action(
    name: str, method: Any, declaration: _Metadata
) -> ActionDescription:
    path = f"action {declaration.id} ({name})"
    if (
        not inspect.isfunction(method)
        or inspect.iscoroutinefunction(method)
        or inspect.isgeneratorfunction(method)
        or inspect.isasyncgenfunction(method)
    ):
        raise QgisSdkDeclarationError(
            f"{path}: requires an ordinary synchronous instance method"
        )
    parameters = list(inspect.signature(method).parameters.values())
    if (
        not parameters
        or parameters[0].name != "self"
        or parameters[0].kind
        not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
    ):
        raise QgisSdkDeclarationError(f"{path}: first parameter must be self")
    hints = _hints(method, path)
    properties, required = {}, []
    for parameter in parameters[1:]:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise QgisSdkDeclarationError(
                f"{path}.{parameter.name}: variadic and positional-only inputs are unsupported"
            )
        properties[parameter.name] = _schema(
            hints.get(parameter.name, inspect.Signature.empty),
            f"{path}.{parameter.name}",
            result=False,
        )
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
    result = _schema(
        hints.get("return", inspect.Signature.empty), f"{path}.return", result=True
    )
    return ActionDescription(
        declaration.id,
        declaration.title,
        name,
        _object_schema(properties, required),
        result,
    )


def describe_plugin(cls: type) -> PluginDescription:
    """Inspect trusted author code without constructing it or invoking handlers.

    Annotation resolution may evaluate forward references; this is not a sandbox
    for untrusted Python modules. Dataclass default factories are never called.
    """
    if not inspect.isclass(cls) or "__qgis_sdk_plugin__" not in vars(cls):
        raise QgisSdkDeclarationError("describe_plugin requires a class with @plugin")
    metadata = vars(cls)["__qgis_sdk_plugin__"]
    members = {}
    for base in reversed(cls.__mro__):
        members.update(vars(base))
    actions, ids = [], set()
    for name, member in members.items():
        method = (
            member.__func__
            if isinstance(member, (staticmethod, classmethod))
            else member
        )
        if isinstance(member, property):
            method = member.fget
        if not inspect.isfunction(method):
            continue
        declaration = getattr(method, "__qgis_sdk_action__", None)
        if declaration is None:
            continue
        if declaration.id in ids:
            raise QgisSdkDeclarationError(
                f"action {declaration.id}: duplicate id at {name}"
            )
        ids.add(declaration.id)
        actions.append(_describe_action(name, member, declaration))
    return PluginDescription(
        metadata.id, metadata.title, tuple(sorted(actions, key=lambda item: item.id))
    )
