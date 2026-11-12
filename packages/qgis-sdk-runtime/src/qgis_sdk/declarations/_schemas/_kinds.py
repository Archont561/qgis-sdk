"""The parameter-kind rules: map one input annotation onto its kind and marker."""

from __future__ import annotations

from typing import Annotated, Any, Literal, get_args, get_origin

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.models.files import FileRef
from qgis_sdk.models.parameters import ParameterKind, parameter_kinds

__all__ = ["WIRE_KIND_KEYWORD", "resolve_kind"]

WIRE_KIND_KEYWORD = "x-qgis-sdk"
"""The schema keyword an input's kind rides on, so a page draws the right widget."""

_ENUM_KIND = parameter_kinds()["enum"]
_PRIMITIVE_KIND_NAMES: dict[Any, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}


def _resolve_kind_tail1(**values):
    annotation = values["annotation"]
    base = values["base"]
    kinds = values["kinds"]
    markers = values["markers"]
    path = values["path"]
    strict = values["strict"]
    if get_origin(annotation) is Annotated:
        base, *markers = get_args(annotation)
    for marker in markers:
        kind = next((k for k in kinds.values() if k.marker is type(marker)), None)
        if kind is None:
            if strict:
                raise _refuse_kind(path, f"unknown parameter marker {marker!r}")
            continue
        if base not in kind.stored:
            raise _refuse_kind(path, kind.refusal)
        return kind, marker
    literal = _literal_kind(base, path)
    if literal is not None:
        return literal
    return _resolve_kind_phase1(base, kinds, path)


def _literal_kind(base, path):
    """An enum is a ``Literal[...]`` of strings, with no marker."""
    if get_origin(base) is Literal:
        choices = get_args(base)
        if not choices or not all(type(choice) is str for choice in choices):
            raise _refuse_kind(path, "enum choices must be strings")
        return _ENUM_KIND, None
    return None


def _resolve_kind_phase1(base, kinds, path):
    if base is FileRef:
        raise _refuse_kind(
            path, "a FileRef input needs FileInput(filters=...) or DirectoryInput()"
        )
    name = _PRIMITIVE_KIND_NAMES.get(base)
    if name is None:
        raise _refuse_kind(path, f"cannot express {base!r} as a host parameter")
    return kinds[name], None


def resolve_kind(
    path: str, annotation: Any, *, strict: bool = True
) -> tuple[ParameterKind, Any]:
    """Map one input annotation onto its :class:`ParameterKind` and marker.

    ``LayerInput`` and ``Annotated[str, LayerParameter()]`` are the same
    annotation, so they map to the same kind; a marker on a type it does not
    fit (``Annotated[int, LayerParameter()]``) is refused with ``path`` named.
    ``Literal[...]`` of strings is the ``enum`` kind; the marker is ``None``
    for it and for the primitives. An ``Annotated`` extra that is not an SDK
    marker is refused when ``strict`` (an algorithm's inputs all render in a
    toolbox) and skipped otherwise (an action may carry another library's
    metadata beside the SDK's).
    """
    kinds = parameter_kinds()
    base, markers = annotation, ()
    return _resolve_kind_tail1(**{**globals(), **locals()})


def _refuse_kind(path: str, detail: str) -> QgisSdkDeclarationError:
    supported = ", ".join(parameter_kinds())
    return QgisSdkDeclarationError(
        f"{path}: {detail}; use Annotated markers ({supported})"
    )
