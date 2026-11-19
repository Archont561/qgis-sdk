"""Validating declarations: field parents, method shapes and keyword inputs."""

from __future__ import annotations

import inspect
from typing import Any

from qgis_sdk.declarations._contract import QgisSdkDeclarationError

from ._kinds import WIRE_KIND_KEYWORD
from ._schemas import _schema

__all__ = [
    "check_field_parents",
    "keyword_inputs",
    "require_plain_method",
    "require_self_first",
]


def check_field_parents(properties: dict[str, Any], path: str) -> None:
    """Refuse a field input whose ``of`` is not a layer input of the same call.

    A field input names the layer it reads by that layer input's name, so the
    pair has to be in one request: a field of a layer the caller did not also
    send has nothing to read.

    Args:
        properties: The request's fields, keyed by the name each arrives under.
        path: The declaration's path, used in the error message.

    Raises:
        QgisSdkDeclarationError: A field input names no input of the same
            declaration, or names one that is not a layer.
    """
    for name, schema in properties.items():
        intent = schema.get(WIRE_KIND_KEYWORD) if isinstance(schema, dict) else None
        if not intent or intent.get("kind") != "field":
            continue
        parent = properties.get(intent["of"])
        if parent is None:
            raise QgisSdkDeclarationError(
                f"{path}.{name}: of={intent['of']!r} names no input of this "
                "declaration; a field input belongs to a layer input"
            )
        parent_kind = (parent.get(WIRE_KIND_KEYWORD) or {}).get(
            "kind", parent.get("type")
        )
        if parent_kind != "layer":
            raise QgisSdkDeclarationError(
                f"{path}.{name}: of={intent['of']!r} names a {parent_kind} input; "
                "a field input belongs to a layer input"
            )


def require_plain_method(method: Any, path: str, *, generator: bool = False) -> None:
    """Refuse anything that would borrow the host's loop instead of the SDK's.

    A stream may be a generator function - that is the natural way to produce
    events the dispatcher pulls - but neither kind of operation may be a
    coroutine or an async generator.
    """
    if not _is_ordinary_method(method, generator):
        raise QgisSdkDeclarationError(
            f"{path}: requires an ordinary synchronous instance method"
        )


def _is_ordinary_method(method: object, generator: bool) -> bool:
    """Whether a declared method is the plain synchronous one the dispatcher calls.

    A coroutine or an async generator is never one. A plain generator is one
    only where the declaration promises a stream, which is what ``generator``
    records.
    """
    if not inspect.isfunction(method) or inspect.iscoroutinefunction(method):
        return False
    if inspect.isasyncgenfunction(method):
        return False
    return generator or not inspect.isgeneratorfunction(method)


def require_self_first(parameters: list[Any], path: str) -> None:
    """Require a bound method, so the descriptor is per plugin instance.

    Args:
        parameters: The declaration's parameters, in signature order.
        path: The declaration's path, used in the error message.

    Raises:
        QgisSdkDeclarationError: The first parameter is not ``self``, or is not
            the kind a method's first parameter is.
    """
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


def keyword_inputs(
    parameters: list[Any], hints: dict[str, Any], path: str
) -> tuple[dict[str, Any], list[str]]:
    """Describe the accepted inputs and say which of them must arrive.

    A parameter with a default is optional; one without is required. Variadic
    and positional-only parameters are refused rather than described, because
    neither has a name a JSON object could carry.

    Args:
        parameters: The declaration's parameters, ``self`` already removed.
        hints: The resolved annotations, keyed by parameter name, as
            :func:`resolve_hints` answers them.
        path: The declaration's path, used in the error messages.

    Returns:
        Each input's schema keyed by name, and the names that must arrive.

    Raises:
        QgisSdkDeclarationError: A parameter is variadic or positional-only, or
            its annotation is outside the schema subset.
    """
    properties, required = {}, []
    for parameter in parameters:
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
    check_field_parents(properties, path)
    return properties, required
